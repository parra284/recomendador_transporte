"""
MODELO 2 — Recomendación de proveedor para una solicitud de transporte
=======================================================================

El operario escribe el código de una solicitud y el sistema devuelve un top 3
explicado. La persona de operaciones sigue tomando la decisión final.

Cómo decide, en cuatro pasos:

1. FILTROS DUROS (catálogo de capacidades, derivado del historial):
   contenedor que maneja el proveedor, ciudades que cubre, peso máximo que ha
   atendido EN ESE CONTENEDOR, velocidades que ofrece CON ESE CONTENEDOR,
   combinaciones velocidad-zona posibles y cupos disponibles esta semana.
   Cada exclusión queda con su motivo y el conteo del historial que la respalda.
   `python verificar_catalogo.py` comprueba que ninguna regla contradiga el historial.

2. ESTIMACIONES para cada proveedor que pasa los filtros:
   - Precio y tiempo esperados: modelos entrenados con el historial
     (se compara Ridge con gradient boosting y gana el más simple si empatan).
   - Fiabilidad: el MODELO 1 (ajustada por dificultad, con corrección por pocos
     datos, peso del tiempo y fortalezas por contexto).

3. PUNTAJE con escalas fijas (no relativas a los demás candidatos):
       precio:     100 × (1,5 − precio / precio de mercado), entre 0 y 100
       tiempo:     100 × (1,5 − tiempo / tiempo de mercado), entre 0 y 100
       fiabilidad: el puntaje 0-100 del Modelo 1
   "De mercado" = lo que costaría o tardaría un proveedor promedio en ese mismo
   envío. Un proveedor 20 % más barato que el mercado saca 70 en precio.

4. PESOS según el perfil del envío:
   - base por tipo de contenedor (pesos del equipo: a tiempo + sin daño +
     satisfacción se agrupan en "fiabilidad", que ya los combina el Modelo 1);
   - la velocidad pedida (prio, exp, same) y un plazo ajustado suben el peso
     del tiempo.

Si la solicitud trae plazo, se calcula la probabilidad de llegar dentro de él
(columna "En plazo", con el error del modelo de tiempo) y se avisa cuando un
proveedor del top promete más tiempo que el plazo o lo cumple menos del 70 % de
las veces. "A tiempo" sigue siendo cumplir la promesa del propio proveedor.

Si nadie cumple, el sistema propone alternativas (otra velocidad o un proveedor
sin cupo) y dice qué cambia. También avisa empates, riesgo de no cumplir el
plazo y concentración de envíos en un proveedor.

Correcciones frente a la primera versión del Modelo 2:
- Ya no usa los parámetros ocultos del simulador (factores de tiempo, tarifas
  por zona): todo se estima con el historial, como se haría con datos reales.
- Las reglas de velocidad salen de los datos (la versión anterior excluía a
  4-72, Envía y Grupo TCC de velocidades que sí han atendido cientos de veces).
- Puntualidad, daños y satisfacción vienen del Modelo 1 en lugar de modelos
  sin corrección por pocos datos.
- Escalas fijas en lugar de min-max entre candidatos, y puntaje en lugar de un
  "% de afinidad" que parecía una probabilidad.
- Se agregan capacidad semanal, explicación por factor, alternativas y avisos.
- Catálogo por proveedor Y contenedor (oct-2026): la versión anterior aceptaba
  combinaciones que nunca ocurrieron (Flat Rack mismo día en Coordinadora y
  Grupo TCC, Open Top mismo día en Grupo TCC) y pesos por encima de lo movido en
  ese contenedor (p. ej. Reefer de 6 t en Grupo TCC, cuyo máximo Reefer es 900 kg).

Uso:
    python modelo2_recomendador.py --entrenar
    python modelo2_recomendador.py --codigo T-002
    python modelo2_recomendador.py --demo
"""

from __future__ import annotations

import argparse
import pickle
import warnings
from dataclasses import dataclass
from math import erf, log, sqrt
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import configuracion
from configuracion import (BASE_DATOS, DIR_M2, HOJA_ENVIOS, PERFILES, SOLICITUDES_PRUEBA, escribir_huella,
                           modelo_al_dia)
from modelo1_fiabilidad import ModeloFiabilidad

warnings.filterwarnings("ignore")

# --------------------------------------------------------------------------
# Configuración: los valores vienen de config/perfiles.yaml (ver configuracion.py)
# --------------------------------------------------------------------------

# Pesos por tipo de contenedor (los del equipo; a_tiempo + sin_daño + satisfacción = fiabilidad)
PESOS_PERFIL = {c: dict(p) for c, p in PERFILES["pesos_por_contenedor"].items()}
# Cuánto peso gana el tiempo según la velocidad pedida (luego se renormaliza a 100 %)
EXTRA_TIEMPO_VELOCIDAD = dict(PERFILES["extra_tiempo_por_velocidad"])
# Plazo ajustado: si plazo / tiempo de mercado < HOLGURA_AJUSTADA, el tiempo gana EXTRA_TIEMPO_HOLGURA de peso
HOLGURA_AJUSTADA = PERFILES["plazo"]["holgura_ajustada"]
EXTRA_TIEMPO_HOLGURA = PERFILES["plazo"]["extra_tiempo"]

FACTORES = list(configuracion.FACTORES)
NOMBRE_FACTOR = {"precio": "Precio", "tiempo": "Tiempo", "fiabilidad": "Fiabilidad"}
VELOCIDADES = list(configuracion.VELOCIDADES)  # de más rápida a más lenta
NOMBRE_VELOCIDAD = {"same": "mismo día", "exp": "exprés", "prio": "prioritaria", "std": "estándar"}

