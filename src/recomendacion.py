"""Recomendación: llama al Modelo 2 y deja su resultado listo para mostrar.

El Modelo 2 (sistema_proveedores/modelo2_recomendador.py) filtra con el catálogo
derivado del historial, estima precio y tiempo, toma la fiabilidad del Modelo 1 y
pondera con los pesos de config/perfiles.yaml. Aquí no se recalcula nada: solo se
ordena y se da formato a lo que devuelve, para que el dashboard muestre exactamente
lo mismo que el motor.
"""

from dataclasses import dataclass, field

import pandas as pd

from src.motor import asignacion_lote, configuracion, modelo2_recomendador as m2

TAMANO_TOP = 3
FACTORES = m2.FACTORES
NOMBRE_FACTOR = m2.NOMBRE_FACTOR
NOMBRE_VELOCIDAD = m2.NOMBRE_VELOCIDAD


@dataclass
class Recomendacion:
    solicitud: dict                  # completada por el Modelo 2 (contenedor, zona, distancia, peso total)
    ranking: pd.DataFrame            # todos los candidatos, de mayor a menor puntaje
    pesos: dict
    motivos_pesos: list
    explicacion: str | None
    avisos: list
    excluidos: dict                  # {proveedor: [motivos]}
    alternativas: pd.DataFrame       # solo si nadie cumple
    mercado_precio: float | None = None
    mercado_tiempo: float | None = None
    top: pd.DataFrame = field(init=False)

    def __post_init__(self):
        self.top = self.ranking.head(TAMANO_TOP)

    @property
    def con_plazo(self):
        return bool(self.solicitud.get("plazo_h"))

    @property
    def recomendado(self):
        return None if self.ranking.empty else self.ranking.proveedor.iat[0]


# --- Formato ---

def formatear_miles(numero):
    """95168 -> '95.168' (separador de miles colombiano)."""
    return f"{numero:,.0f}".replace(",", ".")


def formatear_cop(numero):
    return f"$ {formatear_miles(numero)}"


def formatear_cambio(pct):
    return f"{pct:+.0f} %"


def formatear_horas(horas):
    return f"{horas:.1f} h" if horas < 10 else f"{horas:.0f} h"


# --- Recomendación ---

def recomendar(rec, solicitud):
    """Ejecuta el Modelo 2 sobre una solicitud (dict en el formato de la base)."""
    r = rec.recomendar(solicitud)
    alternativas = r.get("alternativas")
    return Recomendacion(
        solicitud=r["solicitud"],
        ranking=r["ranking"],
        pesos=r.get("pesos", {}),
        motivos_pesos=r.get("motivos_pesos", []),
        explicacion=r.get("explicacion"),
        avisos=list(r["avisos"]),
        excluidos=dict(r["excluidos"]),
        alternativas=alternativas if alternativas is not None else pd.DataFrame(),
        mercado_precio=r.get("mercado_precio"),
        mercado_tiempo=r.get("mercado_tiempo"),
    )


def solicitud_historica(rec, codigo):
    """Un envío de la base usado como solicitud (incluye quién lo hizo y cómo le fue)."""
    if codigo not in set(rec.hist["id_envio"]):
        raise KeyError(f"El envío {codigo} no está en la base de datos.")
    fila = rec.hist.loc[rec.hist["id_envio"] == codigo].iloc[0].to_dict()
    fila["proveedor_historico"] = fila.pop("proveedor")
    return fila


# --- Tablas para el dashboard ---

def resumen_solicitud(s):
    """Textos del encabezado de la solicitud (después de que el Modelo 2 la completa)."""
    plazo = s.get("plazo_h")
    return {
        "Ruta": f"{s['origen']} → {s['destino']}",
        "Zona": f"{s['zona']} · {s['distancia_km']:.0f} km",
        "Carga": f"{s.get('categoria_carga', '')} · {s['tipo_contenedor']}",
        "Peso": f"{s['bultos_unidades']} × {s['peso_por_bulto_kg']:g} kg = {formatear_miles(s['peso_total_kg'])} kg",
        "Velocidad": NOMBRE_VELOCIDAD[s["nivel_velocidad"]],
        "Plazo": f"{plazo:.0f} h" if plazo else "sin plazo",
        "Valor declarado": formatear_cop(s["valor_declarado_cop"]),
        "Fecha": pd.Timestamp(s["fecha_orden"]).strftime("%Y-%m-%d"),
    }


