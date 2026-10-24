"""Dashboard del recomendador de transportistas.

Lee la base de datos (config/fuente_datos.yaml), usa los Modelos 1 y 2 de
sistema_proveedores/ y muestra su resultado. Solo presentación: la lógica está en src/.
"""

import altair as alt
import pandas as pd
import streamlit as st

from src import recomendacion as R
from src.fuente_datos import archivos_solicitudes, cargar_recomendador, info_modelo
from src.motor import configuracion
from src.pantalla_acceso import exigir_acceso
from src.solicitud import cargar_solicitudes, catalogos_desde_envios

# Paleta categórica de referencia (slots 1-3), validada en modo claro y oscuro.
COLORES_FACTORES = {"light": ["#2a78d6", "#eb6834", "#1baf7a"], "dark": ["#3987e5", "#d95926", "#199e70"]}
SUPERFICIE = {"light": "#ffffff", "dark": "#0e1117"}
ENVIO_HISTORICO_EJEMPLO = "S-030106"

st.set_page_config(page_title="Recomendador de transportistas", layout="wide")


# --- Carga (en caché; la huella cambia si cambian la base, la configuración o el motor) ---

@st.cache_resource(show_spinner="Cargando los modelos. Si la base cambió se reentrenan (unos 20 a 40 segundos)...")
def recomendador(huella):
    return cargar_recomendador()


@st.cache_resource
def catalogos(huella, _rec):
    return catalogos_desde_envios(_rec.hist, configuracion.PERFILES["entrenamiento"]["min_servicios"])


@st.cache_resource
def solicitudes_de(ruta, modificado, huella, _catalogos):
    return cargar_solicitudes(ruta, _catalogos)


@st.cache_resource(show_spinner="Calculando la recomendación de cada solicitud...")
def tabla_general(ruta, modificado, huella, _rec, _solicitudes):
    return R.tabla_general(_rec, _solicitudes)


def tema():
    tipo = getattr(st.context.theme, "type", None)
    return tipo if tipo in COLORES_FACTORES else "light"


# --- Secciones ---

def mostrar_errores_de_carga(errores):
    if not errores:
        return
    st.warning(f"{len(errores)} fila(s) del archivo tienen errores y no se cargaron.")
    st.dataframe(pd.DataFrame([{"Fila": e.fila, "Solicitud": e.id_envio, "Campo": e.campo, "Problema": e.mensaje}
                               for e in errores]), hide_index=True, width="stretch")


def mostrar_resumen(r):
    s = r.solicitud
    resumen = R.resumen_solicitud(s)
    st.subheader(f"Solicitud {s.get('id_envio', '')}")
    for fila in (list(resumen.items())[:4], list(resumen.items())[4:]):
        for columna, (nombre, valor) in zip(st.columns(4), fila):
            columna.metric(nombre, valor)
    if s.get("descripcion"):
        st.caption(s["descripcion"])
    st.info("**Pesos aplicados:** " + " · ".join(r.motivos_pesos) if r.motivos_pesos else
            "Sin pesos: ningún proveedor pasó los filtros.")


