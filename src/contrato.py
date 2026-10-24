"""Contrato de datos compartido: UNA recomendación del motor → un dict/JSON que usan las tres vistas.

El dashboard, el mapa y el mundo 3D no recalculan nada: todos leen este contrato, construido a
partir del MISMO resultado de src.recomendacion.recomendar() (Modelo 2). Por eso la recomendación,
los costos y los tiempos no pueden contradecirse entre vistas.

Cada campo declara su procedencia:
  real         -> viene tal cual de la base de datos
  calculado    -> lo calculan los Modelos 1 y 2 a partir de la base
  simulado     -> todavía simulado (p. ej. cupos semanales)
  referencia   -> dato externo a la base (coordenadas aproximadas de config/ciudades.yaml)
  no_disponible -> la base no lo tiene; se deja en None, nunca se inventa

Uso por línea de comandos (exporta el contrato de una solicitud):
    python -m src.contrato --solicitud T-001 --salida contrato.json
"""

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from src import recomendacion as R
from src.motor import configuracion

VERSION = "1.0"
RAIZ = Path(__file__).resolve().parent.parent
RUTA_CIUDADES = RAIZ / "config" / "ciudades.yaml"
# Archivo con la solicitud activa del dashboard, servido por Streamlit en app/static/contrato/ (fuera de git).
RUTA_CONTRATO_ACTIVO = RAIZ / "static" / "contrato" / "solicitud_activa.json"

PROCEDENCIA = {
    "solicitud.origen": "real", "solicitud.destino": "real", "solicitud.categoria_carga": "real",
    "solicitud.peso_total_kg": "real", "solicitud.fecha_orden": "real", "solicitud.nivel_velocidad": "real",
    "solicitud.distancia_km": "calculado", "solicitud.zona": "calculado", "solicitud.tipo_contenedor": "calculado",
    "solicitud.volumen_m3": "no_disponible", "solicitud.tipo_vehiculo": "no_disponible",
    "ruta.estado": "no_disponible", "ruta.geometria": "no_disponible",
    "elegibles.precio_cop": "calculado", "elegibles.tiempo_esperado_h": "calculado",
    "elegibles.tiempo_prometido_h": "calculado", "elegibles.fiabilidad": "calculado",
    "elegibles.prob_a_tiempo_pct": "calculado", "elegibles.puntaje": "calculado",
    "elegibles.calificacion_clientes": "real", "elegibles.cupos_disponibles": "simulado",
    "elegibles.fortalezas": "calculado", "excluidos.motivos": "calculado",
    "geografia.coordenadas": "referencia",
}


class ErrorContrato(Exception):
    """No se pudo construir o leer el contrato (p. ej. archivo de coordenadas ilegible)."""


# --- utilidades ---

