"""
MODELO 1 — Fiabilidad / reputación de proveedores
==================================================

Responde a la pregunta: "¿qué tan confiable es este proveedor, en general y
para este tipo de envío en particular?" a partir del historial de envíos.

El puntaje de fiabilidad (0-100) combina cuatro componentes medidos en cada envío:

    componente          qué mide                                         peso
    ------------------  -----------------------------------------------  ----
    puntualidad         ¿llegó dentro del plazo prometido? (sí/no)        40 %
    magnitud_retraso    si llegó tarde, ¿qué tan tarde? (0 = el doble     20 %
                        del tiempo prometido o más, 1 = a tiempo)
    integridad          ¿llegó sin daños?                                 25 %
    satisfaccion        calificación del cliente 1-5, llevada a 0-1       15 %

Cuatro correcciones hacen que el puntaje sea justo y explicable:

1. AJUSTE POR DIFICULTAD. No todos los envíos son igual de difíciles (una zona
   especial o un envío exprés en temporada alta fallan más para cualquiera). Un
   modelo de referencia, entrenado sin la variable proveedor, calcula qué
   resultado se esperaría de un proveedor promedio en cada envío. El proveedor
   se mide por cuánto supera o queda por debajo de ese valor esperado.

2. CORRECCIÓN POR POCOS DATOS (promedio bayesiano). Cada efecto se calcula como
       suma(diferencias) / (envíos + m)
   Con muchos envíos, m casi no pesa; con pocos, el efecto se acerca a 0 (el
   proveedor se trata como uno promedio hasta que haya evidencia).

3. PESO DEL TIEMPO. Los envíos recientes cuentan más: un envío de hace
   VIDA_MEDIA meses pesa la mitad que uno de hoy.

4. FORTALEZAS Y DEBILIDADES POR CONTEXTO. Además del efecto general, se mide
   el efecto extra de cada proveedor por zona, contenido, tipo de carga,
   velocidad, ruta y temporada, con la misma corrección por pocos datos.
   Un contexto se etiqueta "Fortaleza" o "Debilidad" solo si la diferencia
   observada es de al menos 2 puntos y supera una prueba estadística con
   control de falsos hallazgos (Benjamini-Hochberg, q <= 0,10).

Resultado para un envío concreto (lo que usa el Modelo 2):

    fiabilidad = dificultad del envío            (igual para todos los proveedores)
               + desempeño general del proveedor
               + ajustes por contexto (zona, contenido, ruta, ...)

Uso:
    python modelo1_fiabilidad.py            # base y carpeta de salida según config/fuente_datos.yaml
"""

from __future__ import annotations

import argparse
import pickle
from math import erfc, sqrt
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

from configuracion import BASE_DATOS, COMPONENTES_FIABILIDAD, DIR_M1, HOJA_ENVIOS, PERFILES

# --------------------------------------------------------------------------
# Configuración. Los pesos de los componentes están en config/perfiles.yaml
# (entrenamiento.pesos_fiabilidad); el resto de parámetros, aquí.
# --------------------------------------------------------------------------

PESOS = dict(PERFILES["entrenamiento"]["pesos_fiabilidad"])
COMPONENTES = list(COMPONENTES_FIABILIDAD)
BINARIOS = {"puntualidad", "integridad"}
NOMBRE_COMPONENTE = {
    "puntualidad": "Puntualidad",
    "magnitud_retraso": "Retrasos cortos",
    "integridad": "Carga sin daños",
    "satisfaccion": "Satisfacción del cliente",
}

# Variables que describen la dificultad del envío (nunca incluyen al proveedor)
VARS_CATEGORICAS = ["zona", "tipo_carga", "contenido", "nivel_velocidad", "origen", "destino"]
VARS_NUMERICAS = ["temporada_alta", "fragil", "log_kg", "log_km"]

