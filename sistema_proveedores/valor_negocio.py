"""
VALOR DE NEGOCIO — ahorro, puntualidad y tiempo del operario por año
====================================================================

Parte de la prueba retrospectiva de validar_modelo2.py (entrenado hasta
2026-03-31, probado en abr-sep 2026) y la repite como se operaría de verdad:
cada SEMANA de prueba es un lote que se reparte con asignacion_lote
(programación entera), con cupos semanales y el tope del 35 % por proveedor.
Los cupos semanales se calculan SOLO con el entrenamiento (percentil 90 del
volumen semanal × 1,15, la misma regla de capacidad_simulada).

Cada cifra de salida es una de dos cosas:
  [VALIDACIÓN]  sale de la prueba retrospectiva;
  [SUPUESTO]    se declara aquí y se puede cambiar por argumento.

Uso:
    python valor_negocio.py
    python valor_negocio.py --envios-mes 1300 --adopcion-esperada 0.8 --adopcion-conservadora 0.5
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from asignacion_lote import _resolver
from configuracion import BASE_DATOS, DIR_VALIDACION, HOJA_ENVIOS
from modelo2_recomendador import CONCENTRACION_MAX
from validar_modelo2 import CORTE, RESULTADOS, entrenar_hasta_corte, puntuar_todos


def cupos_semanales(train: pd.DataFrame, catalogo) -> dict:
    sem = pd.to_datetime(train.fecha_orden).dt.to_period("W")
    vol = train.assign(semana=sem).groupby(["proveedor", "tipo_contenedor", "semana"]).size()
    return {(p, c): int(math.ceil(s.quantile(0.9) * 1.15))
            for (p, c), s in vol.groupby(level=[0, 1]) if c in catalogo.contenedores[p]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default=str(BASE_DATOS))
    ap.add_argument("--salida", default=str(DIR_VALIDACION))
    ap.add_argument("--envios-mes", type=float, default=1300)
    ap.add_argument("--min-manual", type=float, default=5.0)
    ap.add_argument("--min-sistema", type=float, default=1.0)
    ap.add_argument("--costo-hora-operario", type=float, default=25_000)
    ap.add_argument("--horas-ano-persona", type=float, default=2_000)
    ap.add_argument("--adopcion-esperada", type=float, default=0.80)
    ap.add_argument("--adopcion-conservadora", type=float, default=0.50)
    ap.add_argument("--realizacion-conservadora", type=float, default=0.50,
                    help="parte de la mejora estimada que se materializa en el escenario conservador")
    a = ap.parse_args()

    env = pd.read_excel(a.datos, sheet_name=HOJA_ENVIOS)
    rec, train = entrenar_hasta_corte(env)
    test = env[pd.to_datetime(env.fecha_orden) > CORTE].copy()
    sol = test.drop(columns=RESULTADOS)
    pts = puntuar_todos(rec, sol)
    elegido = test.set_index("id_envio").proveedor
    semana = test.set_index("id_envio").fecha_orden.pipe(pd.to_datetime).dt.to_period("W")
    cupos = cupos_semanales(train, rec.cat)

    # ---- asignación semana a semana con restricciones --------------------
    cand = pts[pts.elegible].rename(columns={"id_envio": "codigo"})[["codigo", "proveedor", "tipo_contenedor", "puntaje"]]
    asign, sin_asignar, semanas = {}, 0, 0
    for s, ids in semana.groupby(semana):
        c = cand[cand.codigo.isin(ids.index)]
        if c.empty:
            continue
        n = ids.size
        tope = math.floor(CONCENTRACION_MAX * n + 1e-9)
        with contextlib.redirect_stdout(io.StringIO()):
            r, metodo = _resolver(c, cupos, tope, "auto")
        asign.update(r)
        sin_asignar += sum(v is None for v in r.values())
        semanas += 1
    top_libre = pts[pts.elegible].loc[pts[pts.elegible].groupby("id_envio").puntaje.idxmax()].set_index("id_envio").proveedor

    idx = pts.set_index(["id_envio", "proveedor"])

    def comparar(recomendado: pd.Series, nombre: str) -> dict:
        ids = [i for i, p in recomendado.items() if pd.notna(p)]  # sin asignar: None (o NaN en pandas 3)
        r_ = [(i, recomendado[i]) for i in ids]
        e_ = [(i, elegido[i]) for i in ids]
        precio_r, precio_e = idx.loc[r_, "precio_cop"].to_numpy(), idx.loc[e_, "precio_cop"].to_numpy()
        pat_r, pat_e = idx.loc[r_, "prob_a_tiempo"].to_numpy(), idx.loc[e_, "prob_a_tiempo"].to_numpy()
        t_r, t_e = idx.loc[r_, "tiempo_esperado_h"].to_numpy(), idx.loc[e_, "tiempo_esperado_h"].to_numpy()
        reparto = recomendado.loc[ids].value_counts(normalize=True).mul(100).round(1).to_dict()
        return {"escenario_modelo": nombre, "envios": len(ids),
                "coincidencia_pct": 100 * float(np.mean([recomendado[i] == elegido[i] for i in ids])),
                "costo_total_elegido_cop": float(precio_e.sum()), "costo_total_recomendado_cop": float(precio_r.sum()),
                "dif_costo_total_pct": 100 * float(precio_r.sum() / precio_e.sum() - 1),
                "dif_costo_medio_cop": float((precio_r - precio_e).mean()),
                "dif_prob_a_tiempo_pts": float((pat_r - pat_e).mean()),
                "prob_a_tiempo_elegido_pct": float(pat_e.mean()), "prob_a_tiempo_recomendado_pct": float(pat_r.mean()),
                "dif_tiempo_h": float((t_r - t_e).mean()), "reparto_pct": reparto,
                "max_cuota_pct": max(reparto.values())}

    libre = comparar(top_libre, "Sin restricciones (techo teórico)")
    con = comparar(pd.Series(asign), "Con cupos semanales y tope 35 % (operación)")

    # ---- tiempo por solicitud --------------------------------------------
    muestra = sol.sample(40, random_state=1).to_dict("records")
    rec.recomendar(dict(muestra[0]))  # calienta
    t0 = time.perf_counter()
    for s in muestra:
        rec.recomendar(dict(s))
    seg_por_solicitud = (time.perf_counter() - t0) / len(muestra)

    # ---- valor anual ------------------------------------------------------
    envios_ano = a.envios_mes * 12
    precio_medio = float(test.precio_cop.mean())              # [VALIDACIÓN] precio real medio abr-sep 2026
    gasto_ano = envios_ano * precio_medio
    min_ahorrados = a.min_manual - a.min_sistema

    def escenario(nombre, adopcion, realizacion):
        dif_costo = con["dif_costo_total_pct"] / 100 * realizacion
        dif_pat = con["dif_prob_a_tiempo_pts"] * realizacion
        envios_sistema = envios_ano * adopcion
        horas = envios_sistema * min_ahorrados / 60
        return {"escenario": nombre, "adopcion": adopcion, "realizacion": realizacion,
                "envios_con_sistema_ano": envios_sistema,
                "ahorro_flete_cop_ano": -dif_costo * gasto_ano * adopcion,
                "ahorro_flete_pct_gasto": -100 * dif_costo * adopcion,
                "mejora_puntualidad_pts": dif_pat * adopcion,
                "envios_adicionales_a_tiempo_ano": dif_pat / 100 * envios_sistema,
                "horas_operario_ahorradas_ano": horas,
                "personas_equivalentes": horas / a.horas_ano_persona,
                "valor_tiempo_operario_cop_ano": horas * a.costo_hora_operario}

    escenarios = [escenario("Conservador", a.adopcion_conservadora, a.realizacion_conservadora),
                  escenario("Esperado", a.adopcion_esperada, 1.0)]
    out = {
        "fuente": {"corte": str(CORTE.date()), "envios_prueba": len(test), "semanas_prueba": semanas,
                   "metodo_lote": metodo, "sin_asignar_con_restricciones": sin_asignar},
        "validacion_sin_restricciones": libre, "validacion_con_restricciones": con,
        "segundos_por_solicitud": seg_por_solicitud,
        "precio_medio_envio_cop": precio_medio,
        "supuestos": {"envios_mes": a.envios_mes, "envios_ano": envios_ano, "gasto_flete_ano_cop": gasto_ano,
                      "min_manual": a.min_manual, "min_sistema": a.min_sistema,
                      "costo_hora_operario_cop": a.costo_hora_operario, "horas_ano_persona": a.horas_ano_persona,
                      "adopcion_esperada": a.adopcion_esperada, "adopcion_conservadora": a.adopcion_conservadora,
                      "realizacion_conservadora": a.realizacion_conservadora},
        "escenarios": escenarios,
    }
    Path(a.salida).mkdir(exist_ok=True)
    (Path(a.salida) / "valor_negocio.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(json.dumps({k: v for k, v in out.items() if k != "escenarios"}, ensure_ascii=False, indent=1, default=str))
    print(pd.DataFrame(escenarios).round(1).T.to_string())


if __name__ == "__main__":
    main()
