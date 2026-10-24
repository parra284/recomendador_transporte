"""Pruebas de las restricciones duras."""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from src.restricciones import (
    ALERTA_CAPACIDAD_POR_CONFIRMAR,
    DatosProveedores,
    Proveedor,
    cargar_datos,
    evaluar_proveedores,
    formatear_miles,
    regla_capacidad,
    regla_cobertura,
    regla_documentos,
    regla_equipo,
    regla_extradimensionada,
    regla_imo,
    regla_peso,
    regla_poliza,
    regla_refrigerada,
    regla_tarifa,
)
from src.solicitud import Solicitud, cargar_solicitudes

DATOS = Path(__file__).resolve().parent.parent / "data"
FECHA = date(2026, 11, 4)


def solicitud(**cambios):
    base = dict(
        id_solicitud="T001", origen="BUN-SPRBUN", destino="BOG",
        fecha_cita=datetime(2026, 11, 4, 6, 0), tipo_contenedor="40HC", peso_bruto_t=22.5,
        imo=False, refrigerada=False, extradimensionada=False, valor_declarado_usd=85000,
    )
    base.update(cambios)
    return Solicitud(**base)


PROVEEDOR = Proveedor(
    id_proveedor="PX", nombre="Proveedor de prueba", equipos=("20DV", "40HC"), peso_max_t=32.0,
    permite_imo=False, permite_refrigerada=False, permite_extradimensionada=False,
    poliza_monto_usd=200000, poliza_vence=date(2027, 1, 1), habilitacion_vence=date(2027, 1, 1),
)

DATOS_MINIMOS = DatosProveedores(
    proveedores=(PROVEEDOR,),
    rutas=frozenset({("PX", "BUN-SPRBUN", "BOG")}),
    tarifas={("PX", "BUN-SPRBUN", "BOG", "40HC"): 4_000_000},
    capacidad={("PX", FECHA, "40HC"): ("confirmada", 2),
               ("PX", date(2026, 11, 5), "40HC"): ("sin_capacidad", 0)},
)


def aplicar(regla, sol=None, prov=PROVEEDOR):
    return regla(sol or solicitud(), prov, DATOS_MINIMOS)


# --- Una prueba por regla: caso que pasa y caso que no ---

def test_cobertura():
    assert aplicar(regla_cobertura).pasa
    r = aplicar(regla_cobertura, solicitud(destino="MDE"))
    assert not r.pasa and r.motivo == "No cubre la ruta BUN-SPRBUN → MDE"


def test_equipo():
    assert aplicar(regla_equipo).pasa
    r = aplicar(regla_equipo, solicitud(tipo_contenedor="40DV"))
    assert not r.pasa and "40DV" in r.motivo and "20DV, 40HC" in r.motivo


def test_peso():
    assert aplicar(regla_peso, solicitud(peso_bruto_t=30.48), replace(PROVEEDOR, peso_max_t=30.48)).pasa
    r = aplicar(regla_peso, solicitud(peso_bruto_t=30.0), replace(PROVEEDOR, peso_max_t=28.0))
    assert not r.pasa and r.motivo == "Peso máximo de 28 t no alcanza las 30 t de la carga"


def test_imo():
    sol_imo = solicitud(imo=True, clase_imo=3)
    assert aplicar(regla_imo, sol_imo, replace(PROVEEDOR, permite_imo=True)).pasa
    r = aplicar(regla_imo, sol_imo)
    assert not r.pasa and "IMO (clase 3)" in r.motivo


def test_refrigerada():
    sol_rf = solicitud(tipo_contenedor="40RF", refrigerada=True, temperatura_c=-18)
    assert aplicar(regla_refrigerada, sol_rf, replace(PROVEEDOR, permite_refrigerada=True)).pasa
    r = aplicar(regla_refrigerada, sol_rf)
    assert not r.pasa and "refrigerada (-18 °C)" in r.motivo


def test_extradimensionada():
    sol_ed = solicitud(tipo_contenedor="40FR", extradimensionada=True)
    assert aplicar(regla_extradimensionada, sol_ed, replace(PROVEEDOR, permite_extradimensionada=True)).pasa
    assert not aplicar(regla_extradimensionada, sol_ed).pasa


def test_poliza():
    assert aplicar(regla_poliza, solicitud(valor_declarado_usd=200000)).pasa
    r = aplicar(regla_poliza, solicitud(valor_declarado_usd=350000))
    assert not r.pasa and r.motivo == "Póliza de USD 200.000 no cubre USD 350.000"


def test_documentos_vigentes_el_mismo_dia_de_la_cita():
    prov = replace(PROVEEDOR, habilitacion_vence=FECHA, poliza_vence=FECHA)
    assert aplicar(regla_documentos, prov=prov).pasa


