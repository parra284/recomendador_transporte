"""Pruebas de la recomendación con el Modelo 2 entrenado con la base."""

import math
import shutil

import pytest

from src import recomendacion as R
from src.motor import Recomendador, configuracion, modelo2_recomendador as m2

PROVEEDORES = {"4-72", "Coordinadora", "Envía", "Grupo TCC", "Inter Rapidísimo", "Servientrega"}


@pytest.fixture(scope="module")
def resultados(rec, solicitudes):
    return {codigo: R.recomendar(rec, s.como_dict()) for codigo, s in solicitudes.items()}


# --- Caso de referencia (mismo resultado que sistema_proveedores/salidas_m2/demo.txt) ---

def test_t001_recomienda_a_coordinadora(resultados):
    r = resultados["T-001"]
    assert list(r.top.proveedor) == ["Coordinadora", "Inter Rapidísimo", "Grupo TCC"]
    assert r.top.puntaje.iat[0] == pytest.approx(67.6, abs=0.1)


def test_top_maximo_tres_y_ordenado(resultados):
    for r in resultados.values():
        assert len(r.top) <= R.TAMANO_TOP
        if r.ranking.empty:
            continue
        assert list(r.ranking.puntaje) == sorted(r.ranking.puntaje, reverse=True)


def test_aportes_suman_el_puntaje(resultados):
    for r in resultados.values():
        for x in r.ranking.itertuples():
            assert x.aporte_precio + x.aporte_tiempo + x.aporte_fiabilidad == pytest.approx(x.puntaje)


def test_pesos_aplicados_suman_uno(resultados):
    for r in resultados.values():
        if r.pesos:
            assert sum(r.pesos.values()) == pytest.approx(1)


def test_cada_proveedor_es_candidato_o_excluido_con_motivo(resultados):
    for r in resultados.values():
        candidatos = set(r.ranking.proveedor) if not r.ranking.empty else set()
        assert candidatos | set(r.excluidos) == PROVEEDORES
        assert not candidatos & set(r.excluidos)
        assert all(r.excluidos.values())


# --- Reglas del Modelo 2 que se ven en el dashboard ---

def test_sin_cupos_excluye_al_mejor(resultados):
    r = resultados["T-002"]
    assert r.excluidos["Coordinadora"] == ["Sin cupos esta semana para Reefer"]
    assert r.recomendado == "Grupo TCC"


def test_peso_por_contenedor_excluye(resultados):
    motivos = resultados["T-009"].excluidos["Grupo TCC"]
    assert any(m.startswith("Peso 1,050 kg supera su máximo atendido en Reefer") for m in motivos)


def test_sin_candidatos_propone_alternativas(resultados):
    for codigo in ("T-005", "T-008"):
        r = resultados[codigo]
        assert r.ranking.empty and r.recomendado is None
        assert not R.tabla_alternativas(r).empty


def test_columna_en_plazo_solo_con_plazo(resultados):
    assert "En plazo" in R.tabla_top(resultados["T-002"]).columns
    assert "En plazo" not in R.tabla_top(resultados["T-001"]).columns


def test_tabla_de_aportes_coincide_con_el_ranking(resultados):
    r = resultados["T-001"]
    aportes = R.tabla_aportes(r)
    assert len(aportes) == len(r.top) * len(R.FACTORES)
    por_proveedor = aportes.groupby("Proveedor").Aporte.sum()
    for x in r.top.itertuples():
        assert por_proveedor[x.proveedor] == pytest.approx(x.puntaje, abs=0.01)


# --- Configuración: los pesos salen de config/perfiles.yaml ---

def test_el_motor_usa_los_pesos_del_yaml():
    assert m2.PESOS_PERFIL == configuracion.PERFILES["pesos_por_contenedor"]
    assert m2.EXTRA_TIEMPO_VELOCIDAD == configuracion.PERFILES["extra_tiempo_por_velocidad"]


