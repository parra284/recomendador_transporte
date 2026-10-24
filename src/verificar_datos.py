"""Verifica que la base, la configuración, las solicitudes y el modelo sean coherentes entre sí.

Uso: python -m src.verificar_datos

Revisa:
1. Base de datos: columnas que usan los modelos, sin vacíos, códigos únicos y reglas internas
   (a_tiempo = tránsito real <= prometido; cada categoría de carga va en un solo contenedor).
2. Hoja Panel_Proveedor_Mes: coincide con lo que se agrega de la hoja de envíos.
3. config/perfiles.yaml: pesos válidos y un perfil por cada contenedor de la base.
4. Archivos de solicitudes: columnas exactas y códigos que existen en la base.
5. Modelo guardado: entrenado con la base actual, mismos proveedores y cupos coherentes.
"""

import sys

import numpy as np
import pandas as pd

from src.fuente_datos import archivos_solicitudes, leer_envios, leer_hoja
from src.motor import configuracion
from src.solicitud import COLUMNAS, catalogos_desde_envios, cargar_solicitudes

COLUMNAS_BASE = [
    "id_envio", "mes", "fecha_orden", "origen", "destino", "tipo_contenedor", "categoria_carga",
    "distancia_km", "zona", "tipo_carga", "peso_por_bulto_kg", "bultos_unidades", "peso_total_kg",
    "valor_declarado_cop", "fragil", "seguro", "nivel_velocidad", "proveedor", "precio_cop",
    "transito_prometido_h", "temporada_alta", "transito_real_h", "a_tiempo", "danado", "satisfaccion_1a5",
]
HOJA_PANEL = "Panel_Proveedor_Mes"
# solicitudes_invalidas.csv solo se revisa por columnas: sus errores son intencionales.
ARCHIVOS_SIN_REVISION_DE_CODIGOS = {"solicitudes_invalidas.csv"}
TOLERANCIA = 1e-6


# --- Base de datos ---

def errores_de_base(envios):
    faltan = [c for c in COLUMNAS_BASE if c not in envios.columns]
    if faltan:
        return [f"Base: faltan columnas {', '.join(faltan)}"]
    errores = []
    vacios = envios[COLUMNAS_BASE].isna().sum()
    errores += [f"Base: {n} vacíos en {c}" for c, n in vacios.items() if n]
    repetidos = envios["id_envio"].duplicated().sum()
    if repetidos:
        errores.append(f"Base: {repetidos} códigos id_envio repetidos")
    distinto = (envios["a_tiempo"] != (envios["transito_real_h"] <= envios["transito_prometido_h"]).astype(int)).sum()
    if distinto:
        errores.append(f"Base: {distinto} envíos con a_tiempo distinto de (tránsito real <= prometido)")
    contenedores = envios.groupby("categoria_carga")["tipo_contenedor"].nunique()
    for categoria in contenedores[contenedores > 1].index:
        errores.append(f"Base: la categoría '{categoria}' aparece en más de un contenedor")
    return errores


def errores_de_panel(envios, panel):
    """La hoja resumen debe coincidir con lo que se agrega de los envíos."""
    agregado = envios.groupby(["proveedor", "mes"]).agg(
        pedidos=("id_envio", "size"), a_tiempo_pct=("a_tiempo", "mean"),
        satisfaccion=("satisfaccion_1a5", "mean"), transito_h=("transito_real_h", "mean")).reset_index()
    cruce = panel.merge(agregado, on=["proveedor", "mes"], how="outer", suffixes=("_panel", "_envios"),
                        indicator=True)
    errores = []
    sueltas = (cruce["_merge"] != "both").sum()
    if sueltas:
        errores.append(f"{HOJA_PANEL}: {sueltas} filas proveedor-mes no coinciden con los envíos")
    ambos = cruce[cruce["_merge"] == "both"]
    for c in ["pedidos", "a_tiempo_pct", "satisfaccion", "transito_h"]:
        dif = np.abs(ambos[f"{c}_panel"] - ambos[f"{c}_envios"]).max()
        if dif > TOLERANCIA:
            errores.append(f"{HOJA_PANEL}: {c} difiere de los envíos hasta en {dif:g}")
    return errores


# --- Configuración ---