# Contextos donde se buscan fortalezas y debilidades
DIMENSIONES = ["zona", "tipo_carga", "contenido", "nivel_velocidad", "ruta", "temporada"]
# Columnas que se usan automáticamente si la base las trae (p. ej. la versión con contenedores)
OPCIONALES = ["tipo_contenedor"]
NOMBRE_DIMENSION = {
    "zona": "Zona",
    "tipo_carga": "Tipo de carga",
    "contenido": "Contenido",
    "nivel_velocidad": "Velocidad",
    "ruta": "Ruta",
    "temporada": "Temporada",
    "tipo_contenedor": "Contenedor",
}

UMBRAL_PUNTOS = 2.0   # diferencia mínima (en puntos de 0-100) para hablar de fortaleza/debilidad
Z_MINIMO = 1.96       # y que sea estadísticamente clara (95 %)
MIN_ENVIOS_CONTEXTO = 10
# Hay cientos de combinaciones proveedor × contexto: probadas al 95 % una por una, ~5 %
# saldrían "significativas" por azar. Se controla la tasa de falsos hallazgos con el
# método de Benjamini-Hochberg (una familia de pruebas por dimensión): en cada
# dimensión, como máximo ~10 % de las etiquetas serían falsas.
Q_MAXIMO = 0.10

# Nivel de confianza según "envíos equivalentes" (envíos ponderados por antigüedad).
# Umbrales apoyados en la hoja M6 de la base: con menos de ~50 envíos el ranking
# acierta al mejor proveedor apenas la mitad de las veces.
CONFIANZA = [(300, "Alta"), (50, "Media"), (0, "Baja")]

MESES_RECIENTES = 3   # ventana para la tendencia: últimos 3 meses...
MESES_PREVIOS = 9     # ...comparados con los 9 anteriores


@dataclass
class Parametros:
    vida_media_meses: float = 6.0   # un envío de hace 6 meses pesa la mitad
    # Regla simple de explicar: con m envíos equivalentes, el historial propio pesa la mitad
    m_proveedor: float = 50.0       # "envíos ficticios" promedio para el efecto general
    m_contexto: float = 50.0        # ídem para cada contexto
    dimensiones: list = field(default_factory=lambda: list(DIMENSIONES))
    iteraciones: int = 5


# --------------------------------------------------------------------------
# Preparación de datos
# --------------------------------------------------------------------------

def preparar(envios: pd.DataFrame) -> pd.DataFrame:
    """Crea las variables derivadas. Funciona con o sin columnas de resultado."""
    d = envios.copy()
    # La base con contenedores llama "categoria_carga" a lo que la primera versión llamaba "contenido"
    if "contenido" not in d and "categoria_carga" in d:
        d["contenido"] = d["categoria_carga"]
    if "fecha_orden" in d:
        d["fecha_orden"] = pd.to_datetime(d["fecha_orden"])
    d["ruta"] = d["origen"].astype(str) + " → " + d["destino"].astype(str)
    d["temporada"] = np.where(d["temporada_alta"] == 1, "alta", "normal")
    d["log_kg"] = np.log1p(d["peso_total_kg"])
    d["log_km"] = np.log1p(d["distancia_km"])

    if "a_tiempo" in d:  # columnas de resultado (solo en el historial)
        ratio = d["transito_real_h"] / d["transito_prometido_h"]
        d["puntualidad"] = d["a_tiempo"].astype(float)
        d["magnitud_retraso"] = 1 - np.clip(ratio - 1, 0, 1)
        d["integridad"] = 1 - d["danado"].astype(float)
        d["satisfaccion"] = (d["satisfaccion_1a5"] - 1) / 4
        d["fiabilidad"] = sum(PESOS[c] * d[c] for c in COMPONENTES)
    return d


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """Valores q: control de la tasa de falsos hallazgos al probar muchos contextos."""
    n = len(p)
    orden = np.argsort(p)
    q = p[orden] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    salida = np.empty(n)
    salida[orden] = np.minimum(q, 1)
    return salida


def nivel_confianza(envios_equivalentes: float) -> str:
    for minimo, etiqueta in CONFIANZA:
        if envios_equivalentes >= minimo:
            return etiqueta
    return "Baja"


# --------------------------------------------------------------------------
# Modelo
# --------------------------------------------------------------------------

