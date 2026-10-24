"""Pruebas del modelo de solicitud, sus validaciones y la carga desde CSV."""

import pandas as pd
import pytest

from src.motor import configuracion
from src.solicitud import (
    COLUMNAS,
    Catalogos,
    cargar_solicitudes,
    catalogos_desde_envios,
    validar_fila,
    validar_filas,
)

CATALOGOS = Catalogos(
    ciudades=("Bogotá", "Cali", "Medellín"),
    rutas=frozenset({("Bogotá", "Cali"), ("Bogotá", "Medellín"), ("Cali", "Bogotá")}),
    contenedor_de_categoria={"Retail": "Dry", "Carne": "Reefer"},
    velocidades=("same", "exp", "prio", "std"),
    peso_max_kg={"Dry": 2000.0, "Reefer": 1200.0},
)
FILA = {
    "id_envio": "X-001", "fecha_orden": "2026-10-26", "origen": "Bogotá", "destino": "Cali",
    "categoria_carga": "Retail", "peso_por_bulto_kg": "12", "bultos_unidades": "3",
    "valor_declarado_cop": "1800000", "fragil": "0", "seguro": "1", "nivel_velocidad": "std",
    "plazo_h": "", "descripcion": "",
}


def validar(**cambios):
    return validar_fila({**FILA, **cambios}, 2, CATALOGOS)


def campos_con_error(**cambios):
    solicitud, errores = validar(**cambios)
    assert solicitud is None
    return [e.campo for e in errores]


# --- Fila válida ---

def test_fila_valida_con_tipos_correctos():
    solicitud, errores = validar()
    assert errores == []
    assert solicitud.bultos_unidades == 3 and solicitud.peso_por_bulto_kg == 12.0
    assert solicitud.fragil is False and solicitud.seguro is True
    assert solicitud.plazo_h is None and solicitud.descripcion is None


def test_como_dict_tiene_el_formato_del_modelo_2():
    solicitud, _ = validar(plazo_h="30", fragil="true")
    d = solicitud.como_dict()
    assert list(d) == COLUMNAS
    assert d["fecha_orden"] == "2026-10-26" and d["fragil"] == 1 and d["seguro"] == 1 and d["plazo_h"] == 30.0


# --- Una regla por prueba ---

def test_origen_que_no_esta_en_la_base():
    assert campos_con_error(origen="Buenaventura") == ["origen"]


def test_destino_que_no_esta_en_la_base():
    assert campos_con_error(destino="Quibdó") == ["destino"]


def test_ruta_sin_historial():
    solicitud, errores = validar(origen="Cali", destino="Medellín")
    assert [e.campo for e in errores] == ["destino"]
    assert errores[0].mensaje == "La ruta Cali → Medellín no tiene historial en la base."


def test_categoria_desconocida():
    assert campos_con_error(categoria_carga="Explosivos") == ["categoria_carga"]


def test_peso_total_mayor_al_maximo_del_contenedor():
    solicitud, errores = validar(categoria_carga="Carne", peso_por_bulto_kg="300", bultos_unidades="5")
    assert [e.campo for e in errores] == ["peso_por_bulto_kg"]
    assert "1.500 kg" in errores[0].mensaje and "Reefer (1.200 kg)" in errores[0].mensaje


def test_peso_total_igual_al_maximo_pasa():
    solicitud, errores = validar(categoria_carga="Carne", peso_por_bulto_kg="240", bultos_unidades="5")
    assert errores == [] and solicitud is not None


def test_peso_por_bulto_debe_ser_positivo():
    assert campos_con_error(peso_por_bulto_kg="0") == ["peso_por_bulto_kg"]


def test_bultos_al_menos_uno():
    assert campos_con_error(bultos_unidades="0") == ["bultos_unidades"]


def test_bultos_debe_ser_entero():
    assert campos_con_error(bultos_unidades="2.5") == ["bultos_unidades"]


def test_fecha_mal_escrita():
    solicitud, errores = validar(fecha_orden="26/10/2026")
    assert [e.campo for e in errores] == ["fecha_orden"]
    assert "AAAA-MM-DD" in errores[0].mensaje


def test_velocidad_desconocida():
    assert campos_con_error(nivel_velocidad="urgente") == ["nivel_velocidad"]


def test_valor_declarado_mayor_que_cero():
    assert campos_con_error(valor_declarado_cop="0") == ["valor_declarado_cop"]


@pytest.mark.parametrize("valor, esperado", [("1", True), ("0", False), ("sí", True), ("no", False), ("TRUE", True)])
def test_fragil_acepta_si_o_no(valor, esperado):
    solicitud, _ = validar(fragil=valor)
    assert solicitud.fragil is esperado


def test_fragil_con_texto_no_valido():
    assert campos_con_error(fragil="tal vez") == ["fragil"]


def test_plazo_debe_ser_positivo():
    assert campos_con_error(plazo_h="-5") == ["plazo_h"]


def test_codigo_obligatorio():
    solicitud, errores = validar(id_envio="")
    assert [e.campo for e in errores] == ["id_envio"]
    assert errores[0].mensaje == "El campo id_envio es obligatorio y está vacío."


def test_codigo_repetido_en_el_archivo():
    validas, errores = validar_filas([FILA, {**FILA, "destino": "Medellín"}], CATALOGOS)
    assert len(validas) == 1
    assert [(e.fila, e.campo) for e in errores] == [(3, "id_envio")]


# --- Catálogos derivados del historial ---

def test_catalogos_desde_envios_respetan_el_minimo_de_servicios():
    envios = pd.DataFrame({
        "proveedor": ["A"] * 5 + ["B"],
        "tipo_contenedor": ["Dry"] * 6,
        "peso_total_kg": [100, 100, 100, 100, 150, 900],
        "origen": ["Bogotá"] * 6,
        "destino": ["Cali"] * 6,
        "categoria_carga": ["Retail"] * 6,
    })
    # B movió 900 kg, pero solo una vez: no "ofrece" Dry y su peso no cuenta como máximo del mercado.
    assert catalogos_desde_envios(envios, min_servicios=5).peso_max_kg == {"Dry": 150}
    assert catalogos_desde_envios(envios, min_servicios=1).peso_max_kg == {"Dry": 900}


# --- Archivos de data/ contra la base real ---

def test_solicitudes_de_prueba_cargan_sin_errores(catalogos):
    validas, errores = cargar_solicitudes(configuracion.SOLICITUDES_PRUEBA, catalogos)
    assert len(validas) == 9 and errores == []


def test_solicitudes_invalidas_dan_un_error_por_fila(catalogos):
    validas, errores = cargar_solicitudes(configuracion.DIR_SOLICITUDES / "solicitudes_invalidas.csv", catalogos)
    assert validas == []
    assert [(e.id_envio, e.campo) for e in errores] == [
        ("I-001", "peso_por_bulto_kg"),
        ("I-002", "origen"),
        ("I-003", "categoria_carga"),
        ("I-004", "fecha_orden"),
        ("I-005", "nivel_velocidad"),
        ("I-006", "valor_declarado_cop"),
    ]