def tabla_top(r):
    filas = []
    for i, x in enumerate(r.top.itertuples(), start=1):
        fila = {
            "Posición": i,
            "Proveedor": x.proveedor,
            "Puntaje": round(x.puntaje, 1),
            "Precio estimado": formatear_cop(x.precio_cop),
            "Precio vs mercado": formatear_cambio(x.precio_vs_mercado_pct),
            "Tiempo esperado": formatear_horas(x.tiempo_esperado_h),
            "Tiempo vs mercado": formatear_cambio(x.tiempo_vs_mercado_pct),
            "Fiabilidad": round(x.fiabilidad, 1),
            "A tiempo": f"{x.prob_a_tiempo:.0f} %",
        }
        if r.con_plazo:
            fila["En plazo"] = f"{100 * x.prob_plazo:.0f} %"
        fila.update({"Confianza": x.confianza, "Tendencia": x.tendencia})
        filas.append(fila)
    return pd.DataFrame(filas)


def tabla_aportes(r):
    """Formato largo para las barras apiladas: puntos × peso = aporte, por factor."""
    return pd.DataFrame([{
        "Proveedor": x.proveedor,
        "Factor": NOMBRE_FACTOR[f],
        "orden": i,
        "Puntos": round(getattr(x, f"pts_{f}"), 1),
        "Peso": f"{r.pesos[f]:.0%}",
        "Aporte": round(getattr(x, f"aporte_{f}"), 2),
        "Puntaje": round(x.puntaje, 1),
    } for x in r.top.itertuples() for i, f in enumerate(FACTORES)])


def tabla_desglose_fiabilidad(r):
    """De dónde sale la fiabilidad (Modelo 1) de cada proveedor del top."""
    return pd.DataFrame([{"Proveedor": x.proveedor, "Concepto": d["concepto"], "Puntos": d["puntos"]}
                         for x in r.top.itertuples() for d in x.detalle_fiabilidad["desglose"]])


def tabla_excluidos(r):
    return pd.DataFrame([{"Proveedor": p, "Motivos": "; ".join(m)} for p, m in r.excluidos.items()],
                        columns=["Proveedor", "Motivos"])


def tabla_alternativas(r):
    if r.alternativas.empty:
        return pd.DataFrame()
    return pd.DataFrame([{
        "Proveedor": x.proveedor,
        "Qué cambia": x.que_cambia,
        "Puntaje": round(x.puntaje, 1),
        "Precio estimado": formatear_cop(x.precio_cop),
        "Tiempo esperado": formatear_horas(x.tiempo_esperado_h),
        "Fiabilidad": round(x.fiabilidad, 1),
    } for x in r.alternativas.itertuples()])


def comparacion_historica(r):
    """Si la solicitud es un envío de la base: quién lo hizo, cómo le fue y dónde quedó en el ranking."""
    s = r.solicitud
    elegido = s.get("proveedor_historico")
    if not elegido:
        return None
    ranking = list(r.ranking.proveedor)
    if elegido in ranking:
        lugar = f"quedó de {ranking.index(elegido) + 1}.º de {len(ranking)} en el ranking del modelo"
    else:
        lugar = "el modelo lo excluye: " + "; ".join(r.excluidos.get(elegido, []))
    return {
        "proveedor": elegido,
        "resultado": ("llegó a tiempo" if s.get("a_tiempo") == 1 else "llegó tarde")
                     + (", con daños" if s.get("danado") == 1 else ""),
        "precio_pagado": formatear_cop(s.get("precio_cop", 0)),
        "lugar": lugar,
        "coincide": elegido == r.recomendado,
    }


def tabla_general(rec, solicitudes):
    """Una fila por solicitud con el proveedor recomendado."""
    filas = []
    for sol in solicitudes:
        r = recomendar(rec, sol.como_dict())
        s, mejor = r.solicitud, (r.top.iloc[0] if not r.top.empty else None)
        filas.append({
            "Solicitud": sol.id_envio,
            "Ruta": f"{s['origen']} → {s['destino']}",
            "Contenedor": s["tipo_contenedor"],
            "Velocidad": NOMBRE_VELOCIDAD[s["nivel_velocidad"]],
            "Candidatos": len(r.ranking),
            "Recomendado": mejor.proveedor if mejor is not None else "Sin candidatos",
            "Puntaje": round(mejor.puntaje, 1) if mejor is not None else None,
            "Avisos": len(r.avisos),
        })
    return pd.DataFrame(filas)


# --- Lote ---

def asignar_lote(rec, solicitudes, metodo="auto"):
    """Reparte las solicitudes entre proveedores respetando cupos y el tope de concentración."""
    rec.pruebas = pd.DataFrame([s.como_dict() for s in solicitudes])
    lote = asignacion_lote.asignar_lote([s.id_envio for s in solicitudes], rec=rec, metodo=metodo,
                                        cupos_csv=configuracion.DIR_M2 / "capacidad_semana.csv")
    # El motor escribe sus motivos pensando en la línea de comandos.
    lote["detalle"]["motivo"] = lote["detalle"]["motivo"].str.replace(
        "ver alternativas con --codigo", "ver alternativas en la pestaña Recomendación", regex=False)
    return lote