def grafico_aportes(r):
    datos = R.tabla_aportes(r)
    nombres = [R.NOMBRE_FACTOR[f] for f in R.FACTORES]
    modo = tema()
    orden = list(r.top.proveedor)
    barras = (
        alt.Chart(datos)
        .mark_bar(stroke=SUPERFICIE[modo], strokeWidth=2, cornerRadiusEnd=4)
        .encode(
            y=alt.Y("Proveedor:N", sort=orden, title=None),
            x=alt.X("sum(Aporte):Q", title="Puntaje (aporte de cada factor = puntos × peso)",
                    scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("Factor:N", sort=nombres,
                            scale=alt.Scale(domain=nombres, range=COLORES_FACTORES[modo]),
                            legend=alt.Legend(orient="top", title=None)),
            order=alt.Order("orden:Q"),
            tooltip=["Proveedor", "Factor", "Puntos", "Peso", "Aporte", "Puntaje"],
        )
    )
    totales = (
        alt.Chart(datos.drop_duplicates("Proveedor"))
        .mark_text(align="left", dx=6)
        .encode(y=alt.Y("Proveedor:N", sort=orden), x="Puntaje:Q", text=alt.Text("Puntaje:Q", format=".1f"))
    )
    return (barras + totales).properties(height=60 * len(orden) + 40)


def mostrar_historico(r):
    h = R.comparacion_historica(r)
    if h is None:
        return
    texto = (f"En su momento se eligió **{h['proveedor']}**: {h['resultado']}, costó {h['precio_pagado']}. "
             f"Ese proveedor {h['lugar']}.")
    (st.success if h["coincide"] else st.info)(texto)
    st.caption("Este envío está en la base con la que se entrenaron los modelos, así que la comparación es "
               "ilustrativa. La validación honesta (entrenar hasta mar-2026 y probar en abr-sep 2026) está en "
               "sistema_proveedores/validar_modelo2.py.")


def mostrar_recomendacion(r):
    mostrar_resumen(r)
    if r.ranking.empty:
        st.error("Ningún proveedor cumple todos los requisitos de esta solicitud.")
        alternativas = R.tabla_alternativas(r)
        if alternativas.empty:
            st.write("Tampoco hay alternativas cercanas: escalar a un supervisor.")
        else:
            st.markdown("**Alternativas** (cambiando una condición):")
            st.dataframe(alternativas, hide_index=True, width="stretch")
    else:
        st.markdown(f"**Top {len(r.top)} recomendados** · referencia de mercado: "
                    f"{R.formatear_cop(r.mercado_precio)} y {R.formatear_horas(r.mercado_tiempo)}")
        st.dataframe(R.tabla_top(r), hide_index=True, width="stretch")
        if r.con_plazo:
            st.caption(f"'A tiempo' = cumple lo que promete el propio proveedor; "
                       f"'En plazo' = llega antes de las {r.solicitud['plazo_h']:.0f} h pedidas.")
        if r.explicacion:
            st.success(r.explicacion)
        st.altair_chart(grafico_aportes(r), width="stretch")
        with st.expander("Desglose del puntaje en tabla"):
            st.dataframe(R.tabla_aportes(r).drop(columns="orden"), hide_index=True, width="stretch")
        with st.expander("¿De dónde sale la fiabilidad? (Modelo 1)"):
            st.dataframe(R.tabla_desglose_fiabilidad(r), hide_index=True, width="stretch")
        if len(r.ranking) > len(r.top):
            st.caption("Otros candidatos fuera del top: " + ", ".join(
                f"{x.proveedor} ({x.puntaje:.1f})" for x in r.ranking.iloc[len(r.top):].itertuples()))
    for aviso in r.avisos:
        st.warning(aviso)
    mostrar_historico(r)
    with st.expander(f"Proveedores excluidos ({len(r.excluidos)})"):
        excluidos = R.tabla_excluidos(r)
        if excluidos.empty:
            st.write("Ninguno.")
        else:
            st.dataframe(excluidos, hide_index=True, width="stretch")


def pestana_recomendacion(rec, solicitudes):
    origen = st.radio("Solicitud", ["Del archivo de solicitudes", "Envío histórico de la base"], horizontal=True,
                      key="origen")
    if origen == "Del archivo de solicitudes":
        if not solicitudes:
            st.info("El archivo no tiene solicitudes válidas.")
            return
        por_id = {s.id_envio: s for s in solicitudes}
        elegida = st.selectbox("Solicitud", list(por_id), key="solicitud", format_func=lambda i: (
            f"{i} · {por_id[i].origen} → {por_id[i].destino} · {por_id[i].categoria_carga} · "
            f"{R.NOMBRE_VELOCIDAD[por_id[i].nivel_velocidad]}"))
        mostrar_recomendacion(R.recomendar(rec, por_id[elegida].como_dict()))
    else:
        codigo = st.text_input("Código del envío (de S-000001 a S-031386)", ENVIO_HISTORICO_EJEMPLO).strip()
        try:
            solicitud = R.solicitud_historica(rec, codigo)
        except KeyError as exc:
            st.error(exc.args[0])
            return
        mostrar_recomendacion(R.recomendar(rec, solicitud))


def pestana_lote(rec, solicitudes, archivo, modificado):
    st.markdown(f"Reparte las {len(solicitudes)} solicitudes válidas de **{archivo}** entre proveedores, "
                f"maximizando la suma de puntajes del Modelo 2 sin superar los cupos de la semana ni el "
                f"{configuracion.PERFILES['avisos']['concentracion_max']:.0%} del lote por proveedor.")
    if not solicitudes:
        return
    clave = f"lote_{archivo}_{modificado}_{huella}"
    if st.button("Repartir el lote", key="lote"):
        st.session_state[clave] = R.asignar_lote(rec, solicitudes)
    lote = st.session_state.get(clave)
    if lote is None:
        return
    st.caption(f"Método: {lote['metodo']}")
    for aviso in lote["avisos"]:
        st.warning(aviso)
    c = lote["comprobaciones"]
    (st.success if c["ningun_proveedor_supera_cupos"] and c["ningun_proveedor_supera_tope"] else st.error)(
        f"Nadie supera sus cupos: {'sí' if c['ningun_proveedor_supera_cupos'] else 'NO'} · "
        f"nadie supera el tope: {'sí' if c['ningun_proveedor_supera_tope'] else 'NO'} "
        f"(máximo {c['max_pct_proveedor']:.0%} del lote).")
    tablas = R.tablas_lote(lote)
    st.markdown("**Por solicitud** (pérdida = puntaje de su 1.ª opción − puntaje del asignado)")
    st.dataframe(tablas["detalle"], hide_index=True, width="stretch")
    st.markdown("**Puntaje total por escenario**")
    st.dataframe(tablas["resumen"], hide_index=True, width="stretch")
    izquierda, derecha = st.columns(2)
    izquierda.markdown("**Reparto por proveedor**")
    izquierda.dataframe(tablas["reparto"], hide_index=True, width="stretch")
    derecha.markdown("**Uso de cupos**")
    derecha.dataframe(tablas["uso_cupos"], hide_index=True, width="stretch")


def pestana_proveedores(rec):
    st.markdown("**Fiabilidad general (Modelo 1)**: puntualidad, magnitud del retraso, daños y satisfacción, "
                "ajustados por la dificultad de cada envío.")
    st.dataframe(R.tabla_fiabilidad(rec), hide_index=True, width="stretch")
    st.markdown("**Qué puede atender cada proveedor** (derivado del historial; filtros duros del Modelo 2)")
    st.dataframe(R.tabla_catalogo(rec), hide_index=True, width="stretch")
    st.markdown("**Cupos de esta semana** (simulados; se editan en "
                f"`{(configuracion.DIR_M2 / 'capacidad_semana.csv').relative_to(configuracion.RAIZ).as_posix()}`)")
    st.dataframe(R.tabla_cupos(rec), hide_index=True, width="stretch")


def barra_lateral(rec):
    base, info = R.describir_base(rec), info_modelo()
    st.sidebar.header("Datos")
    st.sidebar.markdown(
        f"**Base:** `{info['base_datos']}`  \n"
        f"{R.formatear_miles(base['envios'])} envíos · {base['desde']} a {base['hasta']}  \n"
        f"{len(base['proveedores'])} proveedores · {base['ciudades']} ciudades · "
        f"{', '.join(base['contenedores'])}")
    st.sidebar.caption(f"Modelos entrenados el {info['entrenado_en'].replace('T', ' ')} con esta base.")
    st.sidebar.caption(configuracion.AVISO_DATOS)


# --- Página ---

if not exigir_acceso():
    st.stop()

st.title("Recomendador de transportistas terrestres")
huella = configuracion.huella_entrenamiento()
rec, reentrenado = recomendador(huella)
if reentrenado and st.session_state.get("huella_avisada") != huella:
    st.toast("Los modelos se reentrenaron con la base actual.")
    st.session_state["huella_avisada"] = huella
cat = catalogos(huella, rec)
barra_lateral(rec)

archivos = archivos_solicitudes()
if not archivos:
    st.error(f"No hay archivos solicitudes*.csv en {configuracion.DIR_SOLICITUDES}.")
    st.stop()
nombres = [a.name for a in archivos]
predeterminado = configuracion.SOLICITUDES_PRUEBA.name
archivo = st.sidebar.selectbox("Archivo de solicitudes", nombres, key="archivo",
                               index=nombres.index(predeterminado) if predeterminado in nombres else 0)
ruta = archivos[nombres.index(archivo)]
modificado = ruta.stat().st_mtime
solicitudes, errores = solicitudes_de(str(ruta), modificado, huella, cat)
mostrar_errores_de_carga(errores)

recomendar_tab, todas_tab, lote_tab, proveedores_tab = st.tabs(
    ["Recomendación", "Todas las solicitudes", "Reparto del lote", "Proveedores"])
with recomendar_tab:
    pestana_recomendacion(rec, solicitudes)
with todas_tab:
    if solicitudes:
        st.dataframe(tabla_general(str(ruta), modificado, huella, rec, solicitudes), hide_index=True,
                     width="stretch")
    else:
        st.info("El archivo no tiene solicitudes válidas.")
with lote_tab:
    pestana_lote(rec, solicitudes, archivo, modificado)
with proveedores_tab:
    pestana_proveedores(rec)
