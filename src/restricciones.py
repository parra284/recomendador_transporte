"""Restricciones duras: descartan a los proveedores que no pueden atender una solicitud."""

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

DIR_DATOS = Path(__file__).resolve().parent.parent / "data"
ALERTA_CAPACIDAD_POR_CONFIRMAR = "Capacidad por confirmar"


@dataclass(frozen=True)
class Proveedor:
    id_proveedor: str
    nombre: str
    equipos: tuple
    peso_max_t: float
    permite_imo: bool
    permite_refrigerada: bool
    permite_extradimensionada: bool
    poliza_monto_usd: float
    poliza_vence: date
    habilitacion_vence: date


@dataclass(frozen=True)
class DatosProveedores:
    proveedores: tuple                 # tupla de Proveedor
    rutas: frozenset                   # {(id_proveedor, origen, destino)}
    tarifas: dict                      # {(id_proveedor, origen, destino, tipo): precio_cop}
    capacidad: dict                    # {(id_proveedor, fecha, tipo): (estado, camiones_libres)}


@dataclass(frozen=True)
class ResultadoRegla:
    pasa: bool
    alerta: Optional[str] = None
    motivo: Optional[str] = None


@dataclass
class EvaluacionProveedor:
    proveedor: Proveedor
    alertas: list = field(default_factory=list)
    motivos: list = field(default_factory=list)


@dataclass
class ResultadoEvaluacion:
    elegibles: list        # EvaluacionProveedor sin motivos
    descartados: list      # EvaluacionProveedor con al menos un motivo
    casi_elegibles: list   # descartados que fallaron una sola regla


# --- Carga de datos ---

def _a_bool(texto):
    return texto.strip().lower() == "true"


