"""
Validación del Modelo 1 — tres pruebas para mostrar al jurado que el método funciona.

1. Prueba en el tiempo: se entrena con oct-2024 a mar-2026 y se predice si los
   envíos de abr-2026 a sep-2026 llegan a tiempo (datos que el modelo no vio).
2. Recuperación de la verdad: la base es simulada y trae el efecto real de cada
   proveedor en la puntualidad (hoja Supuestos). ¿El modelo lo encuentra?
3. Pocos datos: si un proveedor tiene muy pocos envíos, ¿con qué frecuencia
   aparece falsamente como el #1? Se compara la tasa bruta con el modelo.
4. Fortalezas y debilidades sembradas: la base simulada no trae fortalezas por
   contexto (el simulador aplica el mismo efecto del proveedor en todas partes).
   Se "siembran" dos conocidas y se verifica que el modelo las encuentra y no
   inventa otras.

Uso:
    python validar_modelo1.py            # base y carpeta según config/fuente_datos.yaml
"""

import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from configuracion import BASE_DATOS, DIR_M1, HOJA_ENVIOS
from modelo1_fiabilidad import ModeloFiabilidad, Parametros, preparar

CORTE = pd.Timestamp("2026-03-31")


def efectos_rapidos(base: ModeloFiabilidad, train: pd.DataFrame, params: Parametros) -> ModeloFiabilidad:
    """Reutiliza el modelo de dificultad ya entrenado y solo recalcula los efectos."""
    m = ModeloFiabilidad(params)
    m.fecha_corte = base.fecha_corte
    m.dificultad = base.dificultad
    m.vars_cat = base.vars_cat
    if params.dimensiones:  # mismas dimensiones extra que el modelo base (p. ej. tipo_contenedor)
        params.dimensiones = list(params.dimensiones) + [x for x in base.p.dimensiones if x not in params.dimensiones]
    d = m.agregar_residuos(train)
    m.ajustar_efectos(d)
    return m


