"""Pruebas del verificador de datos."""

from src.verificar_datos import (
    errores_de_columnas,
    errores_de_condicion,
    errores_de_perfiles,
    verificar,
)


def test_datos_del_repositorio_son_validos():
    assert verificar() == []


def test_detecta_columnas_en_otro_orden():
    assert errores_de_columnas("x.csv", ["b", "a"], ["a", "b"])


def test_condicion_valida_con_comodin_al_final():
    assert errores_de_condicion("e.csv", 2, "origen=BUN-*") == []


def test_condicion_con_campo_desconocido():
    assert errores_de_condicion("e.csv", 2, "ciudad=BOG")


def test_condicion_sin_igual():
    assert errores_de_condicion("e.csv", 2, "origen")


def test_perfil_que_no_suma_uno():
    perfiles = {"perfiles": {"malo": {"precio": 0.5, "tiempo": 0.4}}}
    assert errores_de_perfiles(perfiles)
