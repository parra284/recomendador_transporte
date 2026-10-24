"""Pruebas del ranking y las explicaciones."""

from dataclasses import replace
from pathlib import Path

import pytest

from src.ranking import (
    MAX_PALABRAS_EXPLICACION,
    cargar_todo,
    clave_orden,
    explicar,
    recomendar,
)
from src.scoring import Confiabilidad, PuntajeProveedor
from src.solicitud import cargar_solicitudes

DATOS = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def datos():
    return cargar_todo()


@pytest.fixture(scope="module")
def solicitudes():
    validas, _ = cargar_solicitudes(DATOS / "solicitudes_ejemplo.csv")
    return {s.id_solicitud: s for s in validas}


def orden(recomendacion):
    return [o.id_proveedor for o in recomendacion.top]


def puntaje_falso(id_p, puntaje, confiabilidad, precio, aportes=None, mezclada=False, viajes=100):
    aportes = aportes or {"precio": puntaje, "tiempo": 0, "confiabilidad": 0, "etiquetas": 0}
    return PuntajeProveedor(
        id_proveedor=id_p, perfil="normal", puntaje=puntaje,
        crudos={"precio": precio, "tiempo": 24, "confiabilidad": confiabilidad, "etiquetas": []},
        normalizados={}, aportes=aportes, etiquetas=[], tiempo_desde_historial=True,
        confiabilidad=Confiabilidad(confiabilidad, viajes, int(viajes * confiabilidad), mezclada, "corredor"),
    )


# --- Casos pedidos ---

def test_s001_orden_normal(datos, solicitudes):
    assert orden(recomendar(solicitudes["S001"], datos)) == ["P01", "P02", "P03"]


def test_s001_orden_urgente(datos, solicitudes):
    urgente = solicitudes["S001"].model_copy(update={"prioridad": "urgente"})
    assert orden(recomendar(urgente, datos)) == ["P02", "P01", "P03"]


def test_sin_elegibles_top_vacio_y_casi_elegibles_con_motivo(datos, solicitudes):
    resultado = recomendar(solicitudes["S006"], datos)
    assert resultado.top == [] and resultado.elegibles == []
    assert [e.proveedor.id_proveedor for e in resultado.casi_elegibles] == ["P04"]
    assert resultado.casi_elegibles[0].motivos[0].startswith("Habilitación vencida")


# --- Estructura del resultado ---

def test_top_maximo_3_y_posiciones(datos, solicitudes):
    resultado = recomendar(solicitudes["S002"], datos)
    assert len(resultado.elegibles) == 4
    assert [o.posicion for o in resultado.top] == [1, 2, 3]


def test_alertas_de_capacidad_y_historial(datos, solicitudes):
    resultado = recomendar(solicitudes["S002"], datos)
    assert resultado.alertas["P06"] == ["Capacidad por confirmar", "Historial escaso (3 viajes)"]
    assert resultado.alertas["P01"] == []


# --- Desempate ---

def test_desempate_por_mayor_confiabilidad():
    a, b = puntaje_falso("A", 50, 0.90, 4e6), puntaje_falso("B", 50, 0.95, 5e6)
    assert [p.id_proveedor for p in sorted([a, b], key=clave_orden)] == ["B", "A"]


def test_desempate_por_menor_precio():
    a, b = puntaje_falso("A", 50, 0.90, 5e6), puntaje_falso("B", 50, 0.90, 4e6)
    assert [p.id_proveedor for p in sorted([a, b], key=clave_orden)] == ["B", "A"]


# --- Explicaciones ---

def test_explicaciones_s001(datos, solicitudes):
    explicaciones = {o.id_proveedor: o.explicacion for o in recomendar(solicitudes["S001"], datos).top}
    assert explicaciones["P01"] == "Buen balance de precio y puntualidad (92% a tiempo)"
    assert explicaciones["P02"] == "El más confiable y rápido del corredor"
    assert explicaciones["P03"] == "El más económico del corredor"


def test_explicacion_incluye_alertas():
    p = puntaje_falso("A", 50, 0.9, 4e6)
    otro = puntaje_falso("B", 40, 0.9, 5e6)
    assert explicar(p, [p, otro], ["Capacidad por confirmar"]) == \
        "El más económico del corredor; capacidad por confirmar"


def test_explicacion_unico_elegible():
    p = puntaje_falso("A", 50, 0.9, 4e6)
    assert explicar(p, [p], []) == "Único proveedor elegible"


def test_explicacion_maximo_20_palabras():
    p = puntaje_falso("A", 50, 0.9, 4e6)
    alertas = ["una alerta bastante larga con muchas palabras"] * 5
    assert len(explicar(p, [p, replace(p, id_proveedor="B")], alertas).split()) == MAX_PALABRAS_EXPLICACION


def test_todas_las_explicaciones_de_ejemplo_tienen_maximo_20_palabras(datos, solicitudes):
    for sol in solicitudes.values():
        for opcion in recomendar(sol, datos).elegibles:
            assert 0 < len(opcion.explicacion.split()) <= MAX_PALABRAS_EXPLICACION
