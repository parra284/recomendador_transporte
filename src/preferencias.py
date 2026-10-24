"""Preferencia de interfaz de cada operador (onboarding de personalización).

Se guarda en seguridad/preferencias.json (carpeta excluida de git), separada de
usuarios.json: aquí solo va el id del operador, la vista elegida y la fecha. Nunca
huellas, fotos ni PIN.

Formato:
    {"version": 1, "operadores": {"<id_usuario>": {"vista": "dashboard", "actualizado": "2026-10-24T10:00:00"}}}

Limitación (provisional): es un archivo local del equipo donde corre la app; no se
sincroniza entre equipos y no admite escrituras simultáneas desde varios procesos.
"""

import json
import os
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_PREFERENCIAS = RAIZ / "seguridad" / "preferencias.json"
VERSION = 1

# Identificadores estables de las tres experiencias (no cambiar: quedan guardados).
DASHBOARD, MAPA, MUNDO_VIRTUAL = "dashboard", "mapa", "mundo_virtual"
VISTAS = (DASHBOARD, MAPA, MUNDO_VIRTUAL)
VISTA_PREDETERMINADA = DASHBOARD


class ErrorPreferencias(Exception):
    """No se pudo leer o guardar el archivo de preferencias."""


def ruta_preferencias():
    """Ruta en uso (función para que las pruebas puedan redirigirla)."""
    return RUTA_PREFERENCIAS


def cargar_preferencias(ruta=None):
    """{id_usuario: vista}. Vacío si el archivo no existe; ErrorPreferencias si está dañado."""
    ruta = Path(ruta or ruta_preferencias())
    if not ruta.exists():
        return {}
    try:
        with open(ruta, encoding="utf-8") as archivo:
            datos = json.load(archivo)
        operadores = datos["operadores"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ErrorPreferencias(f"No se pudo leer el archivo de preferencias ({ruta.name}).") from exc
    # Un valor desconocido (p. ej. de una versión futura) se ignora: se vuelve a preguntar.
    return {u: p["vista"] for u, p in operadores.items() if isinstance(p, dict) and p.get("vista") in VISTAS}


def preferencia_de(usuario, ruta=None):
    """Vista guardada del operador, o None si no tiene. Propaga ErrorPreferencias."""
    if not usuario:
        return None
    return cargar_preferencias(ruta).get(usuario)


def guardar_preferencia(usuario, vista, ruta=None, ahora=None):
    """Guarda la vista del operador sin tocar la de los demás. Escritura atómica (archivo temporal + reemplazo)."""
    if not usuario:
        raise ValueError("Se necesita el id del operador para guardar su preferencia.")
    if vista not in VISTAS:
        raise ValueError(f"Vista desconocida: {vista!r}. Opciones: {', '.join(VISTAS)}.")
    ruta = Path(ruta or ruta_preferencias())
    try:
        operadores = {}
        if ruta.exists():
            with open(ruta, encoding="utf-8") as archivo:
                operadores = json.load(archivo).get("operadores", {})
        operadores[usuario] = {"vista": vista, "actualizado": (ahora or datetime.now()).isoformat(timespec="seconds")}
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(".json.tmp")
        with open(temporal, "w", encoding="utf-8") as archivo:
            json.dump({"version": VERSION, "operadores": operadores}, archivo, ensure_ascii=False, indent=2)
        os.replace(temporal, ruta)
    except (OSError, ValueError, AttributeError) as exc:
        raise ErrorPreferencias("No se pudo guardar la preferencia. Inténtelo de nuevo.") from exc
