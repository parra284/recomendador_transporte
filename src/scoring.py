"""Puntuación de proveedores elegibles con pesos configurables por perfil."""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median

import yaml

from src.restricciones import cargar_tarifas

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "data"
RUTA_PERFILES = RAIZ / "config" / "perfiles.yaml"
VARIABLES = ("precio", "tiempo", "confiabilidad", "etiquetas")
FORMATO_FECHA = "%Y-%m-%dT%H:%M"


@dataclass(frozen=True)
class Viaje:
    id_proveedor: str
    origen: str
    destino: str
    horas: float
    a_tiempo: bool


@dataclass(frozen=True)
class Etiqueta:
    id_proveedor: str
    tipo: str          # fortaleza | debilidad
    etiqueta: str
    condicion: str     # campo=valor, admite * al final


@dataclass(frozen=True)
class DatosScoring:
    tarifas: dict      # {(id_proveedor, origen, destino, tipo): precio_cop}
    viajes: tuple      # tupla de Viaje
    tiempos_base: dict  # {(origen, destino): horas_base}
    etiquetas: tuple   # tupla de Etiqueta


@dataclass(frozen=True)
class ConfigScoring:
    perfiles: dict     # {perfil: {variable: peso}}
    piso_confiabilidad: float
    min_viajes: int
    etiqueta_base: float
    ajuste_por_etiqueta: float


@dataclass(frozen=True)
class Confiabilidad:
    valor: float
    viajes: int
    aciertos: int
    mezclada: bool     # True si tenía menos de min_viajes y se mezcló con el promedio general
    alcance: str       # "corredor" o "historial_completo"


@dataclass
class PuntajeProveedor:
    id_proveedor: str
    perfil: str
    puntaje: float
    crudos: dict          # precio (COP), tiempo (h), confiabilidad (fracción), etiquetas (lista)
    normalizados: dict    # cada variable en [0, 1]
    aportes: dict         # peso * normalizado * 100; suman el puntaje
    etiquetas: list       # Etiqueta que coincidieron con la solicitud
    tiempo_desde_historial: bool
    confiabilidad: Confiabilidad


# --- Configuración ---

def validar_perfiles(perfiles):
    """Lanza ValueError si a un perfil le falta una variable o sus pesos no suman 1."""
    for nombre, pesos in perfiles.items():
        faltantes = set(VARIABLES) - set(pesos)
        if faltantes:
            raise ValueError(f"El perfil '{nombre}' no tiene peso para: {', '.join(sorted(faltantes))}")
        total = sum(pesos.values())
        if abs(total - 1) > 1e-9:
            raise ValueError(f"Los pesos del perfil '{nombre}' suman {total:g} y deben sumar 1")


def cargar_config(ruta=RUTA_PERFILES):
    with open(ruta, encoding="utf-8") as archivo:
        contenido = yaml.safe_load(archivo)
    validar_perfiles(contenido["perfiles"])
    parametros = contenido["parametros"]
    return ConfigScoring(
        perfiles=contenido["perfiles"],
        piso_confiabilidad=float(parametros["piso_confiabilidad"]),
        min_viajes=int(parametros["min_viajes"]),
        etiqueta_base=float(parametros["etiqueta_base"]),
        ajuste_por_etiqueta=float(parametros["ajuste_por_etiqueta"]),
    )


# --- Carga de datos ---

