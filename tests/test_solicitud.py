"""Pruebas del modelo Solicitud y de la carga de solicitudes."""

from datetime import datetime
from pathlib import Path

import pytest

from src.solicitud import cargar_catalogos, cargar_solicitudes, validar_fila

DATOS = Path(__file__).resolve().parent.parent / "data"


def fila_valida(**cambios):
    """Fila de CSV válida (como texto) a la que se le aplican cambios."""
    fila = {
        "id_solicitud": "T001", "origen": "BUN-SPRBUN", "destino": "BOG",
        "fecha_cita": "2026-11-04T06:00", "tipo_contenedor": "40HC", "peso_bruto_t": "22.5",
        "imo": "false", "clase_imo": "", "refrigerada": "false", "temperatura_c": "",
        "extradimensionada": "false", "valor_declarado_usd": "85000",
        "modalidad_aduanera": "NACIONALIZADA", "prioridad": "normal", "observaciones": "",
    }
    fila.update(cambios)
    return fila


def validar(**cambios):
    return validar_fila(fila_valida(**cambios), 2, cargar_catalogos())


def campos_con_error(**cambios):
    _, errores = validar(**cambios)
    return [e.campo for e in errores]


# --- Archivos de ejemplo ---

def test_solicitudes_ejemplo_cargan_12_validas_sin_errores():
    validas, errores = cargar_solicitudes(DATOS / "solicitudes_ejemplo.csv")
    assert len(validas) == 12
    assert errores == []


def test_solicitudes_invalidas_un_error_por_fila_con_el_campo_correcto():
    validas, errores = cargar_solicitudes(DATOS / "solicitudes_invalidas.csv")
    assert validas == []
    assert [(e.fila, e.id_solicitud, e.campo) for e in errores] == [
        (2, "I001", "peso_bruto_t"),
        (3, "I002", "clase_imo"),
        (4, "I003", "temperatura_c"),
        (5, "I004", "origen"),
        (6, "I005", "fecha_cita"),
    ]
    assert all(e.mensaje for e in errores)


# --- Tipos ---

def test_convierte_tipos():
    solicitud, _ = validar(imo="true", clase_imo="3")
    assert solicitud.fecha_cita == datetime(2026, 11, 4, 6, 0)
    assert solicitud.imo is True and solicitud.refrigerada is False
    assert solicitud.peso_bruto_t == 22.5 and solicitud.clase_imo == 3.0
    assert solicitud.temperatura_c is None


def test_booleano_mal_escrito_da_mensaje_en_espanol():
    _, errores = validar(imo="quizas")
    assert errores[0].campo == "imo" and "true o false" in errores[0].mensaje


def test_campo_obligatorio_vacio():
    assert campos_con_error(destino="") == ["destino"]


# --- Catálogos ---

@pytest.mark.parametrize("campo", ["origen", "destino", "tipo_contenedor", "modalidad_aduanera", "prioridad"])
def test_valor_fuera_de_catalogo(campo):
    assert campos_con_error(**{campo: "NO_EXISTE"}) == [campo]


def test_modalidad_vacia_es_valida():
    solicitud, _ = validar(modalidad_aduanera="")
    assert solicitud.modalidad_aduanera is None


def test_prioridad_vacia_equivale_a_normal():
    solicitud, _ = validar(prioridad="")
    assert solicitud.prioridad == "normal"


def test_fecha_mal_escrita():
    _, errores = validar(fecha_cita="04/11/2026 6am")
    assert errores[0].campo == "fecha_cita" and "AAAA-MM-DDTHH:MM" in errores[0].mensaje


# --- Peso ---

def test_peso_en_el_maximo_es_valido():
    assert campos_con_error(peso_bruto_t="30.48") == []


def test_peso_sobre_el_maximo_del_tipo():
    assert campos_con_error(peso_bruto_t="30.5") == ["peso_bruto_t"]


def test_flat_rack_admite_mas_peso():
    assert campos_con_error(tipo_contenedor="40FR", peso_bruto_t="40", extradimensionada="true") == []


def test_peso_cero_no_es_valido():
    assert campos_con_error(peso_bruto_t="0") == ["peso_bruto_t"]


# --- IMO ---

def test_imo_sin_clase():
    assert campos_con_error(imo="true", clase_imo="") == ["clase_imo"]


@pytest.mark.parametrize("clase", ["0", "10"])
def test_imo_con_clase_fuera_de_rango(clase):
    assert campos_con_error(imo="true", clase_imo=clase) == ["clase_imo"]


def test_imo_con_subclase_valida():
    assert campos_con_error(imo="true", clase_imo="2.1") == []


# --- Refrigerada ---

def test_refrigerada_sin_temperatura():
    assert campos_con_error(tipo_contenedor="40RF", refrigerada="true", temperatura_c="") == ["temperatura_c"]


def test_refrigerada_en_contenedor_no_rf():
    assert campos_con_error(refrigerada="true", temperatura_c="4") == ["refrigerada"]


def test_refrigerada_valida():
    assert campos_con_error(tipo_contenedor="20RF", refrigerada="true", temperatura_c="-18") == []


# --- Extradimensionada ---

def test_extradimensionada_en_contenedor_seco():
    assert campos_con_error(extradimensionada="true") == ["extradimensionada"]


@pytest.mark.parametrize("tipo", ["40FR", "40OT"])
def test_extradimensionada_en_fr_u_ot(tipo):
    assert campos_con_error(tipo_contenedor=tipo, extradimensionada="true") == []


# --- Valor declarado ---

@pytest.mark.parametrize("valor", ["0", "-100"])
def test_valor_declarado_debe_ser_positivo(valor):
    assert campos_con_error(valor_declarado_usd=valor) == ["valor_declarado_usd"]
