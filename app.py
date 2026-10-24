"""Dashboard del recomendador de transportistas terrestres."""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src.ranking import cargar_todo, formatear_precio, recomendar
from src.solicitud import cargar_solicitudes

DIR_DATOS = Path(__file__).resolve().parent / "data"
VARIABLES = ["precio", "tiempo", "confiabilidad", "etiquetas"]
NOMBRES_VARIABLES = {"precio": "Precio", "tiempo": "Tiempo", "confiabilidad": "Confiabilidad",
                     "etiquetas": "Etiquetas"}
# Paleta categórica de referencia (slots 1-4), validada para segmentos apilados adyacentes.
COLORES_VARIABLES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]

st.set_page_config(page_title="Recomendador de transportistas", layout="wide")


@st.cache_resource
def datos_recomendador():
    return cargar_todo()


@st.cache_resource
def solicitudes_de(ruta):
    return cargar_solicitudes(ruta)


def etiqueta_solicitud(s):
    return (f"{s.id_solicitud} · {s.origen} → {s.destino} · {s.tipo_contenedor} · "
            f"{s.fecha_cita:%Y-%m-%d %H:%M}")


def caracteristicas(s):
    especiales = []
    if s.imo:
        especiales.append(f"IMO clase {s.clase_imo:g}")
    if s.refrigerada:
        especiales.append(f"refrigerada {s.temperatura_c:g} °C")
    if s.extradimensionada:
        especiales.append("extradimensionada")
    return ", ".join(especiales) or "carga general"


def mostrar_errores_de_carga(errores):
    if not errores:
        return
    st.warning(f"{len(errores)} fila(s) del archivo tienen errores y no se cargaron.")
    st.dataframe(
        pd.DataFrame([{"Fila": e.fila, "Solicitud": e.id_solicitud, "Campo": e.campo, "Problema": e.mensaje}
                      for e in errores]),
        hide_index=True, width="stretch",
    )


def mostrar_resumen(s, config):
    st.subheader(f"Solicitud {s.id_solicitud}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ruta", f"{s.origen} → {s.destino}")
    c2.metric("Cita", f"{s.fecha_cita:%Y-%m-%d %H:%M}")
    c3.metric("Contenedor", f"{s.tipo_contenedor} · {s.peso_bruto_t:g} t")
    c4.metric("Valor declarado", f"USD {s.valor_declarado_usd:,.0f}".replace(",", "."))
    pesos = config.perfiles[s.prioridad]
    texto_pesos = " · ".join(f"{NOMBRES_VARIABLES[v]} {pesos[v]:.0%}" for v in VARIABLES)
    st.caption(f"Carga: {caracteristicas(s)} · Modalidad: {s.modalidad_aduanera or 'sin indicar'}")
    st.info(f"Perfil aplicado: **{s.prioridad}** — {texto_pesos}")


def tabla_top(top):
    return pd.DataFrame([{
        "Posición": o.posicion,
        "Proveedor": f"{o.id_proveedor} · {o.nombre}",
        "Puntaje": round(o.puntaje.puntaje, 2),
        "Precio (COP)": formatear_precio(o.puntaje.crudos["precio"]),
        "Tiempo estimado": f"{o.puntaje.crudos['tiempo']:g} h"
                           + ("" if o.puntaje.tiempo_desde_historial else " (base)"),
        "% a tiempo": f"{o.puntaje.crudos['confiabilidad']:.0%}",
        "Alertas": "; ".join(o.alertas) or "—",
        "Explicación": o.explicacion,
    } for o in top])