def errores_de_perfiles(perfiles, envios):
    errores = [f"perfiles.yaml: {e}" for e in configuracion.validar_perfiles(perfiles)]
    en_base = set(envios["tipo_contenedor"])
    en_config = set(perfiles["pesos_por_contenedor"])
    if en_base - en_config:
        errores.append(f"perfiles.yaml: sin pesos para {', '.join(sorted(en_base - en_config))}, que está en la base")
    if en_config - en_base:
        errores.append(f"perfiles.yaml: pesos para {', '.join(sorted(en_config - en_base))}, que no está en la base")
    otras = set(envios["nivel_velocidad"]) - set(configuracion.VELOCIDADES)
    if otras:
        errores.append(f"Base: velocidades desconocidas para el modelo: {', '.join(sorted(otras))}")
    return errores


# --- Solicitudes ---

def errores_de_columnas(nombre, columnas):
    if columnas == COLUMNAS:
        return []
    return [f"{nombre}: columnas {columnas} != esperadas {COLUMNAS}"]


def errores_de_solicitudes(ruta, catalogos):
    with open(ruta, encoding="utf-8-sig") as archivo:
        columnas = archivo.readline().strip().split(",")
    errores = errores_de_columnas(ruta.name, columnas)
    if errores or ruta.name in ARCHIVOS_SIN_REVISION_DE_CODIGOS:
        return errores
    _, invalidas = cargar_solicitudes(ruta, catalogos)
    return [f"{ruta.name} fila {e.fila} ({e.campo}): {e.mensaje}" for e in invalidas]


# --- Modelo ---

def errores_de_modelo(rec, envios, min_servicios):
    errores = []
    if not configuracion.modelo_al_dia():
        errores.append("Modelo: no corresponde a la base, la configuración, el código o las librerías actuales "
                       "(python -m src.entrenar_modelos)")
    if rec is None:
        return errores
    if sorted(rec.m1.proveedores) != sorted(envios["proveedor"].unique()):
        errores.append("Modelo: sus proveedores no son los de la base")
    if len(rec.hist) != len(envios):
        errores.append(f"Modelo: se entrenó con {len(rec.hist)} envíos y la base tiene {len(envios)}")
    servicios = envios.groupby(["proveedor", "tipo_contenedor"]).size()
    ofrecidos = set(servicios[servicios >= min_servicios].index)
    con_cupos = set(zip(rec.cap["proveedor"], rec.cap["tipo_contenedor"]))
    if con_cupos != ofrecidos:
        errores.append("capacidad_semana.csv: los pares proveedor-contenedor no coinciden con el catálogo "
                       f"(sobran {sorted(con_cupos - ofrecidos)}, faltan {sorted(ofrecidos - con_cupos)})")
    if (rec.cap["disponibles"] != rec.cap["cupos_semana"] - rec.cap["comprometidos"]).any():
        errores.append("capacidad_semana.csv: disponibles debe ser cupos_semana − comprometidos")
    return errores


# --- Todo junto ---

def verificar(envios=None, panel=None, rec=None):
    """Lista de errores de coherencia (vacía si todo cuadra)."""
    if not configuracion.BASE_DATOS.exists():
        return [f"No existe la base de datos {configuracion.BASE_DATOS}"]
    envios = leer_envios() if envios is None else envios
    errores = errores_de_base(envios)
    if errores:
        return errores
    min_servicios = configuracion.PERFILES["entrenamiento"]["min_servicios"]
    if panel is None:
        try:
            panel = leer_hoja(HOJA_PANEL)
        except ValueError:
            panel = None
    if panel is not None:
        errores += errores_de_panel(envios, panel)
    errores += errores_de_perfiles(configuracion.PERFILES, envios)
    catalogos = catalogos_desde_envios(envios, min_servicios)
    for ruta in archivos_solicitudes():
        errores += errores_de_solicitudes(ruta, catalogos)
    if rec is None and configuracion.modelo_al_dia():
        from src.motor import Recomendador
        rec = Recomendador.cargar(configuracion.DIR_M2 / configuracion.ARCHIVO_MODELO)
    errores += errores_de_modelo(rec, envios, min_servicios)
    return errores


def main():
    errores = verificar()
    for error in errores:
        print(error)
    print("OK: base, configuración, solicitudes y modelo son coherentes." if not errores
          else f"{len(errores)} errores.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
