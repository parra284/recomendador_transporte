"""
VALIDACIÓN DEL MODELO 2 — seis pruebas para el jurado
=====================================================

1. Prueba retrospectiva sin trampa: Modelo 1, cotizador y catálogo se entrenan
   SOLO con envíos hasta 2026-03-31. Cada envío de abr-sep 2026 se recomienda sin
   mirar su resultado (se borran proveedor, precio, tiempos, a tiempo, daños y
   satisfacción antes de puntuar) y se compara con el proveedor elegido en su momento.
2. Recomendado frente a elegido con los modelos (no con el resultado real):
   costo esperado, probabilidad de llegar a tiempo y tiempo esperado; en total y
   por tipo de contenedor.
3. Resultados reales: ¿los envíos donde el elegido coincidió con el recomendado
   llegaron a tiempo más seguido? Solo indicativo (sesgo de selección).
4. Coherencia: el recomendado nunca viola un filtro duro (comprobación
   independiente, recalculada desde los datos de entrenamiento).
5. Sensibilidad: cada peso base ± 10 puntos → ¿en cuántos envíos cambia el #1?
6. Casos de prueba: las solicitudes de solicitudes_prueba.csv con el modelo de producción.

Extra: la hoja Supuestos (parámetros verdaderos del simulador) se usa SOLO aquí,
para comprobar que el cotizador recupera el factor de precio de cada proveedor y
que el Modelo 1 recupera el orden de puntualidad. Nunca entra en la recomendación.

Para que la prueba retrospectiva corra en minutos, los ~7.500 envíos se puntúan en
bloque con los mismos componentes del Modelo 2 (cotizador, Modelo 1, catálogo,
escala y pesos). Antes de usar ese cálculo, el script comprueba en una muestra
que da exactamente lo mismo que Recomendador.recomendar().

Uso:
    python validar_modelo2.py                     # escribe salidas_validacion_m2/
    python validar_modelo2.py --muestra-igualdad 100
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

import modelo2_recomendador as m2
from configuracion import BASE_DATOS, DIR_M2, DIR_VALIDACION, HOJA_ENVIOS, SOLICITUDES_PRUEBA
from modelo1_fiabilidad import ModeloFiabilidad
from modelo2_recomendador import (FACTORES, MIN_SERVICIOS, Catalogo, Cotizador, Recomendador, escala)

CORTE = pd.Timestamp("2026-03-31")
CORTE_SELECCION_COTIZADOR = "2025-09-30"  # Ridge vs boosting se eligen DENTRO del entrenamiento
RESULTADOS = ["proveedor", "tarifa_referencia_cop", "precio_cop", "transito_prometido_h", "transito_real_h",
              "a_tiempo", "danado", "satisfaccion_1a5", "precio_rel_ref"]
DELTA_PESO = 0.10


# --------------------------------------------------------------------------
# Entrenamiento hasta el corte y puntuación en bloque
# --------------------------------------------------------------------------

def entrenar_hasta_corte(env: pd.DataFrame) -> tuple[Recomendador, pd.DataFrame]:
    fechas = pd.to_datetime(env["fecha_orden"])
    train = env[fechas <= CORTE].copy()
    assert pd.to_datetime(train["fecha_orden"]).max() <= CORTE
    with contextlib.redirect_stdout(io.StringIO()):
        m1 = ModeloFiabilidad().ajustar(train, fecha_corte=CORTE)
        cot = Cotizador().ajustar(train, corte=CORTE_SELECCION_COTIZADOR)
    cat = Catalogo.desde_historial(train)
    # sin cupos: la capacidad simulada es una foto de "esta semana", no del pasado
    return Recomendador(m1, cot, cat, None, train), train


def puntuar_todos(rec: Recomendador, sol: pd.DataFrame) -> pd.DataFrame:
    """Puntaje de cada proveedor para cada solicitud, con la misma lógica que recomendar()."""
    provs = rec.m1.proveedores
    n = len(sol)
    sol = sol.reset_index(drop=True)
    pares = sol.loc[sol.index.repeat(len(provs))].reset_index(drop=True)
    pares["proveedor"] = np.tile(provs, n)

    out = pares[["id_envio", "proveedor", "tipo_contenedor", "nivel_velocidad", "zona"]].copy()
    out["precio_cop"] = rec.cot.estimar(pares, "precio", True)
    out["tiempo_prometido_h"] = rec.cot.estimar(pares, "prometido", True)
    out["tiempo_esperado_h"] = rec.cot.estimar(pares, "tiempo", True)
    merc_p = np.repeat(rec.cot.estimar(sol, "precio", False), len(provs))
    merc_t = np.repeat(rec.cot.estimar(sol, "tiempo", False), len(provs))
    out["mercado_precio"], out["mercado_tiempo"] = merc_p, merc_t
    pred = rec.m1.predecir(pares)
    out["fiabilidad"] = np.round(100 * pred["pred_fiabilidad"].to_numpy(), 1)    # igual que puntuar_envio
    out["prob_a_tiempo"] = np.round(100 * pred["pred_puntualidad"].to_numpy(), 1)
    out["pts_precio"] = [escala(v, r) for v, r in zip(out.precio_cop, merc_p)]
    out["pts_tiempo"] = [escala(v, r) for v, r in zip(out.tiempo_esperado_h, merc_t)]
    out["pts_fiabilidad"] = out["fiabilidad"]

    registros = pares.to_dict("records")
    out["motivos"] = [rec.cat.motivos_exclusion(s, s["proveedor"], None) for s in registros]
    out["elegible"] = out["motivos"].str.len() == 0
    out = aplicar_pesos(rec, out, pares)
    return out


def aplicar_pesos(rec: Recomendador, out: pd.DataFrame, pares: pd.DataFrame | None = None) -> pd.DataFrame:
    """Pesos con Recomendador.pesos() (sin plazo en el historial: dependen de contenedor y velocidad)."""
    out = out.copy()
    claves = out[["tipo_contenedor", "nivel_velocidad"]].drop_duplicates().itertuples(index=False)
    w = {(c, v): rec.pesos({"tipo_contenedor": c, "nivel_velocidad": v}, 1.0)[0] for c, v in claves}
    for f in FACTORES:
        out[f"peso_{f}"] = [w[(c, v)][f] for c, v in zip(out.tipo_contenedor, out.nivel_velocidad)]
    out["puntaje"] = sum(out[f"peso_{f}"] * out[f"pts_{f}"] for f in FACTORES)
    return out


def primera_opcion(pts: pd.DataFrame, columna="puntaje") -> pd.Series:
    e = pts[pts.elegible]
    return e.loc[e.groupby("id_envio")[columna].idxmax()].set_index("id_envio").proveedor


def comprobar_igualdad(rec: Recomendador, sol: pd.DataFrame, pts: pd.DataFrame, n: int, semilla=7) -> dict:
    """El cálculo en bloque debe dar lo mismo que recomendar() envío por envío."""
    muestra = sol.sample(min(n, len(sol)), random_state=semilla)
    max_dif, distintos = 0.0, 0
    for s in muestra.to_dict("records"):
        r = rec.recomendar(dict(s))["ranking"]
        if r.empty:
            distintos += int(pts[(pts.id_envio == s["id_envio"]) & pts.elegible].shape[0] > 0)
            continue
        b = pts[(pts.id_envio == s["id_envio"]) & pts.elegible].set_index("proveedor").puntaje
        dif = (r.set_index("proveedor").puntaje - b).abs()
        max_dif = max(max_dif, float(dif.max()))
        distintos += int(set(r.proveedor) != set(b.index) or r.proveedor.iat[0] != b.idxmax())
    return {"envios_comparados": len(muestra), "max_dif_puntaje": max_dif, "envios_distintos": distintos}


# --------------------------------------------------------------------------
# Pruebas
# --------------------------------------------------------------------------

def tabla_comparacion(d: pd.DataFrame, por: str | None) -> pd.DataFrame:
    def resumen(g):
        return pd.Series({
            "envios": len(g),
            "coincidencia_pct": 100 * g.coincide.mean(),
            "dif_costo_media_cop": (g.precio_rec - g.precio_eleg).mean(),
            "dif_costo_media_pct": 100 * (g.precio_rec / g.precio_eleg - 1).mean(),
            "dif_costo_total_pct": 100 * (g.precio_rec.sum() / g.precio_eleg.sum() - 1),
            "dif_prob_a_tiempo_pts": (g.pat_rec - g.pat_eleg).mean(),
            "dif_tiempo_esperado_h": (g.tiempo_rec - g.tiempo_eleg).mean(),
            "dif_fiabilidad_pts": (g.fiab_rec - g.fiab_eleg).mean(),
        })
    if por is None:
        return resumen(d).to_frame("Total").T
    return d.groupby(por).apply(resumen)


def prueba_coherencia(train: pd.DataFrame, d: pd.DataFrame, sol: pd.DataFrame) -> dict:
    """Recalcula los filtros desde el entrenamiento, sin usar el código del catálogo."""
    n_pc = train.groupby(["proveedor", "tipo_contenedor"]).size()
    n_pcv = train.groupby(["proveedor", "tipo_contenedor", "nivel_velocidad"]).size()
    pmax = train.groupby(["proveedor", "tipo_contenedor"]).peso_total_kg.max()
    ciudades = {p: set(g.origen) | set(g.destino) for p, g in train.groupby("proveedor")}
    vel_zona = set(zip(train.nivel_velocidad, train.zona))
    s = sol.set_index("id_envio").loc[d.id_envio]
    p, c, v = d.recomendado.to_numpy(), s.tipo_contenedor.to_numpy(), s.nivel_velocidad.to_numpy()
    viol = {
        "contenedor": sum(n_pc.get((a, b), 0) < MIN_SERVICIOS for a, b in zip(p, c)),
        "cobertura": sum(o not in ciudades[a] or de not in ciudades[a] for a, o, de in zip(p, s.origen, s.destino)),
        "peso": sum(kg > pmax.get((a, b), -1) for a, b, kg in zip(p, c, s.peso_total_kg)),
        "velocidad": sum(n_pcv.get((a, b, x), 0) < MIN_SERVICIOS for a, b, x in zip(p, c, v)),
        "velocidad_zona": sum((x, z) not in vel_zona for x, z in zip(v, s.zona)),
    }
    return viol


def prueba_sensibilidad(rec: Recomendador, pts: pd.DataFrame, top_base: pd.Series) -> pd.DataFrame:
    filas, original = [], {k: dict(v) for k, v in m2.PESOS_PERFIL.items()}
    try:
        for cont in original:
            n_cont = int((pts.drop_duplicates("id_envio").tipo_contenedor == cont).sum())
            for f in FACTORES:
                for signo in (+1, -1):
                    m2.PESOS_PERFIL[cont][f] = max(0.0, original[cont][f] + signo * DELTA_PESO)
                    top = primera_opcion(aplicar_pesos(rec, pts))
                    m2.PESOS_PERFIL[cont] = dict(original[cont])
                    cambia = int((top != top_base.reindex(top.index)).sum())
                    filas.append({"contenedor": cont, "factor": f, "cambio": f"{signo * 10:+d} pts",
                                  "peso_base": original[cont][f],
                                  "peso_probado": max(0.0, original[cont][f] + signo * DELTA_PESO),
                                  "envios_contenedor": n_cont, "cambia_primera_opcion": cambia,
                                  "pct_del_contenedor": 100 * cambia / n_cont if n_cont else np.nan,
                                  "pct_del_total": 100 * cambia / len(top_base)})
    finally:
        for k, v in original.items():
            m2.PESOS_PERFIL[k] = v
    return pd.DataFrame(filas)


def recuperacion_supuestos(datos: str, pts: pd.DataFrame, rec: Recomendador) -> tuple[pd.DataFrame, dict]:
    """Hoja Supuestos: SOLO para validar. ¿El cotizador recupera el factor de precio?"""
    sup = pd.read_excel(datos, sheet_name="Supuestos", nrows=3).set_index("supuesto")
    sup = sup.apply(pd.to_numeric, errors="coerce")
    verdad_precio = sup.loc["Factor de precio del proveedor"]
    verdad_tiempo = sup.loc["Factor de tiempo del proveedor"]
    verdad_punt = sup.loc["Efecto proveedor en puntualidad (log-horas)"]
    # Envíos Dry de prueba: los seis proveedores manejan Dry, se compara cada uno en los mismos envíos
    dry = pts[pts.tipo_contenedor == "Dry"]
    ancla = "Coordinadora"
    lp = np.log(dry.pivot(index="id_envio", columns="proveedor", values="precio_cop"))
    lt = np.log(dry.pivot(index="id_envio", columns="proveedor", values="tiempo_prometido_h"))
    filas = []
    for p in lp.columns:
        filas.append({"proveedor": p,
                      "factor_precio_verdadero_rel": verdad_precio[p] / verdad_precio[ancla],
                      "factor_precio_estimado_rel": float(np.exp((lp[p] - lp[ancla]).mean())),
                      "factor_tiempo_verdadero_rel": verdad_tiempo[p] / verdad_tiempo[ancla],
                      "factor_tiempo_prometido_estimado_rel": float(np.exp((lt[p] - lt[ancla]).mean())),
                      "efecto_puntualidad_verdadero": verdad_punt[p],
                      "puntualidad_m1_pts": 100 * float(rec.m1.efectos["proveedor"].loc[p, "ef_puntualidad"])})
    t = pd.DataFrame(filas)
    t["error_precio_pct"] = 100 * (t.factor_precio_estimado_rel / t.factor_precio_verdadero_rel - 1)
    t["error_tiempo_pct"] = 100 * (t.factor_tiempo_prometido_estimado_rel / t.factor_tiempo_verdadero_rel - 1)
    resumen = {
        "corr_precio": float(np.corrcoef(t.factor_precio_verdadero_rel, t.factor_precio_estimado_rel)[0, 1]),
        "error_precio_max_pct": float(t.error_precio_pct.abs().max()),
        "corr_tiempo": float(np.corrcoef(t.factor_tiempo_verdadero_rel, t.factor_tiempo_prometido_estimado_rel)[0, 1]),
        "spearman_puntualidad": float(t[["efecto_puntualidad_verdadero", "puntualidad_m1_pts"]]
                                      .rank().corr().iat[0, 1]),
    }
    return t, resumen


CASOS_ESPERADOS = {
    "T-001": ("Carga seca típica: compiten los 6 proveedores y gana el de mejor balance precio-fiabilidad",
              lambda r: not r["excluidos"] and not r["ranking"].empty),
    "T-002": ("Coordinadora sin cupos Reefer queda fuera; gana el de mayor probabilidad de llegar en el plazo",
              lambda r: "Coordinadora" in r["excluidos"] and r["ranking"].prob_plazo.idxmax() == 0),
    "T-003": ("Acero en Open Top: 4-72 y Envía fuera por contenedor",
              lambda r: {"4-72", "Envía"} <= set(r["excluidos"]) and not r["ranking"].empty),
    "T-004": ("Flat Rack: solo Coordinadora, Grupo TCC y Servientrega lo manejan",
              lambda r: set(r["ranking"].proveedor) == {"Coordinadora", "Grupo TCC", "Servientrega"}),
    "T-005": ("Exprés a Quibdó no existe: no hay candidatos y propone prioritaria",
              lambda r: r["ranking"].empty and r["alternativas"] is not None and not r["alternativas"].empty),
    "T-006": ("60 kg a Pasto: 4-72 fuera por peso y Grupo TCC por cobertura",
              lambda r: any("Peso" in m for m in r["excluidos"].get("4-72", []))
              and any("Pasto" in m for m in r["excluidos"].get("Grupo TCC", []))),
    "T-007": ("Mismo día en Medellín: 4-72 fuera; el #1 llega en plazo al menos el 70 % de las veces",
              lambda r: "4-72" in r["excluidos"] and r["ranking"].prob_plazo.iat[0] >= 70),
    "T-008": ("Flat Rack mismo día: nadie lo ha hecho 5 veces; propone exprés",
              lambda r: r["ranking"].empty and not r["alternativas"].empty),
    "T-009": ("Reefer de 1.050 kg: Grupo TCC fuera por peso (máximo 900 kg)",
              lambda r: any("Peso" in m for m in r["excluidos"].get("Grupo TCC", []))),
}


def casos_prueba(modelo: str, pruebas: str) -> pd.DataFrame:
    rec = Recomendador.cargar(modelo)
    rec.pruebas = pd.read_csv(pruebas)
    filas = []
    for c in rec.pruebas.id_envio:
        r = rec.recomendar(rec.solicitud(c))
        if not r["ranking"].empty:
            r["ranking"]["prob_plazo"] = 100 * r["ranking"]["prob_plazo"]
        desc, regla = CASOS_ESPERADOS.get(c, ("(sin regla definida)", lambda r: True))
        top = r["ranking"].proveedor.tolist()[:3] if not r["ranking"].empty else []
        filas.append({"codigo": c, "top3": " > ".join(top) or "—",
                      "puntaje_1": round(r["ranking"].puntaje.iat[0], 1) if top else None,
                      "excluidos": len(r["excluidos"]), "razonable": "sí" if regla(r) else "NO", "lectura": desc})
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------
# Programa principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Validación del Modelo 2")
    ap.add_argument("--datos", default=str(BASE_DATOS))
    ap.add_argument("--modelo", default=str(DIR_M2 / "modelo2.pkl"), help="modelo de producción (prueba 6)")
    ap.add_argument("--pruebas", default=str(SOLICITUDES_PRUEBA))
    ap.add_argument("--salida", default=str(DIR_VALIDACION))
    ap.add_argument("--muestra-igualdad", type=int, default=60)
    a = ap.parse_args()
    out = Path(a.salida)
    out.mkdir(exist_ok=True)
    pd.set_option("display.width", 220)
    log = []

    def p(txt=""):
        print(txt)
        log.append(str(txt))

    env = pd.read_excel(a.datos, sheet_name=HOJA_ENVIOS)
    rec, train = entrenar_hasta_corte(env)
    test = env[pd.to_datetime(env.fecha_orden) > CORTE].copy()
    sol = test.drop(columns=RESULTADOS)                     # lo que se sabe al pedir el envío
    elegido = test.set_index("id_envio").proveedor
    p("VALIDACIÓN DEL MODELO 2")
    p(f"Entrenamiento: {len(train):,} envíos hasta {pd.to_datetime(train.fecha_orden).max():%Y-%m-%d} "
      f"(corte {CORTE:%Y-%m-%d}). Prueba: {len(test):,} envíos de "
      f"{pd.to_datetime(test.fecha_orden).min():%Y-%m-%d} a {pd.to_datetime(test.fecha_orden).max():%Y-%m-%d}.")
    p(f"Modelo de tiempo elegido dentro del entrenamiento: " + ", ".join(
        f"{k} = {v}" for k, v in rec.cot.algoritmo.items()))
    p("Columnas borradas antes de recomendar: " + ", ".join(RESULTADOS))
    p("Cupos: no se aplican (la capacidad simulada es una foto de esta semana, no del pasado).")

    pts = puntuar_todos(rec, sol)
    igual = comprobar_igualdad(rec, sol, pts, a.muestra_igualdad)
    p(f"\nControl: el cálculo en bloque coincide con recomendar() en {igual['envios_comparados']} envíos al azar "
      f"(diferencia máxima de puntaje {igual['max_dif_puntaje']:.1e}; envíos con distinto #1: {igual['envios_distintos']}).")
    assert igual["envios_distintos"] == 0 and igual["max_dif_puntaje"] < 1e-6

    # ---- 1 y 2 -----------------------------------------------------------
    top = primera_opcion(pts)
    sin_candidato = sorted(set(sol.id_envio) - set(top.index))
    idx = pts.set_index(["id_envio", "proveedor"])
    d = pd.DataFrame({"id_envio": top.index, "recomendado": top.values})
    d["elegido"] = elegido.reindex(d.id_envio).values
    d["tipo_contenedor"] = sol.set_index("id_envio").tipo_contenedor.reindex(d.id_envio).values
    d["coincide"] = d.recomendado == d.elegido
    for col, k in [("precio_cop", "precio"), ("prob_a_tiempo", "pat"), ("tiempo_esperado_h", "tiempo"),
                   ("fiabilidad", "fiab"), ("puntaje", "puntaje")]:
        d[f"{k}_rec"] = idx.loc[list(zip(d.id_envio, d.recomendado)), col].to_numpy()
        d[f"{k}_eleg"] = idx.loc[list(zip(d.id_envio, d.elegido)), col].to_numpy()
    d["elegido_elegible"] = idx.loc[list(zip(d.id_envio, d.elegido)), "elegible"].to_numpy()
    d["a_tiempo_real"] = test.set_index("id_envio").a_tiempo.reindex(d.id_envio).to_numpy()
    d.to_csv(out / "por_envio.csv", index=False, encoding="utf-8-sig")

    total = tabla_comparacion(d, None)
    por_cont = tabla_comparacion(d, "tipo_contenedor")
    comp = pd.concat([total, por_cont])
    comp.round(2).to_csv(out / "recomendado_vs_elegido.csv", encoding="utf-8-sig")
    t = total.iloc[0]
    p("\n1-2. RECOMENDADO FRENTE A ELEGIDO EN SU MOMENTO (valores esperados según los modelos, no resultados reales)")
    p(f"  Envíos recomendados: {len(d):,}; sin ningún candidato: {len(sin_candidato)}; elegido que hoy el catálogo "
      f"excluiría: {int((~d.elegido_elegible).sum())}")
    p(comp[["envios", "coincidencia_pct", "dif_costo_media_cop", "dif_costo_media_pct", "dif_costo_total_pct",
            "dif_prob_a_tiempo_pts", "dif_tiempo_esperado_h", "dif_fiabilidad_pts"]].round(1).to_string())
    p("  (dif = recomendado − elegido; costo % = promedio de los cocientes por envío; total % = suma frente a suma)")
    mezcla = pd.DataFrame({"elegido_historico_pct": 100 * d.elegido.value_counts(normalize=True),
                           "recomendado_pct": 100 * d.recomendado.value_counts(normalize=True)}).fillna(0).round(1)
    p("\n  Reparto por proveedor:\n" + mezcla.to_string())
    mezcla.to_csv(out / "reparto_proveedores.csv", encoding="utf-8-sig")

    # ---- 3 ---------------------------------------------------------------
    g = d.groupby("coincide").agg(envios=("id_envio", "size"), a_tiempo_real_pct=("a_tiempo_real", "mean"),
                                  a_tiempo_esperado_pct=("pat_eleg", "mean"))
    g["a_tiempo_real_pct"] *= 100
    g["real_menos_esperado_pts"] = g.a_tiempo_real_pct - g.a_tiempo_esperado_pct
    g.index = g.index.map({True: "Coincide", False: "No coincide"})
    por_prov = d.groupby(["elegido", "coincide"]).a_tiempo_real.agg(["size", "mean"]).unstack()
    por_prov.columns = [f"{a}_{'coincide' if b else 'no_coincide'}" for a, b in por_prov.columns]
    por_prov = por_prov.rename(columns=lambda c: c.replace("size", "envios").replace("mean", "a_tiempo"))
    for c in [c for c in por_prov if c.startswith("a_tiempo")]:
        por_prov[c] *= 100
    p("\n3. RESULTADOS REALES (solo indicativo: sesgo de selección)")
    p(g.round(1).to_string())
    p("  Por proveedor elegido (% a tiempo real):\n" + por_prov.round(1).to_string())
    g.round(2).to_csv(out / "verificacion_real.csv", encoding="utf-8-sig")

    # ---- 4 ---------------------------------------------------------------
    viol = prueba_coherencia(train, d, sol)
    p("\n4. COHERENCIA: violaciones de filtros duros en el recomendado (recalculadas desde el entrenamiento)")
    p("  " + " · ".join(f"{k}: {v}" for k, v in viol.items()) + f"  → {'OK' if sum(viol.values()) == 0 else 'FALLA'}")

    # ---- 5 ---------------------------------------------------------------
    sens = prueba_sensibilidad(rec, pts, top)
    sens.round(2).to_csv(out / "sensibilidad_pesos.csv", index=False, encoding="utf-8-sig")
    p(f"\n5. SENSIBILIDAD: cada peso base ± 10 puntos (luego se renormaliza a 100 %)")
    p(sens[["contenedor", "factor", "cambio", "peso_base", "envios_contenedor", "cambia_primera_opcion",
            "pct_del_contenedor", "pct_del_total"]].round(1).to_string(index=False))

    # ---- extra: hoja Supuestos --------------------------------------------
    rec_sup, res_sup = recuperacion_supuestos(a.datos, pts, rec)
    rec_sup.round(3).to_csv(out / "recuperacion_supuestos.csv", index=False, encoding="utf-8-sig")
    p("\nEXTRA. ¿LOS MODELOS RECUPERAN LOS PARÁMETROS OCULTOS? (hoja Supuestos, solo para validar; relativo a Coordinadora)")
    p(rec_sup.round(3).to_string(index=False))
    p(f"  Correlación factor de precio verdadero vs estimado: {res_sup['corr_precio']:.3f} "
      f"(error máximo {res_sup['error_precio_max_pct']:.1f} %); tiempo prometido: {res_sup['corr_tiempo']:.3f}; "
      f"orden de puntualidad (Spearman) Modelo 1 vs verdad: {res_sup['spearman_puntualidad']:.2f}")

    # ---- 6 ---------------------------------------------------------------
    casos = casos_prueba(a.modelo, a.pruebas)
    casos.to_csv(out / "casos_prueba.csv", index=False, encoding="utf-8-sig")
    p("\n6. CASOS DE PRUEBA (modelo de producción)")
    p(casos.to_string(index=False))

    resumen = {
        "corte": str(CORTE.date()), "envios_entrenamiento": len(train), "envios_prueba": len(test),
        "igualdad_con_recomendar": igual, "sin_candidato": len(sin_candidato),
        "total": {k: float(v) for k, v in total.iloc[0].items()},
        "por_contenedor": {c: {k: float(v) for k, v in r.items()} for c, r in por_cont.iterrows()},
        "verificacion_real": {i: {k: float(v) for k, v in r.items()} for i, r in g.iterrows()},
        "violaciones_filtros": {k: int(v) for k, v in viol.items()},
        "sensibilidad_max_pct_total": float(sens.pct_del_total.max()),
        "sensibilidad_max_pct_contenedor": float(sens.pct_del_contenedor.max()),
        "supuestos": res_sup, "casos_razonables": int((casos.razonable == "sí").sum()), "casos": len(casos),
    }
    (out / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "resumen.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    p(f"\nResultados en {out.resolve()}")


if __name__ == "__main__":
    main()