MIN_SERVICIOS = PERFILES["entrenamiento"]["min_servicios"]      # para decir que un proveedor "ofrece" algo
EMPATE_PUNTOS = PERFILES["avisos"]["empate_puntos"]             # diferencias menores = empate técnico
CONCENTRACION_MAX = PERFILES["avisos"]["concentracion_max"]     # cuota máxima de envíos recientes / del lote
PROB_PLAZO_MIN = PERFILES["avisos"]["prob_plazo_min"]           # aviso si llega en plazo menos que esto
SEMILLA_CAPACIDAD = PERFILES["entrenamiento"]["semilla_capacidad"]

VARS_CAT = ["zona", "tipo_contenedor", "tipo_carga", "nivel_velocidad", "temporada"]
VARS_CAT_PROV = ["proveedor", "prov_zona", "prov_cont", "prov_vel"]
VARS_NUM = ["log_kg", "log_km", "bultos_unidades", "seguro", "fragil", "log_valor", "t"]


# --------------------------------------------------------------------------
# Preparación de solicitudes
# --------------------------------------------------------------------------

def variables_cotizador(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    fecha = pd.to_datetime(d["fecha_orden"])
    d["t"] = (fecha.dt.year - 2024) * 12 + fecha.dt.month - 10   # meses desde oct-2024 (inflación)
    d["temporada"] = np.where(d["temporada_alta"] == 1, "alta", "normal")
    d["log_kg"] = np.log1p(d["peso_total_kg"])
    d["log_km"] = np.log1p(d["distancia_km"])
    d["log_valor"] = np.log1p(d["valor_declarado_cop"])
    if "proveedor" in d:
        d["prov_zona"] = d["proveedor"] + "|" + d["zona"]
        d["prov_cont"] = d["proveedor"] + "|" + d["tipo_contenedor"]
        d["prov_vel"] = d["proveedor"] + "|" + d["nivel_velocidad"]
    return d


# --------------------------------------------------------------------------
# Etapa 1: catálogo de capacidades y capacidad semanal
# --------------------------------------------------------------------------

@dataclass
class Catalogo:
    """Qué puede atender cada proveedor, derivado SOLO del historial.

    Reglas (todas con el mismo umbral MIN_SERVICIOS = "lo ha hecho al menos 5 veces"):
      - contenedor: el proveedor lo ha movido >= 5 veces;
      - velocidad: >= 5 servicios con ESE contenedor y ESA velocidad (no se
        combinan por separado contenedor y velocidad: evita aceptar, p. ej.,
        Flat Rack mismo día en un proveedor que nunca lo ha hecho);
      - peso: hasta el máximo que ha movido en ESE contenedor (no el máximo
        global del proveedor);
      - ciudades: las que ha atendido como origen o destino;
      - velocidad-zona: combinaciones que existen en el historial de cualquier
        proveedor (mismo día solo local; exprés nunca en zona especial).
    Lo que tiene entre 1 y 4 servicios se publica como "ocasional" con su
    conteo: no se recomienda, pero el catálogo no dice que nunca ocurrió.
    """
    contenedores: dict        # proveedor -> {contenedores con >= MIN_SERVICIOS}
    servicios: dict           # (proveedor, contenedor) -> envíos en el historial
    combos: dict              # (proveedor, contenedor, velocidad) -> envíos en el historial
    ciudades: dict            # proveedor -> {ciudades atendidas como origen o destino}
    peso_max: dict            # (proveedor, contenedor) -> kg máximos atendidos
    vel_zona_posibles: set
    rutas: pd.DataFrame
    contenedor_de_categoria: dict

    @classmethod
    def desde_historial(cls, env: pd.DataFrame) -> "Catalogo":
        provs = sorted(env["proveedor"].unique())
        servicios = env.groupby(["proveedor", "tipo_contenedor"]).size().to_dict()
        ciudades = {p: set(env.loc[env.proveedor == p, "origen"]) | set(env.loc[env.proveedor == p, "destino"])
                    for p in provs}
        return cls(
            contenedores={p: {c for (q, c), n in servicios.items() if q == p and n >= MIN_SERVICIOS} for p in provs},
            servicios=servicios,
            combos=env.groupby(["proveedor", "tipo_contenedor", "nivel_velocidad"]).size().to_dict(),
            ciudades=ciudades,
            peso_max=env.groupby(["proveedor", "tipo_contenedor"])["peso_total_kg"].max().to_dict(),
            vel_zona_posibles=set(map(tuple, env[["nivel_velocidad", "zona"]].drop_duplicates().to_numpy())),
            rutas=env.groupby(["origen", "destino"]).agg(distancia_km=("distancia_km", "median"),
                                                         zona=("zona", "first")),
            contenedor_de_categoria=env.groupby("categoria_carga")["tipo_contenedor"].agg(
                lambda s: s.mode().iat[0]).to_dict(),
        )

    def ofrece(self, p: str, contenedor: str, velocidad: str) -> bool:
        return self.combos.get((p, contenedor, velocidad), 0) >= MIN_SERVICIOS

    def tabla(self) -> pd.DataFrame:
        """Una fila por proveedor y contenedor, con los conteos que respaldan cada regla."""
        todas = set().union(*self.ciudades.values())
        conts = sorted({c for (_, c) in self.servicios})
        filas = []
        for p in sorted(self.ciudades):
            for c in conts:
                n = self.servicios.get((p, c), 0)
                ofrece = c in self.contenedores[p]
                vel_n = {v: self.combos.get((p, c, v), 0) for v in VELOCIDADES}
                fmt = lambda vs: ", ".join(f"{v} ({vel_n[v]})" for v in vs) or "—"
                filas.append({
                    "proveedor": p,
                    "tipo_contenedor": c,
                    "servicios": n,
                    "maneja_contenedor": "sí" if ofrece else ("ocasional" if n else "no"),
                    "velocidades_ofrecidas": fmt([v for v in VELOCIDADES if ofrece and vel_n[v] >= MIN_SERVICIOS]),
                    "velocidades_ocasionales": fmt([v for v in VELOCIDADES if 0 < vel_n[v] < MIN_SERVICIOS]),
                    "velocidades_sin_historial": (", ".join(v for v in VELOCIDADES if vel_n[v] == 0) or "—") if n else "todas",
                    "peso_max_atendido_kg": round(self.peso_max[(p, c)], 1) if n else None,
                    "ciudades_cubiertas": len(self.ciudades[p]),
                    "ciudades_sin_cobertura": ", ".join(sorted(todas - self.ciudades[p])) or "—",
                })
        return pd.DataFrame(filas)

    def motivos_exclusion(self, s: dict, p: str, capacidad: pd.DataFrame | None) -> list[str]:
        m = []
        c, v = s["tipo_contenedor"], s["nivel_velocidad"]
        n_cont = self.servicios.get((p, c), 0)
        if c not in self.contenedores[p]:
            m.append(f"No maneja contenedor {c}" +
                     (f" ({n_cont} servicios en el historial; mínimo {MIN_SERVICIOS})" if n_cont else ""))
        for ciudad in {s["origen"], s["destino"]}:
            if ciudad not in self.ciudades[p]:
                m.append(f"No cubre {ciudad}")
        if c in self.contenedores[p]:
            if s["peso_total_kg"] > self.peso_max[(p, c)]:
                m.append(f"Peso {s['peso_total_kg']:,.0f} kg supera su máximo atendido en {c} "
                         f"({self.peso_max[(p, c)]:,.0f} kg)")
            if not self.ofrece(p, c, v):
                n = self.combos.get((p, c, v), 0)
                m.append(f"No ofrece velocidad {NOMBRE_VELOCIDAD[v]} con {c} "
                         f"({n} servicios en el historial; mínimo {MIN_SERVICIOS})")
        if (s["nivel_velocidad"], s["zona"]) not in self.vel_zona_posibles:
            m.append(f"Velocidad {NOMBRE_VELOCIDAD[s['nivel_velocidad']]} no es posible en zona {s['zona']}")
        if capacidad is not None:
            fila = capacidad[(capacidad.proveedor == p) & (capacidad.tipo_contenedor == s["tipo_contenedor"])]
            if not fila.empty and fila["disponibles"].iat[0] <= 0:
                m.append(f"Sin cupos esta semana para {s['tipo_contenedor']}")
        return m


def capacidad_simulada(env: pd.DataFrame, catalogo: Catalogo, semilla=SEMILLA_CAPACIDAD) -> pd.DataFrame:
    """Cupos semanales por proveedor y contenedor.

    SIMULADA: la base no trae capacidad. Cupos = percentil 90 de su volumen
    semanal histórico × 1,15. Comprometidos = un porcentaje al azar entre 55 % y
    95 %, salvo un caso lleno a propósito (Coordinadora Reefer) para mostrar en la
    demo qué pasa cuando el mejor proveedor no tiene capacidad.
    """
    rng = np.random.default_rng(semilla)
    sem = pd.to_datetime(env["fecha_orden"]).dt.to_period("W")
    vol = env.assign(semana=sem).groupby(["proveedor", "tipo_contenedor", "semana"]).size()
    filas = []
    for (p, c), serie in vol.groupby(level=[0, 1]):
        if c not in catalogo.contenedores[p]:
            continue
        cupos = int(np.ceil(serie.quantile(0.9) * 1.15))
        comprometidos = int(round(cupos * rng.uniform(0.55, 0.95)))
        if (p, c) == ("Coordinadora", "Reefer"):
            comprometidos = cupos
        filas.append({"proveedor": p, "tipo_contenedor": c, "cupos_semana": cupos,
                      "comprometidos": comprometidos, "disponibles": cupos - comprometidos})
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------
# Etapa 3a: cotizador (precio y tiempo esperados)
# --------------------------------------------------------------------------

class Cotizador:
    """Estima precio, tiempo prometido y tiempo real con el historial.

    Para cada variable entrena dos modelos: uno CON proveedor (lo que cobraría o
    tardaría ese proveedor) y otro SIN proveedor (el "mercado": un proveedor
    promedio en ese envío), que sirve de referencia para la escala del puntaje.
    """
    OBJETIVOS = {"precio": "precio_cop", "prometido": "transito_prometido_h", "tiempo": "transito_real_h"}

    def __init__(self):
        self.modelos, self.sigma, self.comparacion = {}, {}, None

    @staticmethod
    def _pipe(algoritmo, con_proveedor):
        cats = VARS_CAT + (VARS_CAT_PROV if con_proveedor else [])
        prep = ColumnTransformer([("num", StandardScaler(), VARS_NUM),
                                  ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cats)])
        reg = Ridge(alpha=1.0) if algoritmo == "Ridge" else HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.08, random_state=0)
        return make_pipeline(prep, reg), cats

    def ajustar(self, env: pd.DataFrame, corte="2026-03-31") -> "Cotizador":
        d = variables_cotizador(env)
        tr, te = d[pd.to_datetime(d.fecha_orden) <= corte], d[pd.to_datetime(d.fecha_orden) > corte]
        filas = []
        self.algoritmo = {}
        for nombre, col in self.OBJETIVOS.items():
            res = {}
            for alg in ["Ridge", "Gradient boosting"]:
                pipe, cats = self._pipe(alg, True)
                pipe.fit(tr[VARS_NUM + cats], np.log(tr[col]))
                pred = pipe.predict(te[VARS_NUM + cats])
                y = np.log(te[col])
                res[alg] = r2_score(y, pred)
                filas.append({"variable": nombre, "modelo": alg, "R2_prueba": r2_score(y, pred),
                              "error_medio_pct": 100 * (np.exp(mean_absolute_error(y, pred)) - 1)})
            # gana el más simple salvo que el complejo mejore el R² en al menos 0,005
            self.algoritmo[nombre] = "Gradient boosting" if res["Gradient boosting"] - res["Ridge"] >= 0.005 else "Ridge"
        self.comparacion = pd.DataFrame(filas)
        self.comparacion["elegido"] = self.comparacion.apply(
            lambda r: "sí" if self.algoritmo[r["variable"]] == r["modelo"] else "", axis=1)

        for nombre, col in self.OBJETIVOS.items():
            for con_prov in (True, False):
                pipe, cats = self._pipe(self.algoritmo[nombre], con_prov)
                pipe.fit(d[VARS_NUM + cats], np.log(d[col]))
                resid = np.log(d[col]) - pipe.predict(d[VARS_NUM + cats])
                clave = (nombre, con_prov)
                self.modelos[clave], self.sigma[clave] = (pipe, cats), float(resid.std())
        return self

    def estimar(self, d: pd.DataFrame, nombre: str, con_proveedor: bool) -> np.ndarray:
        pipe, cats = self.modelos[(nombre, con_proveedor)]
        s = self.sigma[(nombre, con_proveedor)]
        # exp(predicción + σ²/2): corrige el sesgo de volver de la escala logarítmica
        return np.exp(pipe.predict(variables_cotizador(d)[VARS_NUM + cats]) + s ** 2 / 2)


