"""
COMPARACIÓN DE MODELOS PARA "LLEGA A TIEMPO" Y PRECIO

Compara, sobre los mismos envíos de prueba, la tasa global, el % histórico del proveedor,
regresión logística, bosque aleatorio, gradient boosting y el Modelo 1. Usa dos cortes:
el del recomendador anterior (entrena hasta abr-2026) y el de validar_modelo2.py (hasta mar-2026).
Las diferencias frente a la logística llevan intervalo de confianza del 95 % (bootstrap pareado).

Uso:  python comparar_modelos.py
"""
import contextlib, io, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score, log_loss, brier_score_loss, r2_score, mean_absolute_error
from configuracion import BASE_DATOS, HOJA_ENVIOS
from modelo1_fiabilidad import ModeloFiabilidad
from modelo2_recomendador import Cotizador, variables_cotizador, VARS_NUM

env = pd.read_excel(BASE_DATOS, sheet_name=HOJA_ENVIOS)
env["fecha_orden"] = pd.to_datetime(env.fecha_orden)
env["t"] = (env.fecha_orden.dt.year - 2024) * 12 + env.fecha_orden.dt.month - 10
env["log_peso"] = np.log(env.peso_total_kg); env["log_valor"] = np.log(env.valor_declarado_cop); env["log_ref"] = np.log(env.tarifa_referencia_cop)
env["prov_zona"] = env.proveedor + "|" + env.zona; env["prov_temp"] = env.proveedor + "|" + env.temporada_alta.astype(str); env["prov_cont"] = env.proveedor + "|" + env.tipo_contenedor
NUM = ["distancia_km", "bultos_unidades", "transito_prometido_h", "temporada_alta", "fragil", "seguro", "log_peso", "log_valor"]
CAT = ["proveedor", "zona", "nivel_velocidad", "tipo_contenedor", "prov_zona", "prov_temp", "prov_cont"]
prep = lambda num: ColumnTransformer([("n", StandardScaler(), num), ("c", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT)])
pipe = lambda m, num=NUM: Pipeline([("p", prep(num)), ("m", m)])

rng = np.random.default_rng(0)
def ll(y, p): p = np.clip(p, 1e-6, 1-1e-6); return -(y*np.log(p) + (1-y)*np.log(1-p))
def boot(y, pa, pb, B=2000):
    """dif de log-loss (a - b) con IC 95 % por bootstrap pareado; negativo = a mejor"""
    d = ll(y, pa) - ll(y, pb); n = len(d)
    bs = np.array([d[rng.integers(0, n, n)].mean() for _ in range(B)])
    return d.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)
def auc_boot(y, pa, pb, B=500):
    n=len(y); vals=[]
    for _ in range(B):
        i = rng.integers(0, n, n); vals.append(roc_auc_score(y[i], pa[i]) - roc_auc_score(y[i], pb[i]))
    return roc_auc_score(y,pa)-roc_auc_score(y,pb), np.percentile(vals,2.5), np.percentile(vals,97.5)