# --- Base y proveedores ---

def describir_base(rec):
    h = rec.hist
    fechas = pd.to_datetime(h["fecha_orden"])
    return {
        "envios": len(h),
        "desde": f"{fechas.min():%Y-%m-%d}",
        "hasta": f"{fechas.max():%Y-%m-%d}",
        "proveedores": sorted(h["proveedor"].unique()),
        "ciudades": len(set(h.origen) | set(h.destino)),
        "contenedores": sorted(h["tipo_contenedor"].unique()),
    }


def tabla_fiabilidad(rec):
    """Ranking general del Modelo 1 (fiabilidad ajustada por dificultad)."""
    t = rec.m1.ranking
    return pd.DataFrame({
        "Posición": t.posicion,
        "Proveedor": t.proveedor,
        "Envíos": t.envios,
        "Fiabilidad": t.fiabilidad_ajustada,
        "IC 95 %": [f"{a:.1f} – {b:.1f}" for a, b in zip(t.fiabilidad_ic95_inf, t.fiabilidad_ic95_sup)],
        "A tiempo (bruto)": [f"{v:.0f} %" for v in t.a_tiempo_bruto_pct],
        "Confianza": t.confianza,
        "Tendencia": t.tendencia,
        "Fortalezas": t.fortalezas,
        "Debilidades": t.debilidades,
    })


def tabla_catalogo(rec):
    """Qué puede atender cada proveedor según el historial (filtros duros del Modelo 2)."""
    t = rec.cat.tabla()
    t = t[t.servicios > 0]
    return pd.DataFrame({
        "Proveedor": t.proveedor,
        "Contenedor": t.tipo_contenedor,
        "Envíos": t.servicios,
        "Lo maneja": t.maneja_contenedor,
        "Velocidades ofrecidas": t.velocidades_ofrecidas,
        "Peso máximo movido (kg)": [formatear_miles(v) for v in t.peso_max_atendido_kg],
        "Ciudades sin cobertura": t.ciudades_sin_cobertura,
    }).reset_index(drop=True)


def tabla_cupos(rec):
    """Cupos de la semana por proveedor y contenedor (capacidad_semana.csv, simulados)."""
    c = rec.cap
    return pd.DataFrame({
        "Proveedor": c.proveedor,
        "Contenedor": c.tipo_contenedor,
        "Cupos": c.cupos_semana,
        "Comprometidos": c.comprometidos,
        "Disponibles": c.disponibles,
    })


def tablas_lote(lote):
    """Tablas del reparto del lote con encabezados para el operario."""
    def texto(v, formato=".1f"):
        return "—" if v is None or pd.isna(v) else format(v, formato)

    d = lote["detalle"]
    detalle = pd.DataFrame({
        "Solicitud": d.codigo,
        "Ruta": d.ruta,
        "Contenedor": d.contenedor,
        "Candidatos": d.candidatos,
        "1.ª opción": d.primera_opcion.fillna("—"),
        "Puntaje 1.ª": [texto(v) for v in d.pts_primera],
        "Asignado": d.asignado.fillna("Sin asignar"),
        "Opción asignada": [texto(v, ".0f") for v in d.opcion_asignada],
        "Puntaje asignado": [texto(v) for v in d.pts_asignado],
        "Pérdida": [texto(v) for v in d.perdida],
        "Motivo": d.motivo,
    })
    if d.proveedor_historico.notna().all():
        detalle.insert(4, "Elegido en su momento", d.proveedor_historico)
    r = lote["resumen"]
    resumen = pd.DataFrame({
        "Escenario": r.escenario,
        "Asignadas": r.asignadas,
        "Sin asignar": r.sin_asignar,
        "Puntaje total": r.puntaje_total.round(1),
        "Puntaje medio": r.puntaje_medio.round(1),
        "Pérdida vs. sin restricciones": r.perdida_vs_sin_restricciones.round(1),
        "Método": r.metodo,
    })
    reparto = lote["reparto"].drop(columns=["pct_sin_restricciones", "pct_con_restricciones"]).rename(
        columns={"proveedor": "Proveedor", "historico_real": "Histórico real"})
    uso = lote["uso_cupos"].rename(columns={
        "proveedor": "Proveedor", "tipo_contenedor": "Contenedor", "cupos_disponibles": "Cupos disponibles",
        "pedidos_sin_restricciones": "Lo piden como 1.ª opción", "asignados": "Asignados", "quedan": "Quedan"})
    return {"detalle": detalle, "resumen": resumen, "reparto": reparto, "uso_cupos": uso}