def _num(v, decimales=None):
    """Número JSON o None (NaN, None y valores no numéricos nunca se convierten en 0)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, decimales) if decimales is not None else f


def _lista(texto):
    if not isinstance(texto, str) or texto.strip() in ("", "—", "-"):
        return []
    return [p.strip() for p in texto.split(";") if p.strip()]


def cargar_coordenadas(ruta=RUTA_CIUDADES):
    """{"fuente", "verificado", "ciudades": {nombre: {"lat", "lon"}}}. ErrorContrato si el archivo no se puede leer."""
    try:
        with open(ruta, encoding="utf-8") as archivo:
            datos = yaml.safe_load(archivo)
        ciudades = {n: {"lat": float(c["lat"]), "lon": float(c["lon"])} for n, c in datos["ciudades"].items()}
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        raise ErrorContrato(f"No se pudieron leer las coordenadas de referencia ({Path(ruta).name}).") from exc
    return {"fuente": datos.get("fuente", ""), "verificado": bool(datos.get("verificado", False)), "ciudades": ciudades}


def calificaciones_clientes(rec):
    """{proveedor: (promedio 1-5, n)} desde la columna real satisfaccion_1a5 del historial."""
    h = rec.hist
    if "satisfaccion_1a5" not in h.columns:
        return {}
    g = h.groupby("proveedor")["satisfaccion_1a5"].agg(["mean", "count"])
    return {p: (round(float(f["mean"]), 2), int(f["count"])) for p, f in g.iterrows() if f["count"] > 0}


def _cupos(rec, proveedor, contenedor):
    c = rec.cap
    fila = c[(c.proveedor == proveedor) & (c.tipo_contenedor == contenedor)]
    return None if fila.empty else int(fila["disponibles"].iat[0])


def _fiabilidad_m1(rec):
    return {f.proveedor: f for f in rec.m1.ranking.itertuples()}


# --- contrato ---

def construir(rec, r, coordenadas=None, ahora=None):
    """Contrato de UNA recomendación ya calculada (r = src.recomendacion.recomendar(...))."""
    s = r.solicitud
    contenedor = s.get("tipo_contenedor")
    estrellas = calificaciones_clientes(rec)
    m1 = _fiabilidad_m1(rec)
    elegibles = []
    for i, x in enumerate(r.ranking.itertuples(), start=1):
        promedio, n = estrellas.get(x.proveedor, (None, 0))
        fila_m1 = m1.get(x.proveedor)
        elegibles.append({
            "posicion": i,
            "proveedor": x.proveedor,
            "puntaje": _num(x.puntaje, 2),
            "precio_cop": _num(x.precio_cop, 0),
            "precio_vs_mercado_pct": _num(x.precio_vs_mercado_pct, 1),
            "tiempo_esperado_h": _num(x.tiempo_esperado_h, 1),
            "tiempo_prometido_h": _num(x.tiempo_prometido_h, 1),
            "tiempo_vs_mercado_pct": _num(x.tiempo_vs_mercado_pct, 1),
            "fiabilidad": _num(x.fiabilidad, 1),
            "prob_a_tiempo_pct": _num(x.prob_a_tiempo, 1),
            "prob_plazo_pct": _num(100 * x.prob_plazo, 1) if r.con_plazo else None,
            "confianza": x.confianza,
            "tendencia": x.tendencia,
            "aportes": {f: _num(getattr(x, f"aporte_{f}"), 2) for f in R.FACTORES},
            "puntos": {f: _num(getattr(x, f"pts_{f}"), 1) for f in R.FACTORES},
            "calificacion_clientes": {"promedio": promedio, "n": n} if promedio is not None else None,
            "cupos_disponibles": _cupos(rec, x.proveedor, contenedor),
            "fortalezas": _lista(getattr(fila_m1, "fortalezas", None)),
            "debilidades": _lista(getattr(fila_m1, "debilidades", None)),
        })
    alternativas = [] if r.alternativas.empty else [
        {"proveedor": a.proveedor, "que_cambia": a.que_cambia, "puntaje": _num(a.puntaje, 2),
         "precio_cop": _num(a.precio_cop, 0), "tiempo_esperado_h": _num(a.tiempo_esperado_h, 1)}
        for a in r.alternativas.itertuples()]

    geografia = None
    if coordenadas is not None:
        c = coordenadas["ciudades"]
        geografia = {
            "origen": c.get(s["origen"]), "destino": c.get(s["destino"]),
            "trazado": "linea_recta",          # no hay geometría vial en la base
            "fuente": coordenadas["fuente"], "verificado": coordenadas["verificado"],
        }

    huella = configuracion.leer_huella() or {}
    return {
        "version": VERSION,
        "generado": (ahora or datetime.now()).isoformat(timespec="seconds"),
        "fuente": {"base_datos": huella.get("base_datos"), "envios": huella.get("envios"),
                   "periodo": huella.get("periodo"), "modelo_entrenado": huella.get("entrenado_en"),
                   "aviso": configuracion.AVISO_DATOS},
        "solicitud": {
            "id": s.get("id_envio"),
            "origen": s["origen"], "destino": s["destino"],
            "categoria_carga": s.get("categoria_carga"), "tipo_contenedor": contenedor,
            "tipo_carga": s.get("tipo_carga"),
            "peso_total_kg": _num(s.get("peso_total_kg"), 1), "bultos": _num(s.get("bultos_unidades"), 0),
            "valor_declarado_cop": _num(s.get("valor_declarado_cop"), 0),
            "nivel_velocidad": s.get("nivel_velocidad"),
            "plazo_h": _num(s.get("plazo_h"), 1),
            "fecha_orden": pd.Timestamp(s["fecha_orden"]).strftime("%Y-%m-%d") if s.get("fecha_orden") is not None else None,
            "distancia_km": _num(s.get("distancia_km"), 0), "zona": s.get("zona"),
            "volumen_m3": None, "tipo_vehiculo": None,   # no existen en la base
        },
        "ruta": {"estado": None, "geometria": None},      # no existen en la base
        "estado": "ok" if elegibles else "sin_elegibles",
        "recomendado": r.recomendado,
        "pesos": {f: _num(v, 4) for f, v in (r.pesos or {}).items()},
        "motivos_pesos": list(r.motivos_pesos),
        "mercado": {"precio_cop": _num(r.mercado_precio, 0), "tiempo_h": _num(r.mercado_tiempo, 1)},
        "elegibles": elegibles,
        "excluidos": [{"proveedor": p, "motivos": list(m)} for p, m in r.excluidos.items()],
        "alternativas": alternativas,
        "explicacion": r.explicacion,
        "avisos": list(r.avisos),
        "geografia": geografia,
        "procedencia": dict(PROCEDENCIA),
    }


def a_json(contrato):
    return json.dumps(contrato, ensure_ascii=False, indent=2)


def guardar(contrato, ruta=None):
    """Escribe el contrato (atómico). Devuelve la ruta. Lanza ErrorContrato si falla."""
    ruta = Path(ruta or RUTA_CONTRATO_ACTIVO)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(".json.tmp")
        temporal.write_text(a_json(contrato), encoding="utf-8")
        temporal.replace(ruta)
    except OSError as exc:
        raise ErrorContrato("No se pudo guardar el contrato de la solicitud activa.") from exc
    return ruta


def main(argv=None):
    from src.fuente_datos import cargar_recomendador
    from src.solicitud import cargar_solicitudes, catalogos_desde_envios

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solicitud", required=True, help="id del archivo de solicitudes (T-001) o envío histórico (S-000001)")
    parser.add_argument("--salida", type=Path, help="archivo JSON de salida (por defecto, la consola)")
    args = parser.parse_args(argv)
    rec, _ = cargar_recomendador()
    catalogos = catalogos_desde_envios(rec.hist, configuracion.PERFILES["entrenamiento"]["min_servicios"])
    validas, _ = cargar_solicitudes(configuracion.SOLICITUDES_PRUEBA, catalogos)
    por_id = {s.id_envio: s.como_dict() for s in validas}
    solicitud = por_id.get(args.solicitud) or R.solicitud_historica(rec, args.solicitud)
    contrato = construir(rec, R.recomendar(rec, solicitud), cargar_coordenadas())
    if args.salida:
        print(f"Contrato guardado en {guardar(contrato, args.salida)}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(a_json(contrato))
    return 0


if __name__ == "__main__":
    sys.exit(main())