# --------------------------------------------------------------------------
# Etapa 3b: recomendador
# --------------------------------------------------------------------------

def escala(valor, referencia):
    """1,5 − valor/referencia, llevado a 0-100: igual al mercado = 50, 50 % menos = 100, 50 % más = 0."""
    return float(np.clip(1.5 - valor / referencia, 0, 1) * 100)


class Recomendador:
    def __init__(self, m1, cotizador, catalogo, capacidad, historial, solicitudes_prueba=None):
        self.m1, self.cot, self.cat, self.cap = m1, cotizador, catalogo, capacidad
        self.hist = historial
        self.pruebas = solicitudes_prueba if solicitudes_prueba is not None else pd.DataFrame()
        fin = pd.to_datetime(historial["fecha_orden"]).max()
        recientes = historial[pd.to_datetime(historial["fecha_orden"]) > fin - pd.Timedelta(days=28)]
        self.cuota_reciente = (recientes["proveedor"].value_counts(normalize=True)).to_dict()

    # ----- entrenamiento -----

    @classmethod
    def entrenar(cls, env: pd.DataFrame, solicitudes_prueba=None) -> "Recomendador":
        print("Entrenando Modelo 1 (fiabilidad)...")
        m1 = ModeloFiabilidad().ajustar(env)
        print("Entrenando cotizador (precio y tiempo)...")
        cot = Cotizador().ajustar(env)
        cat = Catalogo.desde_historial(env)
        cap = capacidad_simulada(env, cat)
        return cls(m1, cot, cat, cap, env, solicitudes_prueba)

    # ----- solicitudes -----

    def solicitud(self, codigo: str) -> dict:
        for tabla in (self.pruebas, self.hist):
            if len(tabla) and codigo in set(tabla["id_envio"]):
                s = tabla.loc[tabla["id_envio"] == codigo].iloc[0].to_dict()
                if "proveedor" in s:  # solicitud histórica: guardamos lo que se eligió en su momento
                    s["proveedor_historico"] = s.pop("proveedor")
                return self.completar(s)
        raise KeyError(f"No encuentro la solicitud {codigo}")

    def completar(self, s: dict) -> dict:
        """Rellena lo que se puede deducir: contenedor, distancia, zona, tipo de carga, temporada."""
        s = dict(s)
        if pd.isna(s.get("tipo_contenedor")) or not s.get("tipo_contenedor"):
            s["tipo_contenedor"] = self.cat.contenedor_de_categoria[s["categoria_carga"]]
        s["peso_total_kg"] = s.get("peso_total_kg") or s["peso_por_bulto_kg"] * s["bultos_unidades"]
        if pd.isna(s.get("distancia_km")) or pd.isna(s.get("zona")) or not s.get("zona"):
            ruta = self.cat.rutas.loc[(s["origen"], s["destino"])]
            s["distancia_km"], s["zona"] = float(ruta["distancia_km"]), ruta["zona"]
        if pd.isna(s.get("tipo_carga")) or not s.get("tipo_carga"):
            s["tipo_carga"] = ("Paletizada" if s["tipo_contenedor"] == "Flat Rack" or s["peso_por_bulto_kg"] >= 150
                               else "Paquete")
        fecha = pd.Timestamp(s.get("fecha_orden") or pd.Timestamp.today().normalize())
        s["fecha_orden"] = fecha
        s.setdefault("temporada_alta", int(fecha.month in (11, 12)))
        if pd.isna(s["temporada_alta"]):
            s["temporada_alta"] = int(fecha.month in (11, 12))
        for campo, defecto in (("fragil", 0), ("seguro", 1), ("valor_declarado_cop", 1_000_000)):
            if campo not in s or pd.isna(s[campo]):
                s[campo] = defecto
        s["plazo_h"] = s.get("plazo_h") if s.get("plazo_h") and not pd.isna(s.get("plazo_h")) else None
        return s

    # ----- pesos -----

    def pesos(self, s: dict, tiempo_mercado: float) -> tuple[dict, list[str]]:
        w = dict(PESOS_PERFIL[s["tipo_contenedor"]])
        motivos = [f"Base para contenedor {s['tipo_contenedor']}: precio {w['precio']:.0%}, "
                   f"tiempo {w['tiempo']:.0%}, fiabilidad {w['fiabilidad']:.0%}"]
        extra = EXTRA_TIEMPO_VELOCIDAD[s["nivel_velocidad"]]
        if extra:
            w["tiempo"] += extra
            motivos.append(f"Velocidad {NOMBRE_VELOCIDAD[s['nivel_velocidad']]}: el tiempo gana {extra:.0%} de peso")
        if s.get("plazo_h") and s["plazo_h"] / tiempo_mercado < HOLGURA_AJUSTADA:
            w["tiempo"] += EXTRA_TIEMPO_HOLGURA
            motivos.append(f"Plazo ajustado ({s['plazo_h']:.0f} h frente a {tiempo_mercado:.0f} h típicas): "
                           f"el tiempo gana {EXTRA_TIEMPO_HOLGURA:.0%} de peso")
        total = sum(w.values())
        w = {k: v / total for k, v in w.items()}
        if len(motivos) > 1:
            motivos.append("Pesos finales (renormalizados a 100 %): " +
                           ", ".join(f"{NOMBRE_FACTOR[k].lower()} {v:.0%}" for k, v in w.items()))
        return w, motivos

    # ----- recomendación -----

    def prob_plazo(self, tiempo_esperado: float, plazo: float | None) -> float:
        """P(tiempo real <= plazo), con el error del modelo de tiempo (log-normal, σ de los residuos).

        Calibrada en los meses de prueba (abr-sep 2026): lo predicho y lo observado difieren 1-3 puntos.
        """
        if not plazo:
            return float("nan")
        s = self.cot.sigma[("tiempo", True)]
        mu = log(tiempo_esperado) - s ** 2 / 2       # tiempo_esperado ya trae la corrección exp(σ²/2)
        return 0.5 * (1 + erf((log(plazo) - mu) / (s * sqrt(2))))

    def _evaluar(self, s: dict, proveedores: list[str]) -> pd.DataFrame:
        filas = pd.DataFrame([{**s, "proveedor": p} for p in proveedores])
        base = pd.DataFrame([s])
        mercado_precio = float(self.cot.estimar(base, "precio", False)[0])
        mercado_tiempo = float(self.cot.estimar(base, "tiempo", False)[0])
        r = pd.DataFrame({"proveedor": proveedores})
        r["precio_cop"] = self.cot.estimar(filas, "precio", True)
        r["tiempo_prometido_h"] = self.cot.estimar(filas, "prometido", True)
        r["tiempo_esperado_h"] = self.cot.estimar(filas, "tiempo", True)
        fiab = {x["proveedor"]: x for x in self.m1.puntuar_envio(s, proveedores=proveedores)}
        r["fiabilidad"] = [fiab[p]["fiabilidad"] for p in proveedores]
        r["prob_a_tiempo"] = [fiab[p]["prob_a_tiempo"] for p in proveedores]
        r["prob_sin_danos"] = [fiab[p]["prob_sin_danos"] for p in proveedores]
        r["confianza"] = [fiab[p]["confianza"] for p in proveedores]
        r["tendencia"] = [fiab[p]["tendencia"] for p in proveedores]
        r["prob_plazo"] = [self.prob_plazo(t, s.get("plazo_h")) for t in r["tiempo_esperado_h"]]
        r["detalle_fiabilidad"] = [fiab[p] for p in proveedores]
        r["precio_vs_mercado_pct"] = 100 * (r["precio_cop"] / mercado_precio - 1)
        r["tiempo_vs_mercado_pct"] = 100 * (r["tiempo_esperado_h"] / mercado_tiempo - 1)
        r["pts_precio"] = [escala(v, mercado_precio) for v in r["precio_cop"]]
        r["pts_tiempo"] = [escala(v, mercado_tiempo) for v in r["tiempo_esperado_h"]]
        r["pts_fiabilidad"] = r["fiabilidad"]
        r.attrs.update(mercado_precio=mercado_precio, mercado_tiempo=mercado_tiempo)
        return r

    def recomendar(self, s: dict, top: int = 3, usar_cupos: bool = True) -> dict:
        """Top de proveedores para una solicitud. Con usar_cupos=False no se filtra por cupos
        (lo usa la asignación por lotes, que maneja los cupos como restricción conjunta)."""
        s = self.completar(s)
        excluidos, candidatos = {}, []
        for p in self.m1.proveedores:
            motivos = self.cat.motivos_exclusion(s, p, self.cap if usar_cupos else None)
            (excluidos.__setitem__(p, motivos) if motivos else candidatos.append(p))

        resultado = {"solicitud": s, "excluidos": excluidos, "avisos": [], "alternativas": None}
        if not candidatos:
            resultado["alternativas"] = self._alternativas(s, excluidos)
            resultado["ranking"] = pd.DataFrame()
            resultado["avisos"].append("Ningún proveedor cumple todos los requisitos: revisar las alternativas.")
            return resultado

        r = self._evaluar(s, candidatos)
        w, motivos_pesos = self.pesos(s, r.attrs["mercado_tiempo"])
        for f in FACTORES:
            r[f"aporte_{f}"] = w[f] * r[f"pts_{f}"]
        r["puntaje"] = r[[f"aporte_{f}" for f in FACTORES]].sum(axis=1)
        r = r.sort_values("puntaje", ascending=False).reset_index(drop=True)
        resultado.update(ranking=r, pesos=w, motivos_pesos=motivos_pesos,
                         mercado_precio=r.attrs.get("mercado_precio"), mercado_tiempo=r.attrs.get("mercado_tiempo"))
        resultado["explicacion"] = self._explicar(r)
        resultado["avisos"] += self._avisos(s, r)
        return resultado

    def _explicar(self, r: pd.DataFrame) -> str:
        a = r.iloc[0]
        if len(r) == 1:
            return f"{a.proveedor} es el único proveedor que cumple todos los requisitos ({a.puntaje:.1f} puntos)."
        b = r.iloc[1]
        partes = []
        for f in FACTORES:
            dif = a[f"aporte_{f}"] - b[f"aporte_{f}"]
            if abs(dif) < 0.3:
                continue
            if f == "precio":
                txt = f"es {abs(a.precio_cop / b.precio_cop - 1):.0%} {'más barato' if a.precio_cop < b.precio_cop else 'más caro'}"
            elif f == "tiempo":
                horas = b.tiempo_esperado_h - a.tiempo_esperado_h
                h_txt = f"{abs(horas):.1f}" if abs(horas) < 3 else f"{abs(horas):.0f}"
                txt = f"llega {h_txt} h {'antes' if horas > 0 else 'después'}"
            else:
                txt = f"es {'más' if a.fiabilidad > b.fiabilidad else 'menos'} fiable ({a.fiabilidad:.0f} frente a {b.fiabilidad:.0f})"
            partes.append(f"{txt} ({dif:+.1f} pts)")
        frase = f"{a.proveedor} queda primero con {a.puntaje:.1f} puntos. Frente a {b.proveedor} ({b.puntaje:.1f}): "
        return frase + ("; ".join(partes) if partes else "las diferencias son mínimas en todos los factores") + "."

    def _avisos(self, s: dict, r: pd.DataFrame) -> list[str]:
        av = []
        if len(r) > 1 and r.puntaje.iat[0] - r.puntaje.iat[1] < EMPATE_PUNTOS:
            av.append(f"Empate técnico: {r.proveedor.iat[0]} y {r.proveedor.iat[1]} están a menos de "
                      f"{EMPATE_PUNTOS:.0f} puntos; ambos son opciones válidas.")
        if s.get("plazo_h"):
            plazo, top3 = s["plazo_h"], r.head(3)
            if (r.prob_plazo < 0.5).all():
                av.append(f"Ningún proveedor tiene más del 50 % de probabilidad de llegar dentro del plazo de {plazo:.0f} h: "
                          f"renegociar el plazo o subir la velocidad.")
            promete_mas = top3[top3.tiempo_prometido_h > plazo]
            if len(promete_mas):
                quien = ", ".join(f"{x.proveedor} ({x.tiempo_prometido_h:.{1 if x.tiempo_prometido_h < 10 else 0}f} h)"
                                 for x in promete_mas.itertuples())
                av.append(f"Promete más tiempo que el plazo de {plazo:.0f} h: {quien}. Su '% a tiempo' se mide contra "
                          f"su propia promesa; para el plazo pedido, ver la columna 'En plazo'.")
            for x in top3[top3.prob_plazo < PROB_PLAZO_MIN].itertuples():
                av.append(f"{x.proveedor} llega dentro del plazo de {plazo:.0f} h solo el {x.prob_plazo:.0%} de las veces "
                          f"(mínimo recomendado {PROB_PLAZO_MIN:.0%}).")
        top = r.proveedor.iat[0]
        if self.cuota_reciente.get(top, 0) > CONCENTRACION_MAX:
            av.append(f"Concentración: {top} ya tiene el {self.cuota_reciente[top]:.0%} de los envíos de las últimas "
                      f"4 semanas (umbral {CONCENTRACION_MAX:.0%}). Si la diferencia es pequeña, considerar la segunda opción.")
        conf = r.confianza.iat[0]
        if conf != "Alta":
            av.append(f"Confianza {conf.lower()} en la fiabilidad de {top}: tiene poco historial.")
        notas = r.detalle_fiabilidad.iat[0]["notas"]
        av += [f"{top}: {n}" for n in notas]
        return av

    def _alternativas(self, s: dict, excluidos: dict) -> pd.DataFrame:
        """Cuando nadie cumple: relaja velocidad o capacidad, y dice qué cambia."""
        opciones = []
        # 1) proveedores cuyo único problema es la capacidad
        for p, motivos in excluidos.items():
            if all(m.startswith("Sin cupos") for m in motivos):
                opciones.append((p, dict(s), "Sin cupos esta semana: confirmar con el proveedor o reprogramar"))
        # 2) una velocidad más lenta que sí sea posible
        i = VELOCIDADES.index(s["nivel_velocidad"])
        for v in VELOCIDADES[i + 1:]:
            s2 = {**s, "nivel_velocidad": v}
            for p in self.m1.proveedores:
                if not self.cat.motivos_exclusion(s2, p, self.cap):
                    opciones.append((p, s2, f"Con velocidad {NOMBRE_VELOCIDAD[v]} en lugar de "
                                            f"{NOMBRE_VELOCIDAD[s['nivel_velocidad']]}"))
            if any(o[1]["nivel_velocidad"] == v for o in opciones):
                break
        if not opciones:
            return pd.DataFrame()
        filas = []
        for p, s2, cambio in opciones:
            r = self._evaluar(s2, [p])
            w, _ = self.pesos(s2, r.attrs["mercado_tiempo"])
            filas.append({"proveedor": p, "que_cambia": cambio,
                          "puntaje": sum(w[f] * r[f"pts_{f}"].iat[0] for f in FACTORES),
                          "precio_cop": r.precio_cop.iat[0], "tiempo_esperado_h": r.tiempo_esperado_h.iat[0],
                          "fiabilidad": r.fiabilidad.iat[0], "prob_plazo": r.prob_plazo.iat[0],
                          **{f"pts_{f}": r[f"pts_{f}"].iat[0] for f in FACTORES},
                          **{f"peso_{f}": w[f] for f in FACTORES}})
        return pd.DataFrame(filas).sort_values("puntaje", ascending=False).reset_index(drop=True)

    # ----- asignación por lotes (ver asignacion_lote.py) -----

    def asignar_lote(self, codigos, **kw) -> dict:
        from asignacion_lote import asignar_lote
        return asignar_lote(codigos, rec=self, **kw)

    # ----- salida en texto -----

    def imprimir(self, res: dict, top: int = 3) -> None:
        s = res["solicitud"]
        print("=" * 90)
        print(f"SOLICITUD {s.get('id_envio', '')}: {s['origen']} → {s['destino']} ({s['zona']}, {s['distancia_km']:.0f} km) · "
              f"{s.get('categoria_carga', '')} · {s['tipo_contenedor']} · {s['bultos_unidades']} × {s['peso_por_bulto_kg']} kg · "
              f"velocidad {NOMBRE_VELOCIDAD[s['nivel_velocidad']]}" + (f" · plazo {s['plazo_h']:.0f} h" if s.get("plazo_h") else ""))
        r = res["ranking"]
        if r.empty:
            print("\n  Ningún proveedor cumple todos los requisitos.")
            alt = res["alternativas"]
            if alt is None or alt.empty:
                print("  Tampoco hay alternativas cercanas: escalar a un supervisor.")
            else:
                print("\n  ALTERNATIVAS:")
                for x in alt.head(top).itertuples():
                    plazo_txt = f" · en plazo {x.prob_plazo:.0%}" if s.get("plazo_h") else ""
                    print(f"   - {x.proveedor}: {x.que_cambia} · {x.puntaje:.1f} pts · ${x.precio_cop:,.0f} · "
                          f"{x.tiempo_esperado_h:.0f} h · fiabilidad {x.fiabilidad:.0f}{plazo_txt}")
                    print("       desglose: " + " + ".join(
                        f"{NOMBRE_FACTOR[f].lower()} {getattr(x, 'pts_' + f):.0f} pts × {getattr(x, 'peso_' + f):.0%} = "
                        f"{getattr(x, 'pts_' + f) * getattr(x, 'peso_' + f):.1f}" for f in FACTORES) + f" → {x.puntaje:.1f}")
        else:
            print("\n  " + " · ".join(res["motivos_pesos"][:1] + res["motivos_pesos"][1:]))
            print(f"  Referencia de mercado: ${res['mercado_precio']:,.0f} · {res['mercado_tiempo']:.0f} h\n")
            con_plazo = bool(s.get("plazo_h"))
            print(f"  {'#':<2} {'Proveedor':<17} {'Puntaje':>7}   {'Precio':>12} {'vs merc.':>8}   {'Tiempo':>7} "
                  f"{'vs merc.':>8}   {'Fiab.':>5} {'A tiempo':>8}" + (f" {'En plazo':>8}" if con_plazo else "") + "   Confianza")
            for i, x in enumerate(r.head(top).itertuples(), 1):
                print(f"  {i:<2} {x.proveedor:<17} {x.puntaje:>7.1f}   ${x.precio_cop:>11,.0f} {x.precio_vs_mercado_pct:>+7.0f}%"
                      f"   {x.tiempo_esperado_h:>5.0f} h {x.tiempo_vs_mercado_pct:>+7.0f}%   {x.fiabilidad:>5.1f} {x.prob_a_tiempo:>7.0f}%"
                      + (f" {x.prob_plazo:>8.0%}" if con_plazo else "") + f"   {x.confianza}")
            if con_plazo:
                print(f"  ('A tiempo' = cumple lo que promete el proveedor; 'En plazo' = llega antes de {s['plazo_h']:.0f} h)")
            print("\n  Desglose (puntos × peso = aporte):")
            for x in r.head(top).itertuples():
                print(f"   {x.proveedor:<17} " + " + ".join(
                    f"{NOMBRE_FACTOR[f].lower()} {getattr(x, 'pts_' + f):.0f} × {res['pesos'][f]:.0%} = {getattr(x, 'aporte_' + f):.1f}"
                    for f in FACTORES) + f" → {x.puntaje:.1f}")
            print(f"  {res['explicacion']}")
        if s.get("proveedor_historico"):
            print(f"  En su momento se eligió {s['proveedor_historico']}: llegó {'a tiempo' if s.get('a_tiempo') == 1 else 'tarde'}"
                  f"{', con daños' if s.get('danado') == 1 else ''}, costó ${s.get('precio_cop', 0):,.0f}.")
        if res["avisos"]:
            print("\n  Avisos:")
            for av in res["avisos"]:
                print(f"   - {av}")
        if res["excluidos"]:
            print("\n  Excluidos:")
            for p, motivos in res["excluidos"].items():
                print(f"   - {p}: {'; '.join(motivos)}")
        print()

    # ----- persistencia -----

    def guardar(self, carpeta=DIR_M2, base=None):
        """Guarda el modelo y sus tablas. Con `base` (la base con la que se entrenó) escribe
        también la huella (fuente_modelo.json) que permite saber si el modelo está al día."""
        carpeta = Path(carpeta)
        carpeta.mkdir(exist_ok=True)
        self.cat.tabla().to_csv(carpeta / "catalogo_proveedores.csv", index=False, encoding="utf-8-sig")
        self.cap.to_csv(carpeta / "capacidad_semana.csv", index=False, encoding="utf-8-sig")
        self.cot.comparacion.round(4).to_csv(carpeta / "comparacion_modelos_precio_tiempo.csv", index=False,
                                             encoding="utf-8-sig")
        datos_m1 = self.m1.__dict__.pop("datos", None)
        with open(carpeta / "modelo2.pkl", "wb") as f:
            pickle.dump(self, f)
        if datos_m1 is not None:
            self.m1.datos = datos_m1
        if base is not None:
            escribir_huella(carpeta, base, self.hist)

    @staticmethod
    def cargar(ruta=DIR_M2 / "modelo2.pkl") -> "Recomendador":
        with open(ruta, "rb") as f:
            rec = pickle.load(f)
        # Los cupos se editan en capacidad_semana.csv (el lote ya los lee de ahí): la
        # recomendación individual usa los mismos, no la copia guardada al entrenar.
        cupos = Path(ruta).parent / "capacidad_semana.csv"
        if cupos.exists():
            rec.cap = pd.read_csv(cupos, encoding="utf-8-sig")
        return rec


