"""
ÉXITO DE LA RECOMENDACIÓN: ¿la #1 del modelo es la mejor opción real sumando todos los factores?

El modelo se entrena hasta 2026-03-31 (igual que validar_modelo2.py). Para cada envío de abr-sep 2026
se calcula, con los RESULTADOS REALES de ese periodo, el puntaje de cada empresa elegible en su tipo
de envío (contenedor × zona × velocidad; si una empresa tiene menos de 30 envíos ahí, contenedor × zona
y luego contenedor), con los mismos pesos del Modelo 2: precio y tiempo reales frente al mercado, y
fiabilidad real (puntualidad, retraso, daños y satisfacción). La "mejor opción" es la de mayor puntaje
real; se mide cuántas veces coincide con la #1 del modelo, con la decisión histórica y con el azar.

Uso:  python exito_recomendacion.py
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from validar_modelo2 import entrenar_hasta_corte, puntuar_todos, RESULTADOS, CORTE
from modelo1_fiabilidad import preparar
from modelo2_recomendador import FACTORES
D = "base_simulada_mensajeria.xlsx"
env = pd.read_excel(D, sheet_name="Envios")
rec, train = entrenar_hasta_corte(env)
test = env[pd.to_datetime(env.fecha_orden) > CORTE].copy()
pts = puntuar_todos(rec, test.drop(columns=RESULTADOS))
p_id = pts.set_index(["id_envio", "proveedor"])

# Resultados REALES de abr-sep, relativos al mercado de cada envío (el mercado viene del modelo sin proveedor, igual para todos)
real = preparar(test).set_index("id_envio")
m = pts.drop_duplicates("id_envio").set_index("id_envio")
real["r_precio"] = real.precio_cop / m.mercado_precio.reindex(real.index)
real["r_tiempo"] = real.transito_real_h / m.mercado_tiempo.reindex(real.index)
real["fiab"] = 100 * real.fiabilidad    # puntualidad 40 + retraso 20 + sin daño 25 + satisfacción 15, real
MIN = 30
niveles = [["tipo_contenedor", "zona", "nivel_velocidad"], ["tipo_contenedor", "zona"], ["tipo_contenedor"]]
agg = {tuple(n): real.groupby(n + ["proveedor"]).agg(n=("fiab", "size"), r_precio=("r_precio", "mean"),
                                                     r_tiempo=("r_tiempo", "mean"), fiab=("fiab", "mean")) for n in niveles}
def desempeno(row, p):
    for n in niveles:
        k = tuple(row[c] for c in n) + (p,)
        t = agg[tuple(n)]
        if k in t.index and t.loc[k, "n"] >= MIN:
            return t.loc[k]
    return None

esc = lambda r: float(np.clip(1.5 - r, 0, 1) * 100)
filas = []
grp = pts[pts.elegible].groupby("id_envio")
for i, g in grp:
    row = real.loc[i]
    w = {f: g[f"peso_{f}"].iat[0] for f in FACTORES}
    s_real = {}
    for p in g.proveedor:
        d = desempeno(row, p)
        if d is None: continue
        s_real[p] = w["precio"] * esc(d.r_precio) + w["tiempo"] * esc(d.r_tiempo) + w["fiabilidad"] * d.fiab
    if len(s_real) < 2: continue
    orden = sorted(s_real, key=lambda p: -s_real[p])
    mejor, top_modelo = orden[0], g.sort_values("puntaje", ascending=False).proveedor.tolist()
    rec1 = top_modelo[0]
    filas.append({"id": i, "cont": row.tipo_contenedor, "n_cand": len(s_real), "mejor_real": mejor, "rec": rec1,
                  "acierto": rec1 == mejor, "en_top3": mejor in top_modelo[:3],
                  "dif_pts": s_real[mejor] - s_real.get(rec1, np.nan),
                  "hist_acierto": row.proveedor == mejor, "hist_dif": s_real[mejor] - s_real.get(row.proveedor, np.nan),
                  "azar": 1 / len(s_real)})
r = pd.DataFrame(filas)
print(f"Envíos evaluados: {len(r):,} de {test.shape[0]:,} (con al menos 2 empresas con ≥{MIN} envíos reales en su tipo de envío)")
print(f"Modelo: la #1 recomendada es la mejor real en {100*r.acierto.mean():.1f} % | la mejor está en su top 3: {100*r.en_top3.mean():.1f} % | "
      f"a menos de 2 pts de la mejor: {100*(r.dif_pts < 2).mean():.1f} % | pérdida media {r.dif_pts.mean():.2f} pts")
print(f"Decisión histórica: elige la mejor real en {100*r.hist_acierto.mean():.1f} % | a <2 pts: {100*(r.hist_dif < 2).mean():.1f} % | pérdida media {r.hist_dif.mean():.2f} pts")
print(f"Al azar: {100*r.azar.mean():.1f} %")
print(r.groupby("cont").agg(envios=("id","size"), acierto=("acierto","mean"), top3=("en_top3","mean"), hist=("hist_acierto","mean")).mul([1,100,100,100]).round(1))
print("Mejor real (reparto %):", (100*r.mejor_real.value_counts(normalize=True)).round(1).to_dict())
print("Errores del modelo: recomendó / la mejor era:", r[~r.acierto].groupby(["rec","mejor_real"]).size().sort_values(ascending=False).head(6).to_dict())
r.to_csv("salidas_validacion_m2/exito_recomendacion.csv", index=False, encoding="utf-8-sig")
print(f"Regla 'siempre Coordinadora': {100*(r.mejor_real == 'Coordinadora').mean():.1f} % · casos donde la mejor no era Coordinadora: {(r.mejor_real != 'Coordinadora').sum()}, el modelo acierta {100*r[r.mejor_real != 'Coordinadora'].acierto.mean():.1f} %")