def _leer_csv(ruta):
    with open(ruta, encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def viaje_desde_fila(fila):
    cargue = datetime.strptime(fila["cargue"], FORMATO_FECHA)
    entrega = datetime.strptime(fila["entrega"], FORMATO_FECHA)
    comprometida = datetime.strptime(fila["entrega_comprometida"], FORMATO_FECHA)
    return Viaje(fila["id_proveedor"], fila["origen"], fila["destino"],
                 horas=(entrega - cargue).total_seconds() / 3600,
                 a_tiempo=entrega <= comprometida)


def cargar_datos_scoring(dir_datos=DIR_DATOS):
    dir_datos = Path(dir_datos)
    return DatosScoring(
        tarifas=cargar_tarifas(dir_datos),
        viajes=tuple(viaje_desde_fila(f) for f in _leer_csv(dir_datos / "historial_viajes.csv")),
        tiempos_base={(f["origen"], f["destino"]): float(f["horas_base"])
                      for f in _leer_csv(dir_datos / "tiempos_base.csv")},
        etiquetas=tuple(Etiqueta(**f) for f in _leer_csv(dir_datos / "etiquetas.csv")),
    )


# --- Valores crudos ---

def precio(solicitud, id_proveedor, datos):
    return datos.tarifas[(id_proveedor, solicitud.origen, solicitud.destino, solicitud.tipo_contenedor)]


def viajes_del_proveedor(id_proveedor, viajes):
    return [v for v in viajes if v.id_proveedor == id_proveedor]


def viajes_del_corredor(solicitud, viajes):
    return [v for v in viajes if (v.origen, v.destino) == (solicitud.origen, solicitud.destino)]


def tiempo(solicitud, id_proveedor, datos, min_viajes):
    """(horas, desde_historial): mediana del corredor si hay min_viajes viajes; si no, horas_base."""
    del_corredor = viajes_del_corredor(solicitud, viajes_del_proveedor(id_proveedor, datos.viajes))
    if len(del_corredor) >= min_viajes:
        return median(v.horas for v in del_corredor), True
    return datos.tiempos_base[(solicitud.origen, solicitud.destino)], False


def promedio_general_a_tiempo(viajes):
    """Fracción de viajes a tiempo en todo el historial (todos los proveedores)."""
    return sum(v.a_tiempo for v in viajes) / len(viajes)


def confiabilidad(solicitud, id_proveedor, datos, min_viajes):
    propios = viajes_del_proveedor(id_proveedor, datos.viajes)
    del_corredor = viajes_del_corredor(solicitud, propios)
    if len(del_corredor) >= min_viajes:
        usados, alcance = del_corredor, "corredor"
    else:
        usados, alcance = propios, "historial_completo"
    viajes, aciertos = len(usados), sum(v.a_tiempo for v in usados)
    if viajes >= min_viajes:
        return Confiabilidad(aciertos / viajes, viajes, aciertos, mezclada=False, alcance=alcance)
    promedio = promedio_general_a_tiempo(datos.viajes)
    valor = (aciertos + min_viajes * promedio) / (viajes + min_viajes)
    return Confiabilidad(valor, viajes, aciertos, mezclada=True, alcance=alcance)


def valor_como_texto(valor):
    """Representación de un campo de la solicitud para comparar con las condiciones."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, float):
        return f"{valor:g}"
    if isinstance(valor, datetime):
        return valor.strftime(FORMATO_FECHA)
    return "" if valor is None else str(valor)


def condicion_coincide(condicion, solicitud):
    campo, _, esperado = condicion.partition("=")
    real = valor_como_texto(getattr(solicitud, campo, None))
    if esperado.endswith("*"):
        return real.startswith(esperado[:-1])
    return real == esperado


def etiquetas_coincidentes(solicitud, id_proveedor, datos):
    return [e for e in datos.etiquetas
            if e.id_proveedor == id_proveedor and condicion_coincide(e.condicion, solicitud)]


# --- Normalización ---

def normalizar_menor_es_mejor(valor, valores):
    """(max - valor) / (max - min); 1 si todos son iguales o hay uno solo."""
    maximo, minimo = max(valores), min(valores)
    if maximo == minimo:
        return 1.0
    return (maximo - valor) / (maximo - minimo)


def _limitar(valor):
    return max(0.0, min(1.0, valor))


def normalizar_confiabilidad(valor, piso):
    return _limitar((valor - piso) / (1 - piso))


def normalizar_etiquetas(etiquetas, base, ajuste):
    fortalezas = sum(e.tipo == "fortaleza" for e in etiquetas)
    debilidades = sum(e.tipo == "debilidad" for e in etiquetas)
    return _limitar(base + ajuste * fortalezas - ajuste * debilidades)


# --- Puntaje ---

def calcular_aportes(pesos, normalizados):
    return {v: 100 * pesos[v] * normalizados[v] for v in VARIABLES}


def puntuar(solicitud, ids_proveedores, datos, config):
    """Puntúa a los proveedores elegibles; devuelve PuntajeProveedor ordenados de mayor a menor."""
    if solicitud.prioridad not in config.perfiles:
        raise ValueError(f"No hay perfil de pesos para la prioridad '{solicitud.prioridad}'")
    if not ids_proveedores:
        return []
    pesos = config.perfiles[solicitud.prioridad]

    crudos = {}
    for id_p in ids_proveedores:
        horas, desde_historial = tiempo(solicitud, id_p, datos, config.min_viajes)
        crudos[id_p] = {
            "precio": precio(solicitud, id_p, datos),
            "tiempo": horas,
            "desde_historial": desde_historial,
            "confiabilidad": confiabilidad(solicitud, id_p, datos, config.min_viajes),
            "etiquetas": etiquetas_coincidentes(solicitud, id_p, datos),
        }
    precios = [c["precio"] for c in crudos.values()]
    tiempos = [c["tiempo"] for c in crudos.values()]

    resultados = []
    for id_p, c in crudos.items():
        normalizados = {
            "precio": normalizar_menor_es_mejor(c["precio"], precios),
            "tiempo": normalizar_menor_es_mejor(c["tiempo"], tiempos),
            "confiabilidad": normalizar_confiabilidad(c["confiabilidad"].valor, config.piso_confiabilidad),
            "etiquetas": normalizar_etiquetas(c["etiquetas"], config.etiqueta_base, config.ajuste_por_etiqueta),
        }
        aportes = calcular_aportes(pesos, normalizados)
        resultados.append(PuntajeProveedor(
            id_proveedor=id_p,
            perfil=solicitud.prioridad,
            puntaje=sum(aportes.values()),
            crudos={"precio": c["precio"], "tiempo": c["tiempo"],
                    "confiabilidad": c["confiabilidad"].valor, "etiquetas": c["etiquetas"]},
            normalizados=normalizados,
            aportes=aportes,
            etiquetas=c["etiquetas"],
            tiempo_desde_historial=c["desde_historial"],
            confiabilidad=c["confiabilidad"],
        ))
    return sorted(resultados, key=lambda r: r.puntaje, reverse=True)
