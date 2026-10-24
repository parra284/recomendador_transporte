"""Contrato compartido (src/contrato.py): una sola recomendación del motor para dashboard, mapa y mundo 3D."""

import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import src.fuente_datos as fuente_datos
import src.pantalla_acceso as pantalla_acceso
import src.preferencias as preferencias
from src import contrato as C
from src import recomendacion as R
from src.sesion import EstadoSesion

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(scope="module")
def coordenadas():
    return C.cargar_coordenadas()


def contrato_de(rec, solicitudes, codigo, coordenadas=None):
    return C.construir(rec, R.recomendar(rec, solicitudes[codigo].como_dict()), coordenadas)


def test_recupera_una_solicitud_existente(rec, solicitudes, coordenadas):
    c = contrato_de(rec, solicitudes, "T-001", coordenadas)
    assert c["solicitud"]["id"] == "T-001"
    assert (c["solicitud"]["origen"], c["solicitud"]["destino"]) == ("Bogotá", "Medellín")
    assert c["estado"] == "ok" and c["recomendado"] == c["elegibles"][0]["proveedor"]


def test_mismo_resultado_que_la_tabla_del_dashboard(rec, solicitudes):
    r = R.recomendar(rec, solicitudes["T-001"].como_dict())
    c = C.construir(rec, r)
    tabla = R.tabla_top(r)
    assert [e["proveedor"] for e in c["elegibles"][:3]] == list(tabla["Proveedor"])
    assert [round(e["puntaje"], 1) for e in c["elegibles"][:3]] == list(tabla["Puntaje"])
    assert [R.formatear_cop(e["precio_cop"]) for e in c["elegibles"][:3]] == list(tabla["Precio estimado"])
    assert [R.formatear_horas(e["tiempo_esperado_h"]) for e in c["elegibles"][:3]] == list(tabla["Tiempo esperado"])


def test_excluidos_no_aparecen_como_elegibles(rec, solicitudes):
    c = contrato_de(rec, solicitudes, "T-002")        # Coordinadora no tiene cupos Reefer (caso de la demo)
    elegibles = {e["proveedor"] for e in c["elegibles"]}
    excluidos = {x["proveedor"] for x in c["excluidos"]}
    assert not elegibles & excluidos
    assert "Coordinadora" in excluidos


def test_sin_elegibles_no_inventa_recomendacion(rec, solicitudes):
    c = contrato_de(rec, solicitudes, "T-005")
    assert c["estado"] == "sin_elegibles" and c["recomendado"] is None and c["elegibles"] == []
    assert c["excluidos"] and c["alternativas"]


def test_campos_ausentes_quedan_vacios_y_marcados(rec, solicitudes):
    c = contrato_de(rec, solicitudes, "T-001")
    assert c["solicitud"]["volumen_m3"] is None and c["solicitud"]["tipo_vehiculo"] is None
    assert c["ruta"] == {"estado": None, "geometria": None}
    for campo in ("solicitud.volumen_m3", "solicitud.tipo_vehiculo", "ruta.estado", "ruta.geometria"):
        assert c["procedencia"][campo] == "no_disponible"
    assert c["procedencia"]["elegibles.cupos_disponibles"] == "simulado"


def test_estrellas_salen_de_la_calificacion_real_de_clientes(rec, solicitudes):
    c = contrato_de(rec, solicitudes, "T-001")
    top = c["elegibles"][0]
    hist = rec.hist[rec.hist.proveedor == top["proveedor"]]["satisfaccion_1a5"]
    assert top["calificacion_clientes"] == {"promedio": round(float(hist.mean()), 2), "n": int(hist.count())}


def test_geografia_usa_referencia_y_no_inventa_ciudades(rec, solicitudes, coordenadas):
    c = contrato_de(rec, solicitudes, "T-001", coordenadas)
    assert c["geografia"]["origen"] == coordenadas["ciudades"]["Bogotá"]
    assert c["geografia"]["trazado"] == "linea_recta" and c["geografia"]["verificado"] is False
    sin_bogota = {**coordenadas, "ciudades": {k: v for k, v in coordenadas["ciudades"].items() if k != "Bogotá"}}
    assert contrato_de(rec, solicitudes, "T-001", sin_bogota)["geografia"]["origen"] is None


def test_todas_las_ciudades_de_la_base_tienen_coordenadas_de_referencia(rec, coordenadas):
    ciudades_base = set(rec.hist.origen) | set(rec.hist.destino)
    assert ciudades_base <= set(coordenadas["ciudades"])


def test_contrato_es_json_y_se_guarda(rec, solicitudes, coordenadas, tmp_path):
    c = contrato_de(rec, solicitudes, "T-001", coordenadas)
    ruta = C.guardar(c, tmp_path / "c.json")
    assert json.loads(ruta.read_text(encoding="utf-8")) == json.loads(C.a_json(c))


def test_coordenadas_ilegibles_dan_error_explicito(tmp_path):
    malo = tmp_path / "ciudades.yaml"
    malo.write_text("ciudades: [esto no es un mapa", encoding="utf-8")
    with pytest.raises(C.ErrorContrato):
        C.cargar_coordenadas(malo)


# --- las vistas usan el mismo contrato ---

@pytest.fixture
def app_con(tmp_path, monkeypatch, rec):
    ruta = tmp_path / "preferencias.json"
    monkeypatch.setattr(preferencias, "RUTA_PREFERENCIAS", ruta)
    monkeypatch.setattr(pantalla_acceso, "exigir_acceso", lambda: True)

    def abrir(vista):
        preferencias.guardar_preferencia("ana", vista, ruta)
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["sesion"] = EstadoSesion(usuario="ana")
        at.run()
        assert not at.exception, at.exception
        return at
    return abrir


def test_mapa_y_dashboard_muestran_la_misma_recomendacion(app_con):
    publicado = C.RUTA_CONTRATO_ACTIVO
    dashboard = app_con("dashboard")
    recomendado = json.loads(publicado.read_text(encoding="utf-8"))["recomendado"]
    assert recomendado == dashboard.dataframe[0].value["Proveedor"].iat[0]
    mapa = app_con("mapa")
    textos_mapa = " ".join(str(e.value) for e in mapa.success)
    assert f"Recomendado: **{recomendado}**" in textos_mapa
    assert json.loads(publicado.read_text(encoding="utf-8"))["recomendado"] == recomendado


def test_cambiar_de_vista_conserva_la_solicitud(app_con):
    at = app_con("dashboard")
    at.selectbox(key="solicitud").set_value("T-003").run()
    at.sidebar.radio(key="config_vista").set_value("mapa")
    at.sidebar.button(key="config_guardar").click().run()
    assert not at.exception
    assert at.selectbox(key="solicitud").value == "T-003"
    assert json.loads(C.RUTA_CONTRATO_ACTIVO.read_text(encoding="utf-8"))["solicitud"]["id"] == "T-003"


def test_error_de_carga_se_informa_sin_datos_de_reemplazo(monkeypatch, rec):
    def falla():
        raise OSError("base no disponible")
    monkeypatch.setattr(pantalla_acceso, "exigir_acceso", lambda: True)
    monkeypatch.setattr(fuente_datos, "cargar_recomendador", falla)
    st.cache_resource.clear()
    try:
        at = AppTest.from_file(APP, default_timeout=180)
        at.run()
        assert not at.exception
        assert "No se pudieron cargar la base de datos o el modelo" in " ".join(str(e.value) for e in at.error)
        assert not at.dataframe and not at.tabs
    finally:
        st.cache_resource.clear()
