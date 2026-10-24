"""Pruebas de las reglas del verificador de datos con tablas pequeñas."""

import pandas as pd

from src.motor import configuracion
from src.solicitud import COLUMNAS
from src.verificar_datos import (
    COLUMNAS_BASE,
    errores_de_base,
    errores_de_columnas,
    errores_de_panel,
    errores_de_perfiles,
)


def envios(**cambios):
    fila = {c: 1 for c in COLUMNAS_BASE}
    fila.update(id_envio="S-1", mes="2026-01", proveedor="A", tipo_contenedor="Dry", categoria_carga="Retail",
                nivel_velocidad="std", transito_real_h=10.0, transito_prometido_h=12.0, a_tiempo=1,
                satisfaccion_1a5=4)
    base = pd.DataFrame([fila, {**fila, "id_envio": "S-2"}])
    for columna, valores in cambios.items():
        base[columna] = valores
    return base


def test_base_correcta_sin_errores():
    assert errores_de_base(envios()) == []


def test_base_sin_columna():
    assert errores_de_base(envios().drop(columns="precio_cop")) == ["Base: faltan columnas precio_cop"]


def test_base_con_vacios():
    assert errores_de_base(envios(precio_cop=[1, None])) == ["Base: 1 vacíos en precio_cop"]


def test_base_con_codigos_repetidos():
    assert errores_de_base(envios(id_envio=["S-1", "S-1"])) == ["Base: 1 códigos id_envio repetidos"]


def test_base_con_a_tiempo_incoherente():
    errores = errores_de_base(envios(transito_real_h=[10.0, 20.0]))
    assert errores == ["Base: 1 envíos con a_tiempo distinto de (tránsito real <= prometido)"]


def test_base_con_categoria_en_dos_contenedores():
    errores = errores_de_base(envios(tipo_contenedor=["Dry", "Reefer"]))
    assert errores == ["Base: la categoría 'Retail' aparece en más de un contenedor"]


def panel_de(base):
    return pd.DataFrame([{"proveedor": "A", "mes": "2026-01", "pedidos": 2, "a_tiempo_pct": 1.0,
                          "satisfaccion": 4.0, "transito_h": 10.0}])


def test_panel_que_coincide():
    base = envios()
    assert errores_de_panel(base, panel_de(base)) == []


def test_panel_que_no_coincide():
    base = envios()
    panel = panel_de(base).assign(pedidos=3)
    assert errores_de_panel(base, panel) == ["Panel_Proveedor_Mes: pedidos difiere de los envíos hasta en 1"]


def test_perfil_faltante_para_un_contenedor_de_la_base():
    base = envios(tipo_contenedor=["Dry", "Tanque"], categoria_carga=["Retail", "Líquidos"])
    errores = errores_de_perfiles(configuracion.PERFILES, base)
    assert any("sin pesos para Tanque" in e for e in errores)


def test_columnas_de_solicitudes():
    assert errores_de_columnas("s.csv", COLUMNAS) == []
    assert errores_de_columnas("s.csv", list(reversed(COLUMNAS)))