class ModeloFiabilidad:
    def __init__(self, params: Parametros | None = None):
        self.p = params or Parametros()
        self.cols = COMPONENTES + ["fiabilidad"]

    # ---------------- entrenamiento ----------------

    def ajustar(self, envios: pd.DataFrame, fecha_corte=None) -> "ModeloFiabilidad":
        d = preparar(envios)
        self.fecha_corte = pd.Timestamp(fecha_corte) if fecha_corte else d["fecha_orden"].max()
        d = d[d["fecha_orden"] <= self.fecha_corte].copy()
        self.proveedores = sorted(d["proveedor"].unique())
        extra = [c for c in OPCIONALES if c in d.columns]
        self.vars_cat = VARS_CATEGORICAS + extra
        self.p.dimensiones = list(self.p.dimensiones) + [c for c in extra if c not in self.p.dimensiones]

        self.ajustar_dificultad(d)
        d = self.agregar_residuos(d)
        self.ajustar_efectos(d)
        self._resumir(d)
        self.datos = d
        return self

    def ajustar_dificultad(self, d: pd.DataFrame) -> None:
        """Modelo de referencia: resultado esperado de un proveedor promedio."""
        self.dificultad = {}
        for c in COMPONENTES:
            prep = ColumnTransformer([
                ("cat", OneHotEncoder(handle_unknown="ignore"), self.vars_cat),
                ("num", "passthrough", VARS_NUMERICAS),
            ])
            reg = LogisticRegression(max_iter=2000) if c in BINARIOS else Ridge(alpha=1.0)
            modelo = make_pipeline(prep, reg)
            modelo.fit(d[self.vars_cat + VARS_NUMERICAS], d[c])
            self.dificultad[c] = modelo

    def esperado(self, d: pd.DataFrame) -> pd.DataFrame:
        X = d[getattr(self, "vars_cat", VARS_CATEGORICAS) + VARS_NUMERICAS]
        e = pd.DataFrame(index=d.index)
        for c in COMPONENTES:
            m = self.dificultad[c]
            e[c] = m.predict_proba(X)[:, 1] if c in BINARIOS else np.clip(m.predict(X), 0, 1)
        e["fiabilidad"] = sum(PESOS[c] * e[c] for c in COMPONENTES)
        return e

    def agregar_residuos(self, d: pd.DataFrame) -> pd.DataFrame:
        d = d.copy()
        e = self.esperado(d)
        for c in self.cols:
            d[f"esp_{c}"] = e[c]
            d[f"res_{c}"] = d[c] - e[c]
        edad_meses = (self.fecha_corte - d["fecha_orden"]).dt.days / 30.44
        d["peso_tiempo"] = 0.5 ** (edad_meses / self.p.vida_media_meses)
        return d

    def _terminos(self, d: pd.DataFrame):
        yield "proveedor", d["proveedor"].astype(str), self.p.m_proveedor
        for dim in self.p.dimensiones:
            yield dim, d["proveedor"].astype(str) + "|" + d[dim].astype(str), self.p.m_contexto

    def ajustar_efectos(self, d: pd.DataFrame) -> None:
        """Efecto general del proveedor + efectos por contexto (backfitting).

        Cada efecto se estima sobre lo que los demás no explican, así un mismo
        fenómeno (p. ej. ruta y zona) no se cuenta dos veces.

        Los efectos por contexto se CENTRAN dentro de cada proveedor: su promedio
        ponderado es 0. Sin esto, los contextos de un proveedor (p. ej. temporada
        alta + normal, que cubren todos sus envíos) se "repartirían" su efecto
        general, y el ranking subestimaría las diferencias entre proveedores.
        """
        R = d[[f"res_{c}" for c in self.cols]].to_numpy()
        w = d["peso_tiempo"].to_numpy()
        cod_prov, _ = pd.factorize(d["proveedor"].astype(str))
        peso_prov = np.bincount(cod_prov, weights=w)
        terminos = []
        for nombre, clave, m in self._terminos(d):
            codigos, valores = pd.factorize(clave)
            terminos.append((nombre, codigos, valores, m))

        aporte = {t[0]: np.zeros_like(R) for t in terminos}
        efectos_finales = {}
        total = np.zeros_like(R)
        for _ in range(self.p.iteraciones):
            for nombre, codigos, valores, m in terminos:
                parcial = R - (total - aporte[nombre])
                efecto = self._promedio_bayesiano(codigos, len(valores), w, parcial, m)
                if nombre != "proveedor":
                    efecto = self._centrar_por_proveedor(efecto, codigos, cod_prov, w, peso_prov)
                nuevo = efecto[codigos]
                total += nuevo - aporte[nombre]
                aporte[nombre] = nuevo
                efectos_finales[nombre] = efecto

        # Tablas finales con error estándar aproximado
        self.efectos = {}
        for nombre, codigos, valores, m in terminos:
            parcial = R - (total - aporte[nombre])
            k = len(valores)
            suma_w = np.bincount(codigos, weights=w, minlength=k)
            n = np.bincount(codigos, minlength=k)
            efecto = self._promedio_bayesiano(codigos, k, w, parcial, m)
            media_g = np.column_stack([
                np.bincount(codigos, weights=w * parcial[:, j], minlength=k) for j in range(R.shape[1])
            ]) / suma_w[:, None]
            media2_g = np.column_stack([
                np.bincount(codigos, weights=w * parcial[:, j] ** 2, minlength=k) for j in range(R.shape[1])
            ]) / suma_w[:, None]
            var_g = np.maximum(media2_g - media_g ** 2, 0)
            var_global = np.average(parcial ** 2, axis=0, weights=w)
            var = (suma_w[:, None] * var_g + m * var_global) / (suma_w[:, None] + m)
            se = np.sqrt(var / (suma_w[:, None] + m))
            # Diferencia observada (sin corrección) y su error, para la prueba estadística
            suma_w2 = np.bincount(codigos, weights=w ** 2, minlength=k)
            se_obs = np.sqrt(var_global[None, :] * suma_w2[:, None]) / suma_w[:, None]
            efecto = efectos_finales.get(nombre, efecto)

            tabla = pd.DataFrame(index=pd.Index(valores, name="clave"))
            tabla["envios"] = n
            tabla["envios_equivalentes"] = suma_w
            for j, c in enumerate(self.cols):
                tabla[f"ef_{c}"] = efecto[:, j]
                tabla[f"se_{c}"] = se[:, j]
                tabla[f"obs_{c}"] = media_g[:, j]
                tabla[f"se_obs_{c}"] = se_obs[:, j]
            self.efectos[nombre] = tabla

    @staticmethod
    def _centrar_por_proveedor(efecto, codigos, cod_prov, w, peso_prov):
        """Resta a cada efecto de contexto el promedio ponderado de su proveedor."""
        nuevo = efecto[codigos]
        media_prov = np.column_stack([
            np.bincount(cod_prov, weights=w * nuevo[:, j], minlength=len(peso_prov)) for j in range(nuevo.shape[1])
        ]) / peso_prov[:, None]
        prov_de_grupo = np.zeros(len(efecto), dtype=int)
        prov_de_grupo[codigos] = cod_prov
        return efecto - media_prov[prov_de_grupo]

    @staticmethod
    def _promedio_bayesiano(codigos, k, w, valores, m):
        den = np.bincount(codigos, weights=w, minlength=k) + m
        num = np.column_stack([
            np.bincount(codigos, weights=w * valores[:, j], minlength=k) for j in range(valores.shape[1])
        ])
        return num / den[:, None]

    # ---------------- resúmenes ----------------

    def _resumir(self, d: pd.DataFrame) -> None:
        self.base_tipica = {c: d[f"esp_{c}"].mean() for c in self.cols}
        self.tendencias = self._tendencias(d)
        self.contextos = self._tabla_contextos(d)
        self.mensual = self._tabla_mensual(d)
        self.ranking = self._tabla_ranking(d)

    def _tendencias(self, d: pd.DataFrame) -> pd.DataFrame:
        fin = self.fecha_corte
        ini_rec = fin - pd.DateOffset(months=MESES_RECIENTES)
        ini_prev = ini_rec - pd.DateOffset(months=MESES_PREVIOS)
        filas = []
        for prov, g in d.groupby("proveedor"):
            rec = g.loc[g["fecha_orden"] > ini_rec, "res_fiabilidad"]
            prev = g.loc[(g["fecha_orden"] > ini_prev) & (g["fecha_orden"] <= ini_rec), "res_fiabilidad"]
            if len(rec) < 10 or len(prev) < 10:
                filas.append((prov, np.nan, "Sin datos suficientes"))
                continue
            dif = rec.mean() - prev.mean()
            se = np.sqrt(rec.var() / len(rec) + prev.var() / len(prev))
            z = dif / se if se > 0 else 0
            if dif * 100 >= UMBRAL_PUNTOS and z >= Z_MINIMO:
                etiqueta = "Mejorando"
            elif dif * 100 <= -UMBRAL_PUNTOS and z <= -Z_MINIMO:
                etiqueta = "Empeorando"
            else:
                etiqueta = "Estable"
            filas.append((prov, dif * 100, etiqueta))
        return pd.DataFrame(filas, columns=["proveedor", "cambio_reciente_pts", "tendencia"]).set_index("proveedor")

    def _tabla_contextos(self, d: pd.DataFrame) -> pd.DataFrame:
        ef_prov = self.efectos["proveedor"]
        filas = []
        for dim in self.p.dimensiones:
            tabla = self.efectos[dim]
            esp_ctx = d.groupby(dim)[["esp_fiabilidad", "esp_puntualidad"]].mean()
            for valor in esp_ctx.index:
                for prov in self.proveedores:
                    clave = f"{prov}|{valor}"
                    fila = tabla.loc[clave] if clave in tabla.index else None
                    n = int(fila["envios"]) if fila is not None else 0
                    ef = fila["ef_fiabilidad"] if fila is not None else 0.0
                    obs = fila["obs_fiabilidad"] if fila is not None else np.nan
                    z_obs = obs / fila["se_obs_fiabilidad"] if fila is not None else np.nan
                    ef_p = fila["ef_puntualidad"] if fila is not None else 0.0
                    abs_f = esp_ctx.loc[valor, "esp_fiabilidad"] + ef_prov.loc[prov, "ef_fiabilidad"] + ef
                    abs_p = esp_ctx.loc[valor, "esp_puntualidad"] + ef_prov.loc[prov, "ef_puntualidad"] + ef_p
                    filas.append({
                        "proveedor": prov,
                        "dimension": NOMBRE_DIMENSION.get(dim, dim),
                        "valor": valor,
                        "envios": n,
                        "envios_equivalentes": round(float(fila["envios_equivalentes"]), 1) if fila is not None else 0.0,
                        "fiabilidad_en_contexto": round(100 * np.clip(abs_f, 0, 1), 1),
                        "prob_a_tiempo_en_contexto": round(100 * np.clip(abs_p, 0, 1), 1),
                        "vs_su_promedio_pts": round(100 * ef, 2),
                        "diferencia_observada_pts": round(100 * obs, 2),
                        "z": round(z_obs, 2),
                        "p_valor": erfc(abs(z_obs) / sqrt(2)) if fila is not None else np.nan,
                    })
        t = pd.DataFrame(filas)
        if t.empty:  # modelo sin dimensiones de contexto
            return pd.DataFrame(columns=["proveedor", "dimension", "valor", "envios", "vs_su_promedio_pts",
                                         "etiqueta"])
        # ¿Cómo queda frente a los demás proveedores en ese mismo contexto?
        media_ctx = t.groupby(["dimension", "valor"])["fiabilidad_en_contexto"].transform("mean")
        t["vs_competencia_pts"] = (t["fiabilidad_en_contexto"] - media_ctx).round(2)
        t["posicion_en_contexto"] = (
            t.groupby(["dimension", "valor"])["fiabilidad_en_contexto"].rank(ascending=False, method="min").astype(int)
        )
        evaluables = t["envios"] >= MIN_ENVIOS_CONTEXTO
        t["q_valor"] = np.nan
        for dim in t["dimension"].unique():  # una familia de pruebas por dimensión
            filas_dim = evaluables & (t["dimension"] == dim)
            if filas_dim.any():
                t.loc[filas_dim, "q_valor"] = benjamini_hochberg(t.loc[filas_dim, "p_valor"].to_numpy())
        t["etiqueta"] = t.apply(self._etiqueta_contexto, axis=1)
        t["p_valor"] = t["p_valor"].round(5)
        t["q_valor"] = t["q_valor"].round(4)
        return t

    @staticmethod
    def _etiqueta_contexto(f) -> str:
        if f["envios"] == 0:
            return "Sin historial"
        if f["envios"] < MIN_ENVIOS_CONTEXTO:
            return "Pocos datos"
        if f["q_valor"] <= Q_MAXIMO and f["diferencia_observada_pts"] >= UMBRAL_PUNTOS:
            return "Fortaleza"
        if f["q_valor"] <= Q_MAXIMO and f["diferencia_observada_pts"] <= -UMBRAL_PUNTOS:
            return "Debilidad"
        return "Normal"

    def _tabla_mensual(self, d: pd.DataFrame) -> pd.DataFrame:
        g = d.groupby(["proveedor", "mes"])
        t = pd.DataFrame({
            "envios": g.size(),
            "a_tiempo_pct": 100 * g["a_tiempo"].mean(),
            "danado_pct": 100 * g["danado"].mean(),
            "satisfaccion_media_1a5": g["satisfaccion_1a5"].mean(),
            "horas_retraso_medias_si_tarde": g.apply(
                lambda x: (x.loc[x["a_tiempo"] == 0, "transito_real_h"]
                           - x.loc[x["a_tiempo"] == 0, "transito_prometido_h"]).mean(),
                include_groups=False),
            "fiabilidad_bruta": 100 * g["fiabilidad"].mean(),
            "fiabilidad_ajustada": 100 * (self.base_tipica["fiabilidad"] + g["res_fiabilidad"].mean()),
        }).reset_index()
        return t.round(2)

    def _tabla_ranking(self, d: pd.DataFrame) -> pd.DataFrame:
        ef = self.efectos["proveedor"]
        bruto = d.groupby("proveedor")[self.cols].mean()
        filas = []
        for prov in self.proveedores:
            e = ef.loc[prov]
            fila = {
                "proveedor": prov,
                "envios": int(e["envios"]),
                "envios_equivalentes": round(e["envios_equivalentes"], 1),
                "confianza": nivel_confianza(e["envios_equivalentes"]),
            }
            for c in self.cols:
                fila[f"{c}_ajustada"] = round(100 * (self.base_tipica[c] + e[f"ef_{c}"]), 1)
            fila["fiabilidad_ic95_inf"] = round(100 * (self.base_tipica["fiabilidad"] + e["ef_fiabilidad"] - 1.96 * e["se_fiabilidad"]), 1)
            fila["fiabilidad_ic95_sup"] = round(100 * (self.base_tipica["fiabilidad"] + e["ef_fiabilidad"] + 1.96 * e["se_fiabilidad"]), 1)
            fila["a_tiempo_bruto_pct"] = round(100 * bruto.loc[prov, "puntualidad"], 1)
            fila["fiabilidad_bruta"] = round(100 * bruto.loc[prov, "fiabilidad"], 1)
            fila["cambio_reciente_pts"] = round(self.tendencias.loc[prov, "cambio_reciente_pts"], 2)
            fila["tendencia"] = self.tendencias.loc[prov, "tendencia"]
            # Perfil por componente: ¿en qué es mejor o peor que el proveedor promedio?
            fuertes, debiles = [], []
            for c in COMPONENTES:
                dif = e[f"ef_{c}"] - ef[f"ef_{c}"].mean()
                z = dif / e[f"se_{c}"] if e[f"se_{c}"] > 0 else 0
                texto = f"{NOMBRE_COMPONENTE[c]} ({100 * dif:+.1f} pts vs. promedio)"
                if z >= Z_MINIMO:
                    fuertes.append((dif, texto))
                elif z <= -Z_MINIMO:
                    debiles.append((dif, texto))
            fila["fortalezas"] = "; ".join(t for _, t in sorted(fuertes, reverse=True)) or "—"
            fila["debilidades"] = "; ".join(t for _, t in sorted(debiles)) or "—"
            # Fortalezas y debilidades específicas por contexto (frente a su propio promedio)
            ctx = self.contextos[self.contextos["proveedor"] == prov]
            fz = ctx[ctx["etiqueta"] == "Fortaleza"].nlargest(3, "vs_su_promedio_pts")
            db = ctx[ctx["etiqueta"] == "Debilidad"].nsmallest(3, "vs_su_promedio_pts")
            fila["fortalezas_por_contexto"] = "; ".join(f"{r.dimension} {r.valor} ({r.vs_su_promedio_pts:+.1f} pts)" for r in fz.itertuples()) or "—"
            fila["debilidades_por_contexto"] = "; ".join(f"{r.dimension} {r.valor} ({r.vs_su_promedio_pts:+.1f} pts)" for r in db.itertuples()) or "—"
            filas.append(fila)
        t = pd.DataFrame(filas).sort_values("fiabilidad_ajustada", ascending=False)
        t.insert(0, "posicion", range(1, len(t) + 1))
        return t.reset_index(drop=True)

    # ---------------- predicción (lo que consume el Modelo 2) ----------------

    def predecir(self, envios: pd.DataFrame) -> pd.DataFrame:
        """Fiabilidad esperada de cada fila (envío + proveedor). Devuelve columnas
        base_* (dificultad), aporte_<termino>_* y pred_* en escala 0-1."""
        d = preparar(envios)
        e = self.esperado(d)
        out = pd.DataFrame(index=d.index)
        total = pd.DataFrame(0.0, index=d.index, columns=self.cols)
        for nombre, clave, _ in self._terminos(d):
            tabla = self.efectos[nombre]
            for c in self.cols:
                aporte = clave.map(tabla[f"ef_{c}"]).fillna(0.0).to_numpy()
                total[c] += aporte
                if c in ("fiabilidad", "puntualidad"):
                    out[f"aporte_{nombre}_{c}"] = aporte
        for c in self.cols:
            out[f"base_{c}"] = e[c]
            out[f"pred_{c}"] = np.clip(e[c] + total[c], 0, 1)
        return out

    def puntuar_envio(self, envio: dict, proveedores: list | None = None) -> list[dict]:
        """Fiabilidad de cada proveedor para un envío, con su explicación."""
        proveedores = proveedores or self.proveedores
        filas = pd.DataFrame([{**envio, "proveedor": p} for p in proveedores])
        pred = self.predecir(filas)
        prep = preparar(filas)
        resultados = []
        for i, prov in enumerate(proveedores):
            r = pred.iloc[i]
            ef_p = self.efectos["proveedor"]
            n_eq = ef_p.loc[prov, "envios_equivalentes"] if prov in ef_p.index else 0.0
            desglose = [{"concepto": "Dificultad de este tipo de envío (proveedor promedio)",
                         "puntos": float(round(100 * r["base_fiabilidad"], 1))},
                        {"concepto": f"Desempeño general de {prov}",
                         "puntos": float(round(100 * r["aporte_proveedor_fiabilidad"], 1))}]
            notas = []
            menores = 0.0
            for dim in self.p.dimensiones:
                valor = prep.iloc[i][dim]
                clave = f"{prov}|{valor}"
                tabla = self.efectos[dim]
                n_ctx = int(tabla.loc[clave, "envios"]) if clave in tabla.index else 0
                pts = 100 * r[f"aporte_{dim}_fiabilidad"]
                if n_ctx == 0:
                    notas.append(f"Sin historial en {NOMBRE_DIMENSION[dim].lower()} '{valor}': se usa su desempeño general.")
                if abs(pts) >= 0.5:
                    desglose.append({"concepto": f"{NOMBRE_DIMENSION[dim]}: {valor} ({n_ctx} envíos)",
                                     "puntos": float(round(pts, 1))})
                else:
                    menores += pts
            if abs(menores) >= 0.05:
                desglose.append({"concepto": "Otros ajustes menores", "puntos": float(round(menores, 1))})
            resultados.append({
                "proveedor": prov,
                "fiabilidad": float(round(100 * r["pred_fiabilidad"], 1)),
                "prob_a_tiempo": float(round(100 * r["pred_puntualidad"], 1)),
                "prob_sin_danos": float(round(100 * r["pred_integridad"], 1)),
                "confianza": nivel_confianza(n_eq),
                "tendencia": self.tendencias["tendencia"].get(prov, "Sin datos suficientes"),
                "desglose": desglose,
                "notas": notas,
            })
        return sorted(resultados, key=lambda x: -x["fiabilidad"])

    # ---------------- persistencia ----------------

    def guardar(self, carpeta: str | Path) -> None:
        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        self.ranking.to_csv(carpeta / "fiabilidad_ranking.csv", index=False, encoding="utf-8-sig")
        self.contextos.to_csv(carpeta / "fiabilidad_contextos.csv", index=False, encoding="utf-8-sig")
        self.mensual.to_csv(carpeta / "fiabilidad_mensual.csv", index=False, encoding="utf-8-sig")
        datos = self.__dict__.pop("datos", None)
        with open(carpeta / "modelo1.pkl", "wb") as f:
            pickle.dump(self, f)
        if datos is not None:
            self.datos = datos

    @staticmethod
    def cargar(ruta: str | Path) -> "ModeloFiabilidad":
        with open(ruta, "rb") as f:
            return pickle.load(f)


