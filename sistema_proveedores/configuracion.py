"""
Configuración compartida por los Modelos 1 y 2, sus scripts y el dashboard.

- Rutas: config/fuente_datos.yaml (dónde está la base, las solicitudes y el modelo).
- Pesos y umbrales: config/perfiles.yaml (se validan al cargar).
- Huella del modelo: dice si salidas_m2/modelo2.pkl se entrenó con la base, los
  parámetros de entrenamiento, el código del motor y las versiones de scikit-learn,
  pandas y numpy actuales (un .pkl de otra versión puede no abrir o dar otros números). Si algo cambió, el modelo guardado ya no es coherente con los datos y
  hay que reentrenar (el dashboard y modelo2_recomendador.py lo hacen solos).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import yaml

DIR_MOTOR = Path(__file__).resolve().parent
RAIZ = DIR_MOTOR.parent
DIR_CONFIG = RAIZ / "config"

FACTORES = ("precio", "tiempo", "fiabilidad")
COMPONENTES_FIABILIDAD = ("puntualidad", "magnitud_retraso", "integridad", "satisfaccion")
VELOCIDADES = ("same", "exp", "prio", "std")  # de más rápida a más lenta

ARCHIVO_MODELO = "modelo2.pkl"
ARCHIVO_HUELLA = "fuente_modelo.json"
# Código que define lo que se guarda en modelo2.pkl: si cambia, se reentrena.
FUENTES_DEL_MOTOR = ("modelo1_fiabilidad.py", "modelo2_recomendador.py")
TOLERANCIA_SUMA = 1e-9


def leer_yaml(ruta: Path) -> dict:
    with open(ruta, encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


# --------------------------------------------------------------------------
# Validación de config/perfiles.yaml
# --------------------------------------------------------------------------

def _errores_de_suma(nombre: str, pesos: dict, claves: tuple) -> list[str]:
    errores = []
    if set(pesos) != set(claves):
        errores.append(f"{nombre}: debe tener exactamente {', '.join(claves)} (tiene {', '.join(pesos)})")
    if any(v < 0 for v in pesos.values()):
        errores.append(f"{nombre}: los pesos no pueden ser negativos")
    total = sum(pesos.values())
    if abs(total - 1) > TOLERANCIA_SUMA:
        errores.append(f"{nombre}: los pesos suman {total:g} y deben sumar 1")
    return errores


def validar_perfiles(perfiles: dict) -> list[str]:
    """Lista de errores de config/perfiles.yaml (vacía si está bien)."""
    errores = []
    for contenedor, pesos in perfiles["pesos_por_contenedor"].items():
        errores += _errores_de_suma(f"pesos_por_contenedor.{contenedor}", pesos, FACTORES)
    extra = perfiles["extra_tiempo_por_velocidad"]
    if set(extra) != set(VELOCIDADES):
        errores.append(f"extra_tiempo_por_velocidad: debe tener {', '.join(VELOCIDADES)} (tiene {', '.join(extra)})")
    if any(v < 0 for v in extra.values()):
        errores.append("extra_tiempo_por_velocidad: los valores no pueden ser negativos")
    avisos = perfiles["avisos"]
    if not 0 < avisos["concentracion_max"] <= 1:
        errores.append("avisos.concentracion_max: debe estar entre 0 y 1")
    if not 0 <= avisos["prob_plazo_min"] <= 1:
        errores.append("avisos.prob_plazo_min: debe estar entre 0 y 1")
    entrenamiento = perfiles["entrenamiento"]
    if not isinstance(entrenamiento["min_servicios"], int) or entrenamiento["min_servicios"] < 1:
        errores.append("entrenamiento.min_servicios: debe ser un entero mayor o igual a 1")
    errores += _errores_de_suma("entrenamiento.pesos_fiabilidad", entrenamiento["pesos_fiabilidad"],
                                COMPONENTES_FIABILIDAD)
    return errores


def cargar_perfiles(ruta: Path = DIR_CONFIG / "perfiles.yaml") -> dict:
    perfiles = leer_yaml(ruta)
    errores = validar_perfiles(perfiles)
    if errores:
        raise ValueError(f"{ruta} no es válido:\n- " + "\n- ".join(errores))
    return perfiles


# --------------------------------------------------------------------------
# Rutas y parámetros (se leen una vez, al importar)
# --------------------------------------------------------------------------

FUENTE = leer_yaml(DIR_CONFIG / "fuente_datos.yaml")
PERFILES = cargar_perfiles()

BASE_DATOS = RAIZ / FUENTE["base_datos"]
HOJA_ENVIOS = FUENTE["hoja_envios"]
DIR_SOLICITUDES = RAIZ / FUENTE["dir_solicitudes"]
SOLICITUDES_PRUEBA = RAIZ / FUENTE["solicitudes_prueba"]
DIR_M2 = RAIZ / FUENTE["dir_modelo"]
AVISO_DATOS = FUENTE["aviso_datos"]
DIR_M1 = DIR_MOTOR / "salidas_m1"
DIR_VALIDACION = DIR_MOTOR / "salidas_validacion_m2"


# --------------------------------------------------------------------------
# Huella del modelo
# --------------------------------------------------------------------------

def _sha256_archivo(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def _sha256_codigo(ruta: Path) -> str:
    """Hash del código fuente sin depender de los saltos de línea (Windows o Unix)."""
    texto = Path(ruta).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(texto).hexdigest()


def versiones_librerias() -> dict:
    import numpy
    import pandas
    import sklearn

    return {"sklearn": sklearn.__version__, "pandas": pandas.__version__, "numpy": numpy.__version__}


def huella_entrenamiento(base: Path = BASE_DATOS, perfiles: dict | None = None) -> str:
    """Huella de todo lo que determina el modelo entrenado."""
    perfiles = perfiles or PERFILES
    partes = {
        "base": _sha256_archivo(base),
        "entrenamiento": perfiles["entrenamiento"],
        "motor": {f: _sha256_codigo(DIR_MOTOR / f) for f in FUENTES_DEL_MOTOR},
        "librerias": versiones_librerias(),
    }
    return hashlib.sha256(json.dumps(partes, sort_keys=True).encode()).hexdigest()


def escribir_huella(dir_modelo: Path, base: Path, envios) -> dict:
    """Guarda junto al modelo de qué datos salió (lo lee el dashboard)."""
    fechas = envios["fecha_orden"].astype(str)
    base = Path(base).resolve()
    info = {
        "huella": huella_entrenamiento(base),
        "base_datos": base.relative_to(RAIZ).as_posix() if base.is_relative_to(RAIZ) else str(base),
        "sha256_base": _sha256_archivo(base),
        "envios": int(len(envios)),
        "periodo": [fechas.min(), fechas.max()],
        "librerias": versiones_librerias(),
        "entrenado_en": datetime.now().isoformat(timespec="seconds"),
    }
    with open(Path(dir_modelo) / ARCHIVO_HUELLA, "w", encoding="utf-8") as archivo:
        json.dump(info, archivo, ensure_ascii=False, indent=2)
    return info


def leer_huella(dir_modelo: Path = DIR_M2) -> dict | None:
    ruta = Path(dir_modelo) / ARCHIVO_HUELLA
    if not ruta.exists():
        return None
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


def modelo_al_dia(dir_modelo: Path = DIR_M2, base: Path = BASE_DATOS) -> bool:
    """True si el modelo guardado corresponde a la base, la configuración y el código actuales."""
    info = leer_huella(dir_modelo)
    return ((Path(dir_modelo) / ARCHIVO_MODELO).exists() and info is not None
            and info.get("huella") == huella_entrenamiento(base))
