"""Pruebas de la puntuación de proveedores."""

from pathlib import Path

import pytest
import yaml

from src.restricciones import cargar_datos, evaluar_proveedores
from src.scoring import (
    RUTA_PERFILES,
    Etiqueta,
    cargar_config,
    cargar_datos_scoring,
    condicion_coincide,
    normalizar_confiabilidad,
    normalizar_etiquetas,
    normalizar_menor_es_mejor,
    promedio_general_a_tiempo,
    puntuar,
    validar_perfiles,
)
from src.solicitud import cargar_solicitudes

DATOS = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def datos():
    return cargar_datos_scoring()


@pytest.fixture(scope="module")
def config():
    return cargar_config()


@pytest.fixture(scope="module")
def s001():
    validas, _ = cargar_solicitudes(DATOS / "solicitudes_ejemplo.csv")
    return next(s for s in validas if s.id_solicitud == "S001")


@pytest.fixture(scope="module")
def elegibles_s001(s001):
    resultado = evaluar_proveedores(s001, cargar_datos())
    return [e.proveedor.id_proveedor for e in resultado.elegibles]


def puntajes(resultados):
    return {r.id_proveedor: r.puntaje for r in resultados}


# --- Casos de referencia (S001: BUN-SPRBUN -> BOG, 40HC, 2026-11-04) ---

def test_s001_perfil_normal(s001, elegibles_s001, datos, config):
    resultado = puntajes(puntuar(s001, elegibles_s001, datos, config))
    assert resultado == pytest.approx({"P01": 59.33, "P02": 56.00, "P03": 47.50}, abs=0.01)


def test_s001_perfil_urgente(s001, elegibles_s001, datos, config):
    urgente = s001.model_copy(update={"prioridad": "urgente"})
    resultado = puntajes(puntuar(urgente, elegibles_s001, datos, config))
    assert resultado == pytest.approx({"P01": 56.00, "P02": 76.00, "P03": 27.50}, abs=0.01)


def test_s001_resultado_ordenado_y_aportes_suman_puntaje(s001, elegibles_s001, datos, config):
    resultados = puntuar(s001, elegibles_s001, datos, config)
    assert [r.id_proveedor for r in resultados] == ["P01", "P02", "P03"]
    for r in resultados:
        assert sum(r.aportes.values()) == pytest.approx(r.puntaje)


def test_s001_valores_crudos(s001, elegibles_s001, datos, config):
    r = {x.id_proveedor: x for x in puntuar(s001, elegibles_s001, datos, config)}
    assert r["P01"].crudos["precio"] == 4_600_000
    assert (r["P01"].crudos["tiempo"], r["P02"].crudos["tiempo"], r["P03"].crudos["tiempo"]) == (24, 20, 28)
    assert r["P02"].crudos["confiabilidad"] == pytest.approx(0.97)
    assert [e.etiqueta for e in r["P01"].etiquetas] == []
    assert [e.etiqueta for e in r["P02"].etiquetas] == ["puntualidad_bogota"]
    assert [e.etiqueta for e in r["P03"].etiquetas] == ["congestion_buenaventura"]


# --- Casos especiales ---

def test_un_solo_elegible_obtiene_1_en_precio_y_tiempo(s001, datos, config):
    [r] = puntuar(s001, ["P03"], datos, config)
    assert r.normalizados["precio"] == 1 and r.normalizados["tiempo"] == 1


def test_proveedor_con_3_viajes_usa_confiabilidad_mezclada_y_horas_base(s001, datos, config):
    [r] = puntuar(s001, ["P06"], datos, config)
    conf = r.confiabilidad
    assert conf.viajes == 3 and conf.mezclada and conf.alcance == "historial_completo"
    promedio = promedio_general_a_tiempo(datos.viajes)
    esperado = (conf.aciertos + 20 * promedio) / (3 + 20)
    assert r.crudos["confiabilidad"] == pytest.approx(esperado)
    assert not r.tiempo_desde_historial
    assert r.crudos["tiempo"] == datos.tiempos_base[("BUN-SPRBUN", "BOG")]


