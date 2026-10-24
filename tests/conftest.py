"""Fixtures compartidas: el modelo entrenado con la base y los catálogos derivados de ella."""

import pytest

from src.fuente_datos import cargar_recomendador, leer_envios, leer_hoja
from src.motor import configuracion
from src.solicitud import cargar_solicitudes, catalogos_desde_envios


@pytest.fixture(scope="session")
def rec():
    """El mismo recomendador que usa el dashboard (se reentrena si no está al día con la base)."""
    recomendador, _ = cargar_recomendador()
    return recomendador


@pytest.fixture(scope="session")
def catalogos(rec):
    return catalogos_desde_envios(rec.hist, configuracion.PERFILES["entrenamiento"]["min_servicios"])


@pytest.fixture(scope="session")
def solicitudes(catalogos):
    validas, _ = cargar_solicitudes(configuracion.SOLICITUDES_PRUEBA, catalogos)
    return {s.id_envio: s for s in validas}


@pytest.fixture(scope="session")
def envios_base():
    """Hoja de envíos leída directamente del archivo de la base (no del modelo)."""
    return leer_envios()


@pytest.fixture(scope="session")
def panel_base():
    return leer_hoja("Panel_Proveedor_Mes")
