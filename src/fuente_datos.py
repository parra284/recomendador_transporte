"""Entrada y salida: lectura de la base de datos, del modelo entrenado y de los archivos de solicitudes.

Las rutas vienen de config/fuente_datos.yaml. El modelo guardado solo se usa si su
huella coincide con la base, la configuración y el código actuales; si no, se
reentrena con la base (unos 40 segundos) y se guarda con la nueva huella.
"""

from pathlib import Path

import pandas as pd

from src.motor import Recomendador, configuracion

PATRON_SOLICITUDES = "solicitudes*.csv"


def leer_envios(base=None):
    """Hoja de envíos de la base de datos (historial con el que se entrenan los modelos)."""
    return pd.read_excel(base or configuracion.BASE_DATOS, sheet_name=configuracion.HOJA_ENVIOS)


def leer_hoja(nombre, base=None):
    return pd.read_excel(base or configuracion.BASE_DATOS, sheet_name=nombre)


def leer_solicitudes_prueba():
    ruta = configuracion.SOLICITUDES_PRUEBA
    return pd.read_csv(ruta) if Path(ruta).exists() else None


def archivos_solicitudes(directorio=None):
    """Archivos de solicitudes que ofrece el dashboard (solicitudes*.csv)."""
    return sorted(Path(directorio or configuracion.DIR_SOLICITUDES).glob(PATRON_SOLICITUDES))


def entrenar_y_guardar(base=None, dir_modelo=None):
    """Entrena los Modelos 1 y 2 con la base y los guarda junto con su huella."""
    base = Path(base or configuracion.BASE_DATOS)
    rec = Recomendador.entrenar(leer_envios(base), leer_solicitudes_prueba())
    rec.guardar(dir_modelo or configuracion.DIR_M2, base=base)
    return Recomendador.cargar(Path(dir_modelo or configuracion.DIR_M2) / configuracion.ARCHIVO_MODELO)


def cargar_recomendador(entrenar_si_hace_falta=True):
    """(recomendador, se_reentreno). Usa el modelo guardado solo si está al día con la base."""
    if configuracion.modelo_al_dia():
        return Recomendador.cargar(configuracion.DIR_M2 / configuracion.ARCHIVO_MODELO), False
    if not entrenar_si_hace_falta:
        raise RuntimeError("El modelo guardado no corresponde a la base de datos actual. "
                           "Reentrene con: python -m src.entrenar_modelos")
    return entrenar_y_guardar(), True


def info_modelo():
    """Contenido de fuente_modelo.json: base, número de envíos, periodo y fecha de entrenamiento."""
    return configuracion.leer_huella()