for nombre, mask_tr in [("SPLIT DEL SCRIPT ADJUNTO (entrena hasta abr-2026, prueba may-sep)", env.t <= 18),
                        ("SPLIT DE NUESTRA VALIDACIÓN (entrena hasta mar-2026, prueba abr-sep)", env.fecha_orden <= "2026-03-31")]:
    tr, te = env[mask_tr], env[~mask_tr]; y = te.a_tiempo.to_numpy()
    P = {}
    P["Tasa global (base)"] = np.full(len(te), tr.a_tiempo.mean())
    P["% histórico del proveedor"] = te.proveedor.map(tr.groupby("proveedor").a_tiempo.mean()).to_numpy()
    P["Regresión logística"] = pipe(LogisticRegression(C=2, max_iter=2000)).fit(tr[NUM+CAT], tr.a_tiempo).predict_proba(te[NUM+CAT])[:,1]
    NUM2 = [c for c in NUM if c != "transito_prometido_h"]
    P["Logística sin tránsito prometido"] = pipe(LogisticRegression(C=2, max_iter=2000), NUM2).fit(tr[NUM2+CAT], tr.a_tiempo).predict_proba(te[NUM2+CAT])[:,1]
    P["Bosque aleatorio"] = pipe(RandomForestClassifier(n_estimators=200, min_samples_leaf=20, n_jobs=-1, random_state=0)).fit(tr[NUM+CAT], tr.a_tiempo).predict_proba(te[NUM+CAT])[:,1]
    P["Gradient boosting"] = pipe(HistGradientBoostingClassifier(max_iter=200, learning_rate=.08, random_state=0)).fit(tr[NUM+CAT], tr.a_tiempo).predict_proba(te[NUM+CAT])[:,1]
    with contextlib.redirect_stdout(io.StringIO()):
        m1 = ModeloFiabilidad().ajustar(tr.drop(columns=["t"]), fecha_corte=tr.fecha_orden.max())
    P["Modelo 1 (nuestro)"] = m1.predecir(te.drop(columns=["t"]))["pred_puntualidad"].to_numpy()
    filas = [{"modelo": k, "AUC": roc_auc_score(y, p), "log_loss": log_loss(y, np.clip(p,1e-6,1-1e-6)), "brier": brier_score_loss(y, p)} for k, p in P.items()]
    t = pd.DataFrame(filas).set_index("modelo")
    base = t.loc["Tasa global (base)"]
    t["mejora_logloss_vs_base_pct"] = 100*(base.log_loss - t.log_loss)/base.log_loss
    t["mejora_brier_vs_base_pct"] = 100*(base.brier - t.brier)/base.brier
    print(f"\n=== {nombre}: {len(tr):,} entrenamiento / {len(te):,} prueba ===")
    print(t.round(4).to_string())
    lg = P["Regresión logística"]
    for k in ["Modelo 1 (nuestro)", "Bosque aleatorio", "Gradient boosting", "Logística sin tránsito prometido"]:
        d, lo, hi = boot(y, P[k], lg); a, alo, ahi = auc_boot(y, P[k], lg)
        print(f"  {k} − logística: log-loss {d:+.4f} [IC95 {lo:+.4f}, {hi:+.4f}] · AUC {a:+.4f} [{alo:+.4f}, {ahi:+.4f}]")
    # calibración por decil
    for k in ["Regresión logística", "Modelo 1 (nuestro)"]:
        q = pd.qcut(P[k], 10, labels=False, duplicates="drop")
        c = pd.DataFrame({"p":P[k],"y":y,"q":q}).groupby("q").agg(p=("p","mean"), y=("y","mean"))
        print(f"  calibración {k}: error medio |pred-real| por decil = {100*(c.p-c.y).abs().mean():.1f} pts")

# ---- precio en el split del adjunto, sobre log(precio) para comparar igual ----
tr, te = env[env.t <= 18], env[env.t > 18]
NUMP = NUM + ["log_ref"]
yl = np.log(te.precio_cop)
pr_gb = te.log_ref + pipe(HistGradientBoostingRegressor(max_iter=300, learning_rate=.08, random_state=0), NUMP).fit(tr[NUMP+CAT], np.log(tr.precio_cop)-tr.log_ref).predict(te[NUMP+CAT])
pr_rd = te.log_ref + pipe(Ridge(alpha=1), NUMP).fit(tr[NUMP+CAT], np.log(tr.precio_cop)-tr.log_ref).predict(te[NUMP+CAT])
with contextlib.redirect_stdout(io.StringIO()):
    cot = Cotizador().ajustar(tr.drop(columns=["t"]), corte="2025-09-30")
pipe_c, cats = cot.modelos[("precio", True)]
pr_cot = pipe_c.predict(variables_cotizador(te.drop(columns=["t"]))[VARS_NUM + cats])
print("\n=== PRECIO (split del adjunto), medido sobre log(precio) ===")
for k, p in [("Adjunto: Ridge con tarifa de referencia", pr_rd), ("Adjunto: Gradient boosting con tarifa de referencia", pr_gb), (f"Nuestro cotizador ({cot.algoritmo['precio']}, sin tarifa de referencia)", pr_cot)]:
    print(f"  {k:<58} R² {r2_score(yl, p):.4f} · error medio {100*(np.exp(mean_absolute_error(yl, p))-1):.1f} %")