def _leer_csv(ruta):
    with open(ruta, encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def proveedor_desde_fila(fila):
    return Proveedor(
        id_proveedor=fila["id_proveedor"],
        nombre=fila["nombre"],
        equipos=tuple(fila["equipos"].split("|")),
        peso_max_t=float(fila["peso_max_t"]),
        permite_imo=_a_bool(fila["permite_imo"]),
        permite_refrigerada=_a_bool(fila["permite_refrigerada"]),
        permite_extradimensionada=_a_bool(fila["permite_extradimensionada"]),
        poliza_monto_usd=float(fila["poliza_monto_usd"]),
        poliza_vence=date.fromisoformat(fila["poliza_vence"]),
        habilitacion_vence=date.fromisoformat(fila["habilitacion_vence"]),
    )


def cargar_datos(dir_datos=DIR_DATOS):
    """Lee proveedores, rutas, tarifas y capacidad desde los CSV de data/."""
    dir_datos = Path(dir_datos)
    proveedores = tuple(proveedor_desde_fila(f) for f in _leer_csv(dir_datos / "proveedores.csv"))
    rutas = frozenset((f["id_proveedor"], f["origen"], f["destino"])
                      for f in _leer_csv(dir_datos / "rutas_proveedor.csv"))
    tarifas = {(f["id_proveedor"], f["origen"], f["destino"], f["tipo_contenedor"]): float(f["precio_cop"])
               for f in _leer_csv(dir_datos / "tarifas.csv")}
    capacidad = {(f["id_proveedor"], date.fromisoformat(f["fecha"]), f["tipo_contenedor"]):
                 (f["estado"], int(f["camiones_libres"]))
                 for f in _leer_csv(dir_datos / "capacidad.csv")}
    return DatosProveedores(proveedores, rutas, tarifas, capacidad)


# --- Formato de mensajes ---

def formatear_miles(numero):
    """4600000 -> '4.600.000' (separador de miles colombiano)."""
    return f"{numero:,.0f}".replace(",", ".")


def _ruta(solicitud):
    return f"{solicitud.origen} → {solicitud.destino}"


def _ok():
    return ResultadoRegla(pasa=True)


def _falla(motivo):
    return ResultadoRegla(pasa=False, motivo=motivo)


# --- Reglas: (solicitud, proveedor, datos) -> ResultadoRegla ---

def regla_cobertura(solicitud, proveedor, datos):
    if (proveedor.id_proveedor, solicitud.origen, solicitud.destino) in datos.rutas:
        return _ok()
    return _falla(f"No cubre la ruta {_ruta(solicitud)}")


def regla_equipo(solicitud, proveedor, datos):
    if solicitud.tipo_contenedor in proveedor.equipos:
        return _ok()
    return _falla(f"No tiene equipo {solicitud.tipo_contenedor} (dispone de {', '.join(proveedor.equipos)})")


def regla_peso(solicitud, proveedor, datos):
    if solicitud.peso_bruto_t <= proveedor.peso_max_t:
        return _ok()
    return _falla(f"Peso máximo de {proveedor.peso_max_t:g} t no alcanza las {solicitud.peso_bruto_t:g} t de la carga")


def regla_imo(solicitud, proveedor, datos):
    if not solicitud.imo or proveedor.permite_imo:
        return _ok()
    return _falla(f"No está autorizado para carga IMO (clase {solicitud.clase_imo:g})")


def regla_refrigerada(solicitud, proveedor, datos):
    if not solicitud.refrigerada or proveedor.permite_refrigerada:
        return _ok()
    return _falla(f"No está autorizado para carga refrigerada ({solicitud.temperatura_c:g} °C)")


def regla_extradimensionada(solicitud, proveedor, datos):
    if not solicitud.extradimensionada or proveedor.permite_extradimensionada:
        return _ok()
    return _falla("No está autorizado para carga extradimensionada")


def regla_poliza(solicitud, proveedor, datos):
    if proveedor.poliza_monto_usd >= solicitud.valor_declarado_usd:
        return _ok()
    return _falla(f"Póliza de USD {formatear_miles(proveedor.poliza_monto_usd)} "
                  f"no cubre USD {formatear_miles(solicitud.valor_declarado_usd)}")


def regla_documentos(solicitud, proveedor, datos):
    """Póliza y habilitación deben estar vigentes el día de la cita (vencen al final del día)."""
    fecha = solicitud.fecha_cita.date()
    vencidos = [f"{nombre} vencida el {vence.isoformat()}"
                for nombre, vence in (("Habilitación", proveedor.habilitacion_vence),
                                      ("Póliza", proveedor.poliza_vence))
                if vence < fecha]
    if not vencidos:
        return _ok()
    return _falla(f"{' y '.join(vencidos)} (cita el {fecha.isoformat()})")


def regla_tarifa(solicitud, proveedor, datos):
    clave = (proveedor.id_proveedor, solicitud.origen, solicitud.destino, solicitud.tipo_contenedor)
    if clave in datos.tarifas:
        return _ok()
    return _falla(f"No tiene tarifa para {_ruta(solicitud)} en {solicitud.tipo_contenedor}")


def regla_capacidad(solicitud, proveedor, datos):
    fecha = solicitud.fecha_cita.date()
    registro = datos.capacidad.get((proveedor.id_proveedor, fecha, solicitud.tipo_contenedor))
    if registro is None:
        return ResultadoRegla(pasa=True, alerta=ALERTA_CAPACIDAD_POR_CONFIRMAR)
    estado, _ = registro
    if estado == "confirmada":
        return _ok()
    return _falla(f"Sin capacidad para {solicitud.tipo_contenedor} el {fecha.isoformat()}")


REGLAS = (
    regla_cobertura,
    regla_equipo,
    regla_peso,
    regla_imo,
    regla_refrigerada,
    regla_extradimensionada,
    regla_poliza,
    regla_documentos,
    regla_tarifa,
    regla_capacidad,
)


# --- Evaluación ---

def evaluar_proveedor(solicitud, proveedor, datos, reglas=REGLAS):
    """Aplica todas las reglas (sin cortar en la primera falla) y junta alertas y motivos."""
    resultados = [regla(solicitud, proveedor, datos) for regla in reglas]
    return EvaluacionProveedor(
        proveedor=proveedor,
        alertas=[r.alerta for r in resultados if r.alerta],
        motivos=[r.motivo for r in resultados if not r.pasa],
    )


def evaluar_proveedores(solicitud, datos, reglas=REGLAS):
    """Clasifica a todos los proveedores en elegibles, descartados y casi elegibles."""
    evaluaciones = [evaluar_proveedor(solicitud, p, datos, reglas) for p in datos.proveedores]
    elegibles = [e for e in evaluaciones if not e.motivos]
    descartados = [e for e in evaluaciones if e.motivos]
    casi_elegibles = [e for e in descartados if len(e.motivos) == 1]
    return ResultadoEvaluacion(elegibles, descartados, casi_elegibles)