def imprimir_explicacion(resultados: list[dict], top: int = 3) -> None:
    for r in resultados[:top]:
        print(f"\n  {r['proveedor']}: fiabilidad {r['fiabilidad']} · a tiempo {r['prob_a_tiempo']}% · "
              f"confianza {r['confianza']} · {r['tendencia']}")
        for k, item in enumerate(r["desglose"]):
            valor = f"{item['puntos']:.1f}" if k == 0 else f"{item['puntos']:+.1f}"
            print(f"      {valor:>6}  {item['concepto']}")
        for nota in r["notas"]:
            print(f"      nota: {nota}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Modelo 1: fiabilidad de proveedores")
    ap.add_argument("--datos", default=str(BASE_DATOS))
    ap.add_argument("--hoja", default=HOJA_ENVIOS)
    ap.add_argument("--salida", default=str(DIR_M1))
    args = ap.parse_args()

    # Importar la clase desde el módulo (y no desde __main__) para que modelo1.pkl
    # se pueda cargar después desde otros scripts, p. ej. el Modelo 2 o Streamlit.
    from modelo1_fiabilidad import ModeloFiabilidad as Modelo

    envios = pd.read_excel(args.datos, sheet_name=args.hoja)
    modelo = Modelo().ajustar(envios)
    modelo.guardar(args.salida)

    pd.set_option("display.width", 200)
    print("\nRANKING DE FIABILIDAD (ajustado por dificultad, 0-100)\n")
    print(modelo.ranking[["posicion", "proveedor", "envios", "confianza", "fiabilidad_ajustada",
                          "fiabilidad_ic95_inf", "fiabilidad_ic95_sup", "puntualidad_ajustada",
                          "a_tiempo_bruto_pct", "tendencia"]].to_string(index=False))

    ejemplo = envios.iloc[1].to_dict()
    print(f"\nEJEMPLO — envío {ejemplo['id_envio']}: {ejemplo['origen']} → {ejemplo['destino']}, "
          f"{ejemplo.get('contenido', ejemplo.get('categoria_carga'))}, {ejemplo['tipo_carga']}, zona {ejemplo['zona']}")
    imprimir_explicacion(modelo.puntuar_envio(ejemplo))
    print(f"\nArchivos guardados en: {Path(args.salida).resolve()}")