def test_cambiar_un_peso_cambia_el_ranking(rec, solicitudes, monkeypatch):
    monkeypatch.setitem(m2.PESOS_PERFIL, "Dry", {"precio": 1.0, "tiempo": 0.0, "fiabilidad": 0.0})
    r = R.recomendar(rec, solicitudes["T-001"].como_dict())
    mas_barato = r.ranking.loc[r.ranking.precio_cop.idxmin(), "proveedor"]
    assert r.recomendado == mas_barato != "Coordinadora"


# --- Cupos: se leen de capacidad_semana.csv (igual en la recomendación y en el lote) ---

def test_editar_cupos_en_el_csv_cambia_la_recomendacion(tmp_path, solicitudes):
    shutil.copy(configuracion.DIR_M2 / "modelo2.pkl", tmp_path / "modelo2.pkl")
    cupos = (configuracion.DIR_M2 / "capacidad_semana.csv").read_text(encoding="utf-8-sig")
    lineas = [l if not l.startswith("Grupo TCC,Reefer,") else "Grupo TCC,Reefer,11,11,0"
              for l in cupos.splitlines()]
    (tmp_path / "capacidad_semana.csv").write_text("\n".join(lineas), encoding="utf-8-sig")
    r = R.recomendar(Recomendador.cargar(tmp_path / "modelo2.pkl"), solicitudes["T-002"].como_dict())
    assert r.excluidos["Grupo TCC"] == ["Sin cupos esta semana para Reefer"]
    assert r.recomendado != "Grupo TCC"


# --- Envíos históricos ---

def test_envio_historico_muestra_lo_que_paso(rec):
    r = R.recomendar(rec, R.solicitud_historica(rec, "S-000001"))
    h = R.comparacion_historica(r)
    assert h["proveedor"] == "Coordinadora"
    assert h["resultado"] == "llegó a tiempo"
    assert h["coincide"] == (r.recomendado == "Coordinadora")


def test_envio_historico_inexistente(rec):
    with pytest.raises(KeyError):
        R.solicitud_historica(rec, "S-999999")


def test_solicitud_nueva_no_tiene_comparacion_historica(resultados):
    assert R.comparacion_historica(resultados["T-001"]) is None


# --- Vista general y lote ---

def test_tabla_general_una_fila_por_solicitud(rec, solicitudes, resultados):
    tabla = R.tabla_general(rec, list(solicitudes.values())).set_index("Solicitud")
    assert list(tabla.index) == list(solicitudes)
    for codigo, r in resultados.items():
        assert tabla.loc[codigo, "Recomendado"] == (r.recomendado or "Sin candidatos")


def test_lote_respeta_cupos_y_tope(rec, solicitudes):
    lote = R.asignar_lote(rec, list(solicitudes.values()))
    assert lote["comprobaciones"]["ningun_proveedor_supera_cupos"]
    assert lote["comprobaciones"]["ningun_proveedor_supera_tope"]
    tope = math.floor(configuracion.PERFILES["avisos"]["concentracion_max"] * len(solicitudes))
    assert lote["detalle"].asignado.value_counts().max() <= tope
    asignado = lote["detalle"].set_index("codigo").asignado
    assert asignado["T-002"] != "Coordinadora"          # sin cupos de Reefer
    assert not any("--codigo" in m for m in lote["detalle"].motivo)
    tablas = R.tablas_lote(lote)
    assert list(tablas["detalle"].Solicitud) == list(solicitudes)
    assert (tablas["detalle"].set_index("Solicitud").loc["T-005", "Asignado"]) == "Sin asignar"


# --- Formato ---

def test_formato_colombiano():
    assert R.formatear_miles(4600000) == "4.600.000"
    assert R.formatear_cop(95168.4) == "$ 95.168"
    assert R.formatear_cambio(-8.4) == "-8 %"
    assert R.formatear_horas(5.3) == "5.3 h" and R.formatear_horas(34.4) == "34 h"