def grafico_aportes(top):
    filas = [{"Proveedor": o.id_proveedor, "Variable": NOMBRES_VARIABLES[v], "orden": i,
              "Aporte": round(o.puntaje.aportes[v], 2), "Puntaje": round(o.puntaje.puntaje, 2)}
             for o in top for i, v in enumerate(VARIABLES)]
    nombres = [NOMBRES_VARIABLES[v] for v in VARIABLES]
    return (
        alt.Chart(pd.DataFrame(filas))
        .mark_bar(stroke="white", strokeWidth=2, cornerRadiusEnd=4)
        .encode(
            y=alt.Y("Proveedor:N", sort=[o.id_proveedor for o in top], title=None),
            x=alt.X("sum(Aporte):Q", title="Puntaje (aporte de cada variable)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("Variable:N", sort=nombres,
                            scale=alt.Scale(domain=nombres, range=COLORES_VARIABLES),
                            legend=alt.Legend(orient="top", title=None)),
            order=alt.Order("orden:Q"),
            tooltip=["Proveedor", "Variable", "Aporte", "Puntaje"],
        )
        .properties(height=60 * len(top) + 40)
    )


def tabla_motivos(evaluaciones):
    return pd.DataFrame([{
        "Proveedor": f"{e.proveedor.id_proveedor} · {e.proveedor.nombre}",
        "Reglas incumplidas": len(e.motivos),
        "Motivos": "; ".join(e.motivos),
    } for e in evaluaciones])


def mostrar_recomendacion(r):
    if not r.top:
        st.error("Ningún proveedor cumple todas las restricciones para esta solicitud.")
        if r.casi_elegibles:
            st.markdown("**Casi elegibles** (fallan una sola regla):")
            st.dataframe(tabla_motivos(r.casi_elegibles), hide_index=True, width="stretch")
    else:
        st.subheader("Top 3 recomendados")
        st.dataframe(tabla_top(r.top), hide_index=True, width="stretch")
        st.altair_chart(grafico_aportes(r.top), width="stretch")
        if len(r.elegibles) > len(r.top):
            st.caption(f"Otros elegibles fuera del top: "
                       f"{', '.join(o.id_proveedor for o in r.elegibles[len(r.top):])}")
    with st.expander(f"Proveedores descartados ({len(r.descartados)})"):
        if r.descartados:
            st.dataframe(tabla_motivos(r.descartados), hide_index=True, width="stretch")
        else:
            st.write("Ninguno.")


def tabla_general(solicitudes, datos):
    filas = []
    for s in solicitudes:
        r = recomendar(s, datos)
        mejor = r.top[0] if r.top else None
        filas.append({
            "Solicitud": s.id_solicitud,
            "Ruta": f"{s.origen} → {s.destino}",
            "Contenedor": s.tipo_contenedor,
            "Cita": f"{s.fecha_cita:%Y-%m-%d %H:%M}",
            "Perfil": s.prioridad,
            "Recomendado": f"{mejor.id_proveedor} · {mejor.nombre}" if mejor else "Sin elegibles",
            "Puntaje": round(mejor.puntaje.puntaje, 2) if mejor else None,
            "Elegibles": len(r.elegibles),
            "Alertas": "; ".join(mejor.alertas) if mejor and mejor.alertas else "—",
        })
    return pd.DataFrame(filas)


# --- Página ---

st.title("Recomendador de transportistas terrestres")
datos = datos_recomendador()

archivos = sorted(p.name for p in DIR_DATOS.glob("solicitudes_*.csv"))
archivo = st.sidebar.selectbox("Archivo de solicitudes", archivos,
                               index=archivos.index("solicitudes_ejemplo.csv") if "solicitudes_ejemplo.csv" in archivos else 0)
solicitudes, errores = solicitudes_de(DIR_DATOS / archivo)
mostrar_errores_de_carga(errores)
if not solicitudes:
    st.stop()

por_id = {s.id_solicitud: s for s in solicitudes}
id_elegido = st.selectbox("Solicitud", list(por_id), format_func=lambda i: etiqueta_solicitud(por_id[i]))
solicitud = por_id[id_elegido]

mostrar_resumen(solicitud, datos.config)
mostrar_recomendacion(recomendar(solicitud, datos))

st.divider()
st.subheader("Todas las solicitudes")
st.dataframe(tabla_general(solicitudes, datos), hide_index=True, width="stretch")
