"""Prueba de punta a punta del dashboard (Streamlit AppTest), sin la pantalla de acceso facial."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.pantalla_acceso as pantalla_acceso

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(monkeypatch, rec):
    # El ingreso (rostro o PIN) tiene sus propias pruebas en test_seguridad.py.
    monkeypatch.setattr(pantalla_acceso, "exigir_acceso", lambda: True)
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def textos(elementos):
    return " ".join(str(e.value) for e in elementos)


def test_muestra_la_fuente_de_datos(app):
    barra = textos(app.sidebar.markdown)
    assert "data/base_simulada_mensajeria.xlsx" in barra and "31.386 envíos" in barra


def test_recomienda_la_primera_solicitud(app):
    top = app.dataframe[0].value
    assert list(top["Proveedor"]) == ["Coordinadora", "Inter Rapidísimo", "Grupo TCC"]
    assert "Coordinadora queda primero" in textos(app.success)


def test_solicitud_sin_candidatos_muestra_alternativas(app):
    app.selectbox(key="solicitud").set_value("T-005").run()
    assert not app.exception
    assert "Ningún proveedor cumple" in textos(app.error)


def test_envio_historico(app):
    app.radio(key="origen").set_value("Envío histórico de la base").run()
    assert not app.exception
    assert "En su momento se eligió" in textos(app.success) + textos(app.info)


def test_archivo_de_solicitudes_invalidas(app):
    app.selectbox(key="archivo").set_value("solicitudes_invalidas.csv").run()
    assert not app.exception
    assert "6 fila(s) del archivo tienen errores" in textos(app.warning)


def test_reparto_del_lote(app):
    app.button(key="lote").click().run()
    assert not app.exception
    assert "Nadie supera sus cupos: sí" in textos(app.success)