if __name__ == "__main__":
    from modelo2_recomendador import Recomendador as R  # para que el .pkl se pueda cargar desde otros scripts

    ap = argparse.ArgumentParser(description="Modelo 2: recomendación de proveedor")
    ap.add_argument("--datos", default=str(BASE_DATOS))
    ap.add_argument("--pruebas", default=str(SOLICITUDES_PRUEBA))
    ap.add_argument("--salida", default=str(DIR_M2))
    ap.add_argument("--entrenar", action="store_true", help="entrena y guarda el modelo")
    ap.add_argument("--codigo", help="código de la solicitud a recomendar")
    ap.add_argument("--demo", action="store_true", help="recomienda todas las solicitudes de prueba")
    ap.add_argument("--lote", help="códigos separados por coma: los reparte entre proveedores respetando "
                                    "cupos y el tope del 35 %%")
    ap.add_argument("--metodo", choices=["auto", "pulp", "voraz"], default="auto",
                    help="auto = programación entera con PuLP si está instalado; si no, heurística voraz")
    args = ap.parse_args()
    pd.set_option("display.width", 200)

    pruebas = pd.read_csv(args.pruebas) if Path(args.pruebas).exists() else None
    pkl = Path(args.salida) / "modelo2.pkl"
    al_dia = modelo_al_dia(Path(args.salida), Path(args.datos))
    if not args.entrenar and pkl.exists() and not al_dia:
        print("El modelo guardado no corresponde a la base, la configuración, el código o las librerías actuales: "
              "se reentrena.")
    if args.entrenar or not al_dia:
        env = pd.read_excel(args.datos, sheet_name=HOJA_ENVIOS)
        rec = R.entrenar(env, pruebas)
        rec.guardar(args.salida, base=args.datos)
        print("\nComparación de modelos para precio y tiempo (datos de prueba, abr-sep 2026):")
        print(rec.cot.comparacion.round(4).to_string(index=False))
        print("\nCatálogo de capacidades (derivado del historial; conteo de envíos entre paréntesis):")
        print(rec.cat.tabla().drop(columns=["ciudades_cubiertas"]).to_string(index=False))
        print(f"\nModelo guardado en {pkl.resolve()}")
    else:
        rec = R.cargar(pkl)
        if pruebas is not None:
            rec.pruebas = pruebas

    if args.codigo:
        rec.imprimir(rec.recomendar(rec.solicitud(args.codigo)))
    if args.demo:
        for codigo in rec.pruebas["id_envio"]:
            rec.imprimir(rec.recomendar(rec.solicitud(codigo)))
    if args.lote:
        from asignacion_lote import asignar_lote, imprimir_lote
        codigos = [c.strip() for c in args.lote.split(",") if c.strip()]
        imprimir_lote(asignar_lote(codigos, rec=rec, metodo=args.metodo,
                                   cupos_csv=Path(args.salida) / "capacidad_semana.csv"))
