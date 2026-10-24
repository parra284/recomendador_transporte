"""Coherencia de punta a punta: la base, la configuración, el modelo guardado y las solicitudes
usan los mismos datos."""

import copy

import pandas as pd

from src.motor import configuracion
from src.solicitud import catalogos_desde_envios
from src.verificar_datos import verificar


def test_verificador_completo_sin_errores(envios_base, panel_base, rec):
    assert verificar(envios=envios_base, panel=panel_base, rec=rec) == []


# --- El modelo se entrenó con la base actual ---

def test_modelo_guardado_al_dia_con_la_base():
    assert configuracion.modelo_al_dia()


def test_huella_registra_la_base_actual():
    info = configuracion.leer_huella()
    assert configuracion.RAIZ / info["base_datos"] == configuracion.BASE_DATOS


def test_modelo_usa_exactamente_los_envios_de_la_base(rec, envios_base):
    assert len(rec.hist) == len(envios_base)
    assert list(rec.hist.id_envio) == list(envios_base.id_envio)
    columnas = ["proveedor", "precio_cop", "transito_real_h", "a_tiempo"]
    pd.testing.assert_frame_equal(rec.hist[columnas].reset_index(drop=True),
                                  envios_base[columnas].reset_index(drop=True))


def test_proveedores_del_modelo_son_los_de_la_base(rec, envios_base):
    assert sorted(rec.m1.proveedores) == sorted(envios_base.proveedor.unique())


def test_catalogo_del_modelo_coincide_con_la_base(rec, envios_base, catalogos):
    desde_base = catalogos_desde_envios(envios_base, configuracion.PERFILES["entrenamiento"]["min_servicios"])
    assert desde_base == catalogos
    assert rec.cat.contenedor_de_categoria == desde_base.contenedor_de_categoria
    assert set().union(*rec.cat.ciudades.values()) == set(desde_base.ciudades)


# --- La huella detecta cambios en lo que define el modelo ---

def test_huella_cambia_si_cambia_la_base(tmp_path):
    a, b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    a.write_bytes(b"base uno")
    b.write_bytes(b"base dos")
    assert configuracion.huella_entrenamiento(a) != configuracion.huella_entrenamiento(b)


def test_huella_cambia_si_cambia_un_parametro_de_entrenamiento():
    perfiles = copy.deepcopy(configuracion.PERFILES)
    perfiles["entrenamiento"]["min_servicios"] += 1
    assert configuracion.huella_entrenamiento(perfiles=perfiles) != configuracion.huella_entrenamiento()


def test_huella_no_cambia_con_los_pesos_de_recomendacion():
    perfiles = copy.deepcopy(configuracion.PERFILES)
    perfiles["pesos_por_contenedor"]["Dry"]["precio"] = 0.9
    assert configuracion.huella_entrenamiento(perfiles=perfiles) == configuracion.huella_entrenamiento()


# --- config/perfiles.yaml ---

def test_un_perfil_de_pesos_por_cada_contenedor_de_la_base(envios_base):
    assert set(configuracion.PERFILES["pesos_por_contenedor"]) == set(envios_base.tipo_contenedor)


def test_validar_perfiles_detecta_pesos_que_no_suman_uno():
    perfiles = copy.deepcopy(configuracion.PERFILES)
    perfiles["pesos_por_contenedor"]["Dry"]["precio"] = 0.9
    perfiles["entrenamiento"]["pesos_fiabilidad"]["puntualidad"] = 0.5
    errores = configuracion.validar_perfiles(perfiles)
    assert any("pesos_por_contenedor.Dry" in e for e in errores)
    assert any("pesos_fiabilidad" in e for e in errores)


def test_validar_perfiles_detecta_velocidad_faltante():
    perfiles = copy.deepcopy(configuracion.PERFILES)
    del perfiles["extra_tiempo_por_velocidad"]["same"]
    assert any("extra_tiempo_por_velocidad" in e for e in configuracion.validar_perfiles(perfiles))


def test_perfiles_del_repositorio_son_validos():
    assert configuracion.validar_perfiles(configuracion.PERFILES) == []