def test_cambiar_peso_en_yaml_cambia_puntaje(tmp_path, s001, elegibles_s001, datos, config):
    contenido = yaml.safe_load(RUTA_PERFILES.read_text(encoding="utf-8"))
    contenido["perfiles"]["normal"].update(precio=0.55, confiabilidad=0.15)
    ruta = tmp_path / "perfiles.yaml"
    ruta.write_text(yaml.safe_dump(contenido), encoding="utf-8")

    original = puntajes(puntuar(s001, elegibles_s001, datos, config))
    modificado = puntajes(puntuar(s001, elegibles_s001, datos, cargar_config(ruta)))
    assert modificado != pytest.approx(original)
    assert modificado["P03"] == pytest.approx(62.5)  # 55*1 + 15*0 + 15*0.25 + 15*0.25


def test_sin_elegibles_devuelve_lista_vacia(s001, datos, config):
    assert puntuar(s001, [], datos, config) == []


def test_prioridad_sin_perfil(s001, datos, config):
    with pytest.raises(ValueError):
        puntuar(s001.model_copy(update={"prioridad": "otra"}), ["P01"], datos, config)


# --- Configuración ---

def test_perfiles_del_proyecto_suman_1(config):
    assert set(config.perfiles) == {"normal", "urgente", "economica", "alto_valor"}


def test_perfil_que_no_suma_1_es_rechazado():
    with pytest.raises(ValueError, match="suman"):
        validar_perfiles({"malo": {"precio": 0.5, "tiempo": 0.2, "confiabilidad": 0.2, "etiquetas": 0.2}})


def test_perfil_sin_variable_es_rechazado():
    with pytest.raises(ValueError, match="etiquetas"):
        validar_perfiles({"malo": {"precio": 0.5, "tiempo": 0.2, "confiabilidad": 0.3}})


# --- Normalización ---

def test_normalizar_menor_es_mejor():
    assert normalizar_menor_es_mejor(20, [20, 24, 28]) == 1
    assert normalizar_menor_es_mejor(28, [20, 24, 28]) == 0
    assert normalizar_menor_es_mejor(24, [20, 24, 28]) == 0.5
    assert normalizar_menor_es_mejor(5, [5, 5]) == 1


@pytest.mark.parametrize("valor, esperado", [(0.92, 0.6), (0.80, 0.0), (0.70, 0.0), (1.0, 1.0)])
def test_normalizar_confiabilidad(valor, esperado):
    assert normalizar_confiabilidad(valor, 0.80) == pytest.approx(esperado)


def _etiqueta(tipo):
    return Etiqueta("PX", tipo, "x", "origen=*")


def test_normalizar_etiquetas():
    assert normalizar_etiquetas([], 0.5, 0.25) == 0.5
    assert normalizar_etiquetas([_etiqueta("fortaleza")], 0.5, 0.25) == 0.75
    assert normalizar_etiquetas([_etiqueta("debilidad")], 0.5, 0.25) == 0.25


def test_normalizar_etiquetas_limitado_a_0_1():
    assert normalizar_etiquetas([_etiqueta("fortaleza")] * 3, 0.5, 0.25) == 1
    assert normalizar_etiquetas([_etiqueta("debilidad")] * 3, 0.5, 0.25) == 0


# --- Coincidencia de etiquetas ---

@pytest.mark.parametrize("condicion, coincide", [
    ("destino=BOG", True),
    ("destino=MDE", False),
    ("origen=BUN-*", True),
    ("origen=CTG-*", False),
    ("origen=*", True),
    ("refrigerada=false", True),
    ("refrigerada=true", False),
    ("prioridad=normal", True),
])
def test_condicion_coincide(s001, condicion, coincide):
    assert condicion_coincide(condicion, s001) is coincide
