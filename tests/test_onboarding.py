"""Flujo real de la app (AppTest): ingreso → preferencia → onboarding si falta → vista elegida → Configuración.

El ingreso facial se sustituye por un operador ya autenticado (sus reglas se prueban en test_seguridad.py)
y las preferencias se guardan en una carpeta temporal.
"""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.pantalla_acceso as pantalla_acceso
import src.preferencias as preferencias
from src.sesion import EstadoSesion

APP = str(Path(__file__).resolve().parent.parent / "app.py")
TITULO = "¿Cómo prefieres explorar tu operación logística?"


@pytest.fixture
def ruta(tmp_path, monkeypatch, rec):
    ruta = tmp_path / "seguridad" / "preferencias.json"
    monkeypatch.setattr(preferencias, "RUTA_PREFERENCIAS", ruta)
    monkeypatch.setattr(pantalla_acceso, "exigir_acceso", lambda: True)
    return ruta


def abrir(usuario):
    """Una sesión nueva del navegador con el operador ya autenticado."""
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["sesion"] = EstadoSesion(usuario=usuario)
    at.run()
    assert not at.exception, at.exception
    return at


def textos(at):
    return " ".join(str(m.value) for m in at.markdown)


def en_onboarding(at):
    return TITULO in textos(at)


def en_dashboard(at):
    return len(at.tabs) == 4 and not en_onboarding(at)


def guardado(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))["operadores"] if ruta.exists() else {}


def test_operador_nuevo_ve_las_tres_opciones_y_no_puede_continuar_sin_elegir(ruta):
    at = abrir("ana")
    assert en_onboarding(at) and not at.tabs
    for vista in ("dashboard", "mapa", "mundo_virtual"):
        assert at.button(key=f"elegir_{vista}")
    assert at.button(key="onboarding_continuar").disabled


def test_elegir_dashboard_guarda_y_entra(ruta):
    at = abrir("ana")
    at.button(key="elegir_dashboard").click().run()
    assert not at.button(key="onboarding_continuar").disabled
    at.button(key="onboarding_continuar").click().run()
    assert not at.exception
    assert guardado(ruta)["ana"]["vista"] == "dashboard"
    assert en_dashboard(at)


def test_al_volver_a_entrar_va_directo_a_su_interfaz(ruta):
    preferencias.guardar_preferencia("ana", "dashboard", ruta)
    at = abrir("ana")                       # nueva sesión = cerró sesión y volvió a entrar
    assert en_dashboard(at)


def test_cambiar_la_seleccion_antes_de_continuar(ruta):
    at = abrir("ana")
    at.button(key="elegir_mapa").click().run()
    at.button(key="elegir_mundo_virtual").click().run()
    at.button(key="elegir_dashboard").click().run()
    at.button(key="onboarding_continuar").click().run()
    assert guardado(ruta)["ana"]["vista"] == "dashboard"


def test_posponer_no_guarda_y_se_vuelve_a_preguntar(ruta):
    at = abrir("ana")
    at.button(key="onboarding_posponer").click().run()
    assert en_dashboard(at)                 # entra a la vista predeterminada en esta sesión
    assert "ana" not in guardado(ruta)
    assert en_onboarding(abrir("ana"))      # la próxima vez se le vuelve a ofrecer


def test_otro_operador_no_hereda_la_preferencia(ruta):
    preferencias.guardar_preferencia("ana", "mapa", ruta)
    assert en_onboarding(abrir("luis"))


def test_vista_mapa_agrega_la_pestana_del_mapa(ruta):
    preferencias.guardar_preferencia("ana", "mapa", ruta)
    at = abrir("ana")
    assert len(at.tabs) == 5 and "Mapa" in at.tabs[0].label
    assert at.get("deck_gl_json_chart")                     # el mapa se dibuja


def test_preferencia_ilegible_muestra_error_y_vuelve_a_preguntar(ruta):
    ruta.parent.mkdir(parents=True)
    ruta.write_text("{dañado", encoding="utf-8")
    at = abrir("ana")
    assert en_onboarding(at)
    assert "No se pudo recuperar su preferencia" in " ".join(str(e.value) for e in at.error)


def test_error_al_guardar_no_finge_exito(ruta, monkeypatch, tmp_path):
    bloqueo = tmp_path / "archivo"
    bloqueo.write_text("x", encoding="utf-8")
    monkeypatch.setattr(preferencias, "RUTA_PREFERENCIAS", bloqueo / "preferencias.json")
    at = abrir("ana")
    at.button(key="elegir_dashboard").click().run()
    at.button(key="onboarding_continuar").click().run()
    assert en_onboarding(at)                # sigue en el onboarding: no se guardó
    assert "No se pudo guardar la preferencia" in " ".join(str(e.value) for e in at.error)


def test_configuracion_cambia_el_entorno_y_lo_guarda(ruta):
    preferencias.guardar_preferencia("ana", "dashboard", ruta)
    at = abrir("ana")
    at.sidebar.radio(key="config_vista").set_value("mundo_virtual")
    at.sidebar.button(key="config_guardar").click().run()
    assert not at.exception
    assert guardado(ruta)["ana"]["vista"] == "mundo_virtual"
    assert "todavía no muestra estos datos" in textos(at)
    assert guardado(ruta).keys() == {"ana"}  # no crea preferencias para nadie más