def test_documentos_habilitacion_vencida():
    r = aplicar(regla_documentos, prov=replace(PROVEEDOR, habilitacion_vence=date(2026, 11, 3)))
    assert not r.pasa and r.motivo == "Habilitación vencida el 2026-11-03 (cita el 2026-11-04)"


def test_documentos_poliza_vencida():
    r = aplicar(regla_documentos, prov=replace(PROVEEDOR, poliza_vence=date(2026, 10, 31)))
    assert not r.pasa and "Póliza vencida el 2026-10-31" in r.motivo


def test_tarifa():
    assert aplicar(regla_tarifa).pasa
    r = aplicar(regla_tarifa, solicitud(tipo_contenedor="20DV"))
    assert not r.pasa and r.motivo == "No tiene tarifa para BUN-SPRBUN → BOG en 20DV"


def test_capacidad_confirmada_pasa_sin_alerta():
    r = aplicar(regla_capacidad)
    assert r.pasa and r.alerta is None


def test_capacidad_sin_capacidad_no_pasa():
    r = aplicar(regla_capacidad, solicitud(fecha_cita=datetime(2026, 11, 5, 8, 0)))
    assert not r.pasa and r.motivo == "Sin capacidad para 40HC el 2026-11-05"


def test_capacidad_sin_fila_pasa_con_alerta():
    r = aplicar(regla_capacidad, solicitud(fecha_cita=datetime(2026, 11, 6, 8, 0)))
    assert r.pasa and r.alerta == ALERTA_CAPACIDAD_POR_CONFIRMAR


def test_formatear_miles():
    assert formatear_miles(4600000) == "4.600.000"


# --- Evaluación completa ---

def test_evaluacion_junta_todos_los_motivos_y_calcula_casi_elegibles():
    sol = solicitud(destino="MDE", tipo_contenedor="20DV", fecha_cita=datetime(2026, 11, 6, 8, 0))
    resultado = evaluar_proveedores(sol, DATOS_MINIMOS)
    assert resultado.elegibles == [] and resultado.casi_elegibles == []
    assert len(resultado.descartados[0].motivos) == 2  # cobertura y tarifa


def test_evaluacion_elegible_con_alerta():
    resultado = evaluar_proveedores(solicitud(fecha_cita=datetime(2026, 11, 6, 8, 0)), DATOS_MINIMOS)
    assert resultado.elegibles[0].alertas == [ALERTA_CAPACIDAD_POR_CONFIRMAR]


# --- Escenarios con los datos del proyecto ---

@pytest.fixture(scope="module")
def datos():
    return cargar_datos()


@pytest.fixture(scope="module")
def solicitudes():
    validas, _ = cargar_solicitudes(DATOS / "solicitudes_ejemplo.csv")
    return {s.id_solicitud: s for s in validas}


def ids(evaluaciones):
    return sorted(e.proveedor.id_proveedor for e in evaluaciones)


def test_corredor_bun_bog_40hc_4_nov(datos, solicitudes):
    sol = solicitudes["S001"]
    assert (sol.origen, sol.destino, sol.tipo_contenedor, sol.fecha_cita.date()) == \
        ("BUN-SPRBUN", "BOG", "40HC", FECHA)
    resultado = evaluar_proveedores(sol, datos)
    assert ids(resultado.elegibles) == ["P01", "P02", "P03"]
    p04 = next(e for e in resultado.descartados if e.proveedor.id_proveedor == "P04")
    assert p04.motivos == ["Sin capacidad para 40HC el 2026-11-04"]
    assert "P04" in ids(resultado.casi_elegibles)


def test_habilitacion_vencida_nunca_es_elegible(datos, solicitudes):
    p04 = next(p for p in datos.proveedores if p.id_proveedor == "P04")
    posteriores = [s for s in solicitudes.values() if s.fecha_cita.date() > p04.habilitacion_vence]
    assert posteriores, "debe haber solicitudes posteriores al vencimiento para que la prueba tenga sentido"
    for sol in posteriores:
        resultado = evaluar_proveedores(sol, datos)
        assert "P04" not in ids(resultado.elegibles)
        p04_eval = next(e for e in resultado.descartados if e.proveedor.id_proveedor == "P04")
        assert any(m.startswith("Habilitación vencida") for m in p04_eval.motivos)


@pytest.mark.parametrize("id_solicitud", ["S004", "S005"])
def test_solicitud_refrigerada_deja_elegible_a_p05(datos, solicitudes, id_solicitud):
    sol = solicitudes[id_solicitud]
    assert sol.refrigerada
    assert "P05" in ids(evaluar_proveedores(sol, datos).elegibles)
