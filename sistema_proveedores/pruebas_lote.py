"""
Pruebas de la asignación por lotes (asignacion_lote.py).

    python pruebas_lote.py

1. Sin cupos: el mejor proveedor de T-002 y T-009 (Coordinadora) no tiene cupos
   Reefer esta semana; cada una debe ir a su segunda opción, con la pérdida reportada.
2. Competencia por un cupo: Coordinadora con 1 cupo Reefer y dos solicitudes que
   lo quieren. Debe ir a la que más pierde sin él (T-009), aunque llegue segunda;
   repartir por orden de llegada daría menos puntos.
3. Lote de 50 envíos históricos de la semana del 21 al 27 de sep-2026: nadie supera
   cupos ni el 35 %, y la pérdida total cuadra con la suma por solicitud.
4. La heurística voraz también respeta las restricciones y no supera al óptimo.
"""

import pandas as pd

from asignacion_lote import asignar_lote, imprimir_lote, leer_cupos
from modelo2_recomendador import Recomendador

rec = Recomendador.cargar("salidas_m2/modelo2.pkl")
rec.pruebas = pd.read_csv("solicitudes_prueba.csv")
CUPOS = leer_cupos("salidas_m2/capacidad_semana.csv", rec)
LOTE_SEMANA = ("S-030106,S-030110,S-030114,S-030162,S-030179,S-030182,S-030229,S-030231,S-030255,S-030350,"
               "S-030413,S-030463,S-030511,S-030512,S-030538,S-030548,S-030569,S-030585,S-030619,S-030635,"
               "S-030702,S-030721,S-030769,S-030812,S-030817,S-030853,S-030882,S-030891,S-030903,S-030937,"
               "S-030963,S-030975,S-030987,S-030997,S-031036,S-031041,S-031070,S-031119,S-031192,S-031211,"
               "S-031235,S-031242,S-031255,S-031257,S-031268,S-031326,S-031334,S-031365,S-031385,S-031386").split(",")
fila = lambda res, c: res["detalle"].set_index("codigo").loc[c]


def prueba_sin_cupos():
    assert CUPOS[("Coordinadora", "Reefer")] == 0
    res = asignar_lote(["T-001", "T-002", "T-009"], rec=rec, cupos=CUPOS)
    imprimir_lote(res, archivo_csv=None)
    for c, segunda in (("T-002", "Grupo TCC"), ("T-009", "Inter Rapidísimo")):
        f = fila(res, c)
        g = res["candidatos"].query("codigo == @c").sort_values("puntaje", ascending=False)
        assert f.primera_opcion == "Coordinadora" and f.asignado == segunda and f.opcion_asignada == 2, f
        assert abs(f.perdida - (g.puntaje.iat[0] - g.puntaje.iat[1])) < 1e-6
        assert "no tiene cupos" in f.motivo
    assert fila(res, "T-001").asignado == "Coordinadora"          # Dry sí tiene cupos
    print("OK 1: sin cupos para la mejor opción → segunda opción, pérdida reportada\n")


def prueba_competencia():
    cupos = {**CUPOS, ("Coordinadora", "Reefer"): 1}
    res = asignar_lote(["T-002", "T-009"], rec=rec, cupos=cupos)   # T-002 llega primero
    imprimir_lote(res, archivo_csv=None)
    cand = res["candidatos"].set_index(["codigo", "proveedor"]).puntaje
    assert fila(res, "T-009").asignado == "Coordinadora" and fila(res, "T-002").asignado == "Grupo TCC"
    optimo = res["resumen"].puntaje_total.iat[-1]
    por_llegada = cand[("T-002", "Coordinadora")] + cand[("T-009", "Inter Rapidísimo")]
    assert optimo > por_llegada
    print(f"OK 2: el cupo va a T-009 (pierde {cand[('T-009', 'Coordinadora')] - cand[('T-009', 'Inter Rapidísimo')]:.1f} sin él) "
          f"y no a T-002 (pierde {cand[('T-002', 'Coordinadora')] - cand[('T-002', 'Grupo TCC')]:.1f}); "
          f"{optimo:.1f} puntos frente a {por_llegada:.1f} por orden de llegada\n")


def comprobar_restricciones(res, cupos):
    asign = res["detalle"].dropna(subset=["asignado"])
    por_pc = asign.groupby(["asignado", "contenedor"]).size()
    assert all(n <= cupos.get(k, 10 ** 9) for k, n in por_pc.items()), por_pc
    if res["tope"] is not None:
        assert asign.asignado.value_counts().max() <= res["tope"] <= 0.35 * res["n"]


def prueba_lote_semana():
    res = asignar_lote(LOTE_SEMANA, rec=rec, cupos=CUPOS)
    comprobar_restricciones(res, CUPOS)
    r = res["resumen"].set_index("escenario").puntaje_total
    assert r["Sin restricciones"] >= r["Solo cupos"] >= r["Cupos + tope 35 %"]
    assert r["Sin restricciones"] >= r["Solo tope 35 %"] >= r["Cupos + tope 35 %"]
    assert abs(res["detalle"].perdida.sum() - (r["Sin restricciones"] - r["Cupos + tope 35 %"])) < 1e-6
    print(f"OK 3: lote de 50: {r['Sin restricciones']:.1f} → {r['Cupos + tope 35 %']:.1f} puntos, "
          f"tope {res['tope']}, máximo {res['comprobaciones']['max_pct_proveedor']:.0%} por proveedor")
    voraz = asignar_lote(LOTE_SEMANA, rec=rec, cupos=CUPOS, metodo="voraz")
    comprobar_restricciones(voraz, CUPOS)
    assert voraz["resumen"].puntaje_total.iat[-1] <= r["Cupos + tope 35 %"] + 1e-6
    print(f"OK 4: heurística voraz {voraz['resumen'].puntaje_total.iat[-1]:.1f} puntos ≤ óptimo, restricciones respetadas")


if __name__ == "__main__":
    prueba_sin_cupos()
    prueba_competencia()
    prueba_lote_semana()
    print("\nTodas las pruebas del lote pasaron.")