def metricas(y, p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return {"brier": brier_score_loss(y, p), "log_loss": log_loss(y, p), "auc": roc_auc_score(y, p)}


def prueba_tiempo(envios, salida):
    d = preparar(envios)
    train, test = d[d["fecha_orden"] <= CORTE], d[d["fecha_orden"] > CORTE]
    y = test["puntualidad"].to_numpy()

    completo = ModeloFiabilidad().ajustar(envios, fecha_corte=CORTE)
    train = completo.datos  # ya tiene residuos y pesos
    solo_prov = efectos_rapidos(completo, train, Parametros(dimensiones=[]))

    pred_comp = completo.predecir(test)
    pred_prov = solo_prov.predecir(test)
    tasa_prov = train.groupby("proveedor")["puntualidad"].mean()

    candidatos = {
        "A. Tasa global (todos iguales)": np.full(len(test), train["puntualidad"].mean()),
        "B. % a tiempo histórico del proveedor": test["proveedor"].map(tasa_prov).to_numpy(),
        "C. Solo dificultad del envío": pred_comp["base_puntualidad"].to_numpy(),
        "D. Dificultad + proveedor": pred_prov["pred_puntualidad"].to_numpy(),
        "E. Modelo completo (+ contextos)": pred_comp["pred_puntualidad"].to_numpy(),
    }
    filas = []
    for nombre, p in candidatos.items():
        filas.append({"modelo": nombre, **metricas(y, p)})
    tabla = pd.DataFrame(filas)
    rmse = np.sqrt(np.mean((test["fiabilidad"].to_numpy() - pred_comp["pred_fiabilidad"].to_numpy()) ** 2))

    # Sensibilidad a los parámetros (vida media y fuerza de la corrección)
    grid = []
    for vida, m_p, m_c in itertools.product([3, 6, 12, 1e6], [5, 50, 200], [5, 50, 100, 300]):
        m = efectos_rapidos(completo, train, Parametros(vida_media_meses=vida, m_proveedor=m_p, m_contexto=m_c))
        p = m.predecir(test)["pred_puntualidad"].to_numpy()
        grid.append({"vida_media_meses": "sin decaimiento" if vida > 1000 else vida,
                     "m_proveedor": m_p, "m_contexto": m_c, **metricas(y, p)})
    grid = pd.DataFrame(grid).sort_values("log_loss")
    grid.to_csv(Path(salida) / "validacion_sensibilidad.csv", index=False, encoding="utf-8-sig")
    return tabla, rmse, grid, len(train), len(test)


def prueba_verdad(envios, verdad):
    modelo = ModeloFiabilidad().ajustar(envios)
    ef = modelo.efectos["proveedor"]["ef_puntualidad"]
    bruto = preparar(envios).groupby("proveedor")["puntualidad"].mean()
    t = pd.DataFrame({"efecto_verdadero": verdad, "efecto_estimado_pts": 100 * ef, "a_tiempo_bruto_pct": 100 * bruto})
    t = t.sort_values("efecto_verdadero", ascending=False)
    rho_modelo = t["efecto_verdadero"].corr(t["efecto_estimado_pts"], method="spearman")
    rho_bruto = t["efecto_verdadero"].corr(t["a_tiempo_bruto_pct"], method="spearman")
    return t.round(2), rho_modelo, rho_bruto, modelo


def prueba_pocos_datos(modelo, repeticiones=300, semilla=7):
    """Reduce los envíos de un proveedor a N y mira si queda (falsamente) #1."""
    rng = np.random.default_rng(semilla)
    d = modelo.datos
    mejor = modelo.ranking.iloc[0]["proveedor"]
    m = modelo.p.m_proveedor
    filas = []
    for n in [10, 20, 50, 100]:
        falsos_bruto = falsos_modelo = total = 0
        for prov in modelo.proveedores:
            if prov == mejor:
                continue
            idx_p = d.index[d["proveedor"] == prov].to_numpy()
            resto = d[d["proveedor"] != prov]
            # Estadísticos del resto (fijos)
            tasa_resto = resto.groupby("proveedor")["puntualidad"].mean()
            g = resto.groupby("proveedor")
            ef_resto = (g.apply(lambda x: (x["peso_tiempo"] * x["res_puntualidad"]).sum(), include_groups=False)
                        / (g["peso_tiempo"].sum() + m))
            for _ in range(repeticiones):
                s = d.loc[rng.choice(idx_p, size=n, replace=False)]
                tasa = s["puntualidad"].mean()
                ef = (s["peso_tiempo"] * s["res_puntualidad"]).sum() / (s["peso_tiempo"].sum() + m)
                falsos_bruto += tasa > tasa_resto.max()
                falsos_modelo += ef > ef_resto.max()
                total += 1
        filas.append({"envios_del_proveedor": n,
                      "veces_falso_1_tasa_bruta_pct": round(100 * falsos_bruto / total, 1),
                      "veces_falso_1_modelo_pct": round(100 * falsos_modelo / total, 1)})
    return pd.DataFrame(filas), mejor


SEMBRADAS = [
    # (proveedor, columna, valor, tipo, proporción de envíos que se cambian)
    ("Envía", "contenido", "Medicamentos", "Fortaleza", 0.5),
    ("Coordinadora", "zona", "especial", "Debilidad", 0.3),
]


def sembradas_para(envios):
    """Ajusta la lista a la versión de la base (la base con contenedores no tiene 'Medicamentos')."""
    if "contenido" not in envios and "categoria_carga" in envios:
        return [("Envía", "contenido", "Retail", "Fortaleza", 0.5), SEMBRADAS[1]]
    return SEMBRADAS


def sembrar(envios, semilla=11):
    rng = np.random.default_rng(semilla)
    e = envios.copy()
    if "contenido" not in e and "categoria_carga" in e:
        e["contenido"] = e["categoria_carga"]
    for prov, col, valor, tipo, prop in sembradas_para(envios):
        objetivo = 0 if tipo == "Fortaleza" else 1  # se cambian envíos tarde→a tiempo, o al revés
        idx = e.index[(e["proveedor"] == prov) & (e[col] == valor) & (e["a_tiempo"] == objetivo)]
        sel = rng.choice(idx, size=int(prop * len(idx)), replace=False)
        e.loc[sel, "a_tiempo"] = 1 - objetivo
        e.loc[sel, "transito_real_h"] = e.loc[sel, "transito_prometido_h"] * (0.9 if tipo == "Fortaleza" else 1.4)
    return e


def prueba_sembradas(envios):
    modelo = ModeloFiabilidad().ajustar(sembrar(envios))
    c = modelo.contextos
    hallados = c[c["etiqueta"].isin(["Fortaleza", "Debilidad"])]
    nombre_dim = {"contenido": "Contenido", "zona": "Zona"}
    esperados = {(p, nombre_dim[col], v, t) for p, col, v, t, _ in sembradas_para(envios)}
    encontrados = {(r.proveedor, r.dimension, r.valor, r.etiqueta) for r in hallados.itertuples()}
    return (hallados[["proveedor", "dimension", "valor", "envios", "vs_su_promedio_pts", "z", "etiqueta"]],
            len(esperados & encontrados), len(esperados), len(encontrados - esperados))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default=str(BASE_DATOS))
    ap.add_argument("--salida", default=str(DIR_M1))
    args = ap.parse_args()
    Path(args.salida).mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 200)

    envios = pd.read_excel(args.datos, sheet_name=HOJA_ENVIOS)
    sup = pd.read_excel(args.datos, sheet_name="Supuestos", index_col=0)
    verdad = sup.loc["Efecto proveedor en puntualidad (log-horas)"].astype(float)

    lineas = []
    def out(texto=""):
        print(texto)
        lineas.append(str(texto))

    tabla, rmse, grid, n_tr, n_te = prueba_tiempo(envios, args.salida)
    out(f"1) PRUEBA EN EL TIEMPO — entrena hasta {CORTE.date()} ({n_tr} envíos), predice {n_te} envíos posteriores")
    out("   Brier y log-loss: menor es mejor · AUC: mayor es mejor (0,5 = azar)\n")
    out(tabla.round(4).to_string(index=False))
    out("\n   Sensibilidad a parámetros — 5 mejores combinaciones (log-loss):")
    out(grid.head(5).round(4).to_string(index=False))
    pd_ = Parametros()
    defecto = grid[(grid["vida_media_meses"] == pd_.vida_media_meses) & (grid["m_proveedor"] == pd_.m_proveedor)
                   & (grid["m_contexto"] == pd_.m_contexto)]
    out(f"   Parámetros por defecto ({pd_.vida_media_meses:g} meses, m_proveedor={pd_.m_proveedor:g}, "
        f"m_contexto={pd_.m_contexto:g}): log-loss {defecto['log_loss'].iloc[0]:.4f}, "
        f"puesto {grid.index.get_loc(defecto.index[0]) + 1} de {len(grid)}")

    t, rho_m, rho_b, modelo = prueba_verdad(envios, verdad)
    out("\n2) RECUPERACIÓN DE LOS PARÁMETROS VERDADEROS (efecto real en puntualidad)\n")
    out(t.to_string())
    out(f"\n   Correlación de orden (Spearman) con la verdad — modelo: {rho_m:.2f} · tasa bruta: {rho_b:.2f}")

    pocos, mejor = prueba_pocos_datos(modelo)
    out(f"\n3) POCOS DATOS — % de veces que un proveedor con N envíos aparece por error como #1 (el verdadero #1 es {mejor})\n")
    out(pocos.to_string(index=False))

    hallados, ok, total, falsos = prueba_sembradas(envios)
    out("\n4) FORTALEZAS Y DEBILIDADES SEMBRADAS")
    for p, col, v, t, prop in sembradas_para(envios):
        out(f"   Sembrada: {t} de {p} en {col} = {v} ({int(prop * 100)} % de sus envíos ahí cambiados)")
    out("\n   Lo que encontró el modelo:")
    out(hallados.to_string(index=False))
    out(f"\n   Detectadas {ok} de {total} sembradas. Otros hallazgos: {falsos} (pueden ser diferencias propias de la base")
    out("   o efectos secundarios de lo sembrado: revisarlos antes de presentarlos)")

    (Path(args.salida) / "validacion.txt").write_text("\n".join(lineas), encoding="utf-8")
    print(f"\nResultados guardados en {Path(args.salida).resolve()}")
