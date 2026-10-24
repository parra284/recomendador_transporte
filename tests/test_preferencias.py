"""Pruebas de la preferencia de interfaz por operador (src/preferencias.py)."""

import json

import pytest

from src.preferencias import (
    DASHBOARD,
    MAPA,
    MUNDO_VIRTUAL,
    ErrorPreferencias,
    cargar_preferencias,
    guardar_preferencia,
    preferencia_de,
)


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "seguridad" / "preferencias.json"


def test_operador_nuevo_no_tiene_preferencia(ruta):
    assert preferencia_de("ana", ruta) is None
    assert cargar_preferencias(ruta) == {}


def test_guardar_y_recuperar(ruta):
    guardar_preferencia("ana", DASHBOARD, ruta)
    assert preferencia_de("ana", ruta) == DASHBOARD


def test_cambiar_preferencia_reemplaza_la_anterior(ruta):
    guardar_preferencia("ana", MAPA, ruta)
    guardar_preferencia("ana", MUNDO_VIRTUAL, ruta)
    assert preferencia_de("ana", ruta) == MUNDO_VIRTUAL


def test_otro_operador_no_hereda_la_preferencia(ruta):
    guardar_preferencia("ana", MAPA, ruta)
    assert preferencia_de("luis", ruta) is None
    guardar_preferencia("luis", DASHBOARD, ruta)
    assert cargar_preferencias(ruta) == {"ana": MAPA, "luis": DASHBOARD}


def test_sin_usuario_no_hay_preferencia_ni_se_guarda(ruta):
    assert preferencia_de(None, ruta) is None
    with pytest.raises(ValueError):
        guardar_preferencia(None, DASHBOARD, ruta)


def test_vista_desconocida_se_rechaza(ruta):
    with pytest.raises(ValueError):
        guardar_preferencia("ana", "tabla", ruta)
    assert not ruta.exists()


def test_archivo_danado_da_error_explicito(ruta):
    ruta.parent.mkdir(parents=True)
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(ErrorPreferencias):
        preferencia_de("ana", ruta)


def test_error_al_guardar_no_finge_exito(tmp_path):
    bloqueo = tmp_path / "no_es_carpeta"
    bloqueo.write_text("x", encoding="utf-8")       # un archivo donde debería ir una carpeta
    with pytest.raises(ErrorPreferencias):
        guardar_preferencia("ana", DASHBOARD, bloqueo / "preferencias.json")


def test_valor_desconocido_en_el_archivo_se_ignora(ruta):
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({"version": 1, "operadores": {"ana": {"vista": "hologramas"}}}), encoding="utf-8")
    assert preferencia_de("ana", ruta) is None      # se le vuelve a ofrecer el onboarding


def test_solo_se_guarda_la_vista_y_la_fecha(ruta):
    guardar_preferencia("ana", DASHBOARD, ruta)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert set(datos["operadores"]["ana"]) == {"vista", "actualizado"}
    assert not ruta.with_suffix(".json.tmp").exists()
