"""Dashboard BEEP & GO del recomendador de transportistas.

Lee la base de datos (config/fuente_datos.yaml), usa los Modelos 1 y 2 de
sistema_proveedores/ y muestra su resultado. Solo presentación: la lógica está en src/
y la apariencia en src/ui/.
"""

import altair as alt
import pandas as pd
import streamlit as st

from src import contrato as C
from src import recomendacion as R
from src.fuente_datos import archivos_solicitudes, cargar_recomendador, info_modelo
from src.motor import configuracion
from src import preferencias as P
from src.pantalla_acceso import exigir_acceso
from src.pantalla_onboarding import configuracion_lateral, limpiar_interfaz, vista_del_operador
from src.solicitud import cargar_solicitudes, catalogos_desde_envios
from src.ui import componentes as UI
from src.ui.tema import COLORES_FACTORES as PALETA_MARCA, aplicar_tema, estilo_acceso
from src.usuarios import cargar_config_seguridad, cargar_usuarios
from src.vista_mapa import mostrar_mapa

COLORES_FACTORES = {"light": PALETA_MARCA, "dark": PALETA_MARCA}
SUPERFICIE = {"light": "#ffffff", "dark": "#0e1117"}
ENVIO_HISTORICO_EJEMPLO = "S-030106"

st.set_page_config(page_title="BEEP & GO · Recomendador de transporte", page_icon="🚚", layout="wide")
aplicar_tema()


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


@st.cache_resource
def coordenadas_referencia():
    """Coordenadas de config/ciudades.yaml; None si no se pueden leer (se informa, no se inventan)."""
    try:
        return C.cargar_coordenadas()
    except C.ErrorContrato:
        return None


def tema():
    tipo = getattr(st.context.theme, "type", None)
    return tipo if tipo in COLORES_FACTORES else "light"


def usuario_actual():
    """Nombre del usuario con sesión iniciada (solo lectura, para el encabezado)."""
    estado = st.session_state.get("sesion")
    if not getattr(estado, "usuario", None):
        return None
    try:
        return cargar_usuarios(cargar_config_seguridad().archivo_usuarios)[estado.usuario].nombre
    except (KeyError, OSError, ValueError):
        return estado.usuario


def fiabilidad_por_proveedor(rec):
    """Filas del ranking del Modelo 1 por proveedor (fortalezas, debilidades y componentes). Solo lectura."""
    return {fila.proveedor: fila for fila in rec.m1.ranking.itertuples()}


def fortalezas_y_debilidades(fila):
    return UI.lista_fd(UI.partir_lista(fila.fortalezas), UI.partir_lista(fila.debilidades),
                       UI.partir_lista(fila.fortalezas_por_contexto), UI.partir_lista(fila.debilidades_por_contexto))


def en_pantalla_de_acceso():
    estado = st.session_state.get("sesion")
    return not (getattr(estado, "autenticado", False) and not getattr(estado, "bloqueado", False))


# --- Secciones ---

def mostrar_errores_de_carga(errores):
    if not errores:
        return
    st.warning(f"{len(errores)} fila(s) del archivo tienen errores y no se cargaron.")
    st.dataframe(pd.DataFrame([{"Fila": e.fila, "Solicitud": e.id_envio, "Campo": e.campo, "Problema": e.mensaje}
                               for e in errores]), hide_index=True, width="stretch")


def mostrar_resumen(r):
    s = r.solicitud
    with st.container(border=True, key="tarjeta_solicitud"):
        UI.titulo(f"Solicitud {s.get('id_envio', '')}", s.get("descripcion") or "")
        UI.datos_solicitud(R.resumen_solicitud(s))
        st.info("**Pesos aplicados:** " + " · ".join(r.motivos_pesos) if r.motivos_pesos else
                "Sin pesos: ningún proveedor pasó los filtros.")


def grafico_aportes(r):
    datos = R.tabla_aportes(r)
    nombres = [R.NOMBRE_FACTOR[f] for f in R.FACTORES]
    modo = tema()
    orden = list(r.top.proveedor)
    barras = (
        alt.Chart(datos)
        .mark_bar(stroke=SUPERFICIE[modo], strokeWidth=2, cornerRadiusEnd=6, height=26)
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
        .mark_text(align="left", dx=8, fontWeight="bold", color="#0B1F4D")
        .encode(y=alt.Y("Proveedor:N", sort=orden), x="Puntaje:Q", text=alt.Text("Puntaje:Q", format=".1f"))
    )
    return ((barras + totales).properties(height=60 * len(orden) + 40)
            .configure_axis(labelFont="Inter", titleFont="Inter", labelColor="#14213D", titleColor="#6B7A90",
                            gridColor="#EEF2F8", domainColor="#E3E8F0", labelFontSize=13)
            .configure_legend(labelFont="Inter", labelFontSize=13, symbolType="circle")
            .configure_view(strokeWidth=0))


def mostrar_historico(r):
    h = R.comparacion_historica(r)
    if h is None:
        return
    with st.container(border=True, key="tarjeta_historico"):
        UI.titulo("Comparación con lo que pasó", "Envío histórico de la base")
        texto = (f"En su momento se eligió **{h['proveedor']}**: {h['resultado']}, costó {h['precio_pagado']}. "
                 f"Ese proveedor {h['lugar']}.")
        (st.success if h["coincide"] else st.info)(texto)
        st.caption("Este envío está en la base con la que se entrenaron los modelos, así que la comparación es "
                   "ilustrativa. La validación honesta (entrenar hasta mar-2026 y probar en abr-sep 2026) está en "
                   "sistema_proveedores/validar_modelo2.py.")


def tarjeta_recomendado(rec, r, contrato):
    x = r.top.iloc[0]
    del_contrato = contrato["elegibles"][0]
    metricas = [
        ("Precio estimado", R.formatear_cop(x.precio_cop)),
        ("Precio vs mercado", R.formatear_cambio(x.precio_vs_mercado_pct)),
        ("Fiabilidad (Modelo 1)", f"{x.fiabilidad:.1f}"),
        ("Tiempo esperado", R.formatear_horas(x.tiempo_esperado_h)),
        ("Tiempo vs mercado", R.formatear_cambio(x.tiempo_vs_mercado_pct)),
        ("A tiempo", f"{x.prob_a_tiempo:.0f} %"),
    ]
    if r.con_plazo:
        metricas.append(("En plazo", f"{100 * x.prob_plazo:.0f} %"))
    cupos = del_contrato["cupos_disponibles"]
    metricas.append(("Cupos esta semana (simulados)", "No disponible" if cupos is None else cupos))
    chips = (UI.estrellas(del_contrato["calificacion_clientes"])
             + UI.chip(f"Confianza: {x.confianza}", "azul") + UI.chip(f"Tendencia: {x.tendencia}", "gris")
             + UI.chip(f"{len(r.ranking)} candidato(s) cumplen", "verde"))
    ventaja = (f"+{x.puntaje - r.ranking.puntaje.iat[1]:.1f} pts sobre el 2.º"
               if len(r.ranking) > 1 else None)
    fila = fiabilidad_por_proveedor(rec).get(x.proveedor)
    fd = fortalezas_y_debilidades(fila) if fila is not None else ""
    UI.tarjeta_recomendado(x.proveedor, x.puntaje, metricas, chips, ventaja, fd)


def mostrar_recomendacion(rec, r, contrato):
    hay_candidatos = not r.ranking.empty
    UI.pasos([
        ("Solicitud", "validada", "hecho"),
        ("Filtros duros", f"{len(r.ranking)} cumplen · {len(r.excluidos)} excluidos",
         "hecho" if hay_candidatos else "error"),
        ("Puntaje", "precio, tiempo y fiabilidad", "hecho" if hay_candidatos else ""),
        ("Recomendación", r.recomendado or "sin candidatos", "activo" if hay_candidatos else ""),
    ])
    mostrar_resumen(r)
    if not hay_candidatos:
        with st.container(border=True, key="tarjeta_sin_candidatos"):
            st.error("Ningún proveedor cumple todos los requisitos de esta solicitud.")
            alternativas = R.tabla_alternativas(r)
            if alternativas.empty:
                st.write("Tampoco hay alternativas cercanas: escalar a un supervisor.")
            else:
                UI.titulo("Alternativas", "Cambiando una condición")
                st.dataframe(alternativas, hide_index=True, width="stretch")
            for aviso in r.avisos:
                st.warning(aviso)
    else:
        izquierda, derecha = st.columns([1.15, 1], gap="medium")
        with izquierda, st.container(border=True, key="tarjeta_recomendado"):
            UI.titulo("Recomendación principal", "Mejor puntaje del Modelo 2")
            tarjeta_recomendado(rec, r, contrato)
        with derecha, st.container(border=True, key="tarjeta_por_que"):
            UI.titulo("¿Por qué este proveedor?")
            if r.explicacion:
                st.success(r.explicacion)
            for aviso in r.avisos:
                st.warning(aviso)
            if not r.explicacion and not r.avisos:
                st.caption("Sin explicación adicional ni avisos para esta solicitud.")
        with st.container(border=True, key="tarjeta_top"):
            UI.titulo(f"Top {len(r.top)} recomendados",
                      f"Referencia de mercado: {R.formatear_cop(r.mercado_precio)} y {R.formatear_horas(r.mercado_tiempo)}")
            st.dataframe(R.tabla_top(r), hide_index=True, width="stretch")
            if r.con_plazo:
                st.caption(f"'A tiempo' = cumple lo que promete el propio proveedor; "
                           f"'En plazo' = llega antes de las {r.solicitud['plazo_h']:.0f} h pedidas.")
            if len(r.ranking) > len(r.top):
                st.caption("Otros candidatos fuera del top: " + ", ".join(
                    f"{x.proveedor} ({x.puntaje:.1f})" for x in r.ranking.iloc[len(r.top):].itertuples()))
        with st.container(border=True, key="tarjeta_factores"):
            UI.titulo("Factores considerados", "Aporte de cada factor al puntaje")
            st.altair_chart(grafico_aportes(r), width="stretch")
            with st.expander("Desglose del puntaje en tabla"):
                st.dataframe(R.tabla_aportes(r).drop(columns="orden"), hide_index=True, width="stretch")
            with st.expander("¿De dónde sale la fiabilidad? (Modelo 1)"):
                st.dataframe(R.tabla_desglose_fiabilidad(r), hide_index=True, width="stretch")
    mostrar_historico(r)
    with st.expander(f"Proveedores excluidos ({len(r.excluidos)})"):
        excluidos = R.tabla_excluidos(r)
        if excluidos.empty:
            st.write("Ninguno.")
        else:
            st.dataframe(excluidos, hide_index=True, width="stretch")


def elegir_solicitud(rec, solicitudes):
    """Solicitud activa, común a todas las vistas (las claves de los widgets la conservan al cambiar de vista).
    Devuelve el dict de la solicitud o None si no hay una válida."""
    with st.container(border=True, key="tarjeta_selector"):
        UI.titulo("Elegir solicitud", "Del archivo cargado o un envío histórico de la base")
        izquierda, derecha = st.columns([1, 1.6], vertical_alignment="bottom")
        origen = izquierda.radio("Solicitud", ["Del archivo de solicitudes", "Envío histórico de la base"],
                                 horizontal=True, key="origen")
        if origen == "Del archivo de solicitudes":
            if not solicitudes:
                derecha.info("El archivo no tiene solicitudes válidas.")
                return None
            por_id = {s.id_envio: s for s in solicitudes}
            elegida = derecha.selectbox("Solicitud", list(por_id), key="solicitud", format_func=lambda i: (
                f"{i} · {por_id[i].origen} → {por_id[i].destino} · {por_id[i].categoria_carga} · "
                f"{R.NOMBRE_VELOCIDAD[por_id[i].nivel_velocidad]}"))
            solicitud = por_id[elegida].como_dict()
        else:
            codigo = derecha.text_input("Código del envío (de S-000001 a S-031386)", ENVIO_HISTORICO_EJEMPLO).strip()
            try:
                solicitud = R.solicitud_historica(rec, codigo)
            except KeyError as exc:
                derecha.error(exc.args[0])
                return None
    return solicitud


def pestana_recomendacion(rec, r, contrato):
    if r is None:
        st.info("Seleccione una solicitud válida para ver la recomendación.")
        return
    mostrar_recomendacion(rec, r, contrato)


def publicar_contrato(contrato):
    """Deja el contrato de la solicitud activa en static/contrato/ para que lo consuma el mundo 3D."""
    s = contrato["solicitud"]
    clave = (s["id"], s["origen"], s["destino"], contrato["recomendado"], contrato["fuente"]["modelo_entrenado"])
    if st.session_state.get("contrato_publicado") == clave:
        return
    try:
        C.guardar(contrato)
        st.session_state["contrato_publicado"] = clave
    except C.ErrorContrato as exc:
        st.sidebar.warning(str(exc))


def pestana_todas(ruta, modificado, rec, solicitudes):
    with st.container(border=True, key="tarjeta_todas"):
        if not solicitudes:
            st.info("El archivo no tiene solicitudes válidas.")
            return
        tabla = tabla_general(str(ruta), modificado, huella, rec, solicitudes)
        UI.titulo("Todas las solicitudes", "Proveedor recomendado para cada solicitud del archivo")
        sin = int((tabla["Recomendado"] == "Sin candidatos").sum())
        con_avisos = int((tabla["Avisos"] > 0).sum())
        UI.html(UI.chip(f"{len(tabla)} solicitudes", "azul") + " " + UI.chip(f"{sin} sin candidatos", "rojo" if sin else "verde")
                + " " + UI.chip(f"{con_avisos} con avisos", "ambar" if con_avisos else "verde"))
        st.dataframe(tabla, hide_index=True, width="stretch")


def pestana_lote(rec, solicitudes, archivo, modificado):
    with st.container(border=True, key="tarjeta_lote"):
        UI.titulo("Reparto del lote", f"Archivo: {archivo}")
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
    with st.container(border=True, key="tarjeta_lote_resultado"):
        UI.titulo("Resultado del reparto", f"Método: {lote['metodo']}")
        for aviso in lote["avisos"]:
            st.warning(aviso)
        c = lote["comprobaciones"]
        (st.success if c["ningun_proveedor_supera_cupos"] and c["ningun_proveedor_supera_tope"] else st.error)(
            f"Nadie supera sus cupos: {'sí' if c['ningun_proveedor_supera_cupos'] else 'NO'} · "
            f"nadie supera el tope: {'sí' if c['ningun_proveedor_supera_tope'] else 'NO'} "
            f"(máximo {c['max_pct_proveedor']:.0%} del lote).")
        tablas = R.tablas_lote(lote)
        UI.titulo("Por solicitud", "Pérdida = puntaje de su 1.ª opción − puntaje del asignado")
        st.dataframe(tablas["detalle"], hide_index=True, width="stretch")
        UI.titulo("Puntaje total por escenario")
        st.dataframe(tablas["resumen"], hide_index=True, width="stretch")
    izquierda, derecha = st.columns(2, gap="medium")
    with izquierda, st.container(border=True, key="tarjeta_reparto"):
        UI.titulo("Reparto por proveedor")
        st.dataframe(tablas["reparto"], hide_index=True, width="stretch")
    with derecha, st.container(border=True, key="tarjeta_cupos_lote"):
        UI.titulo("Uso de cupos")
        st.dataframe(tablas["uso_cupos"], hide_index=True, width="stretch")


def pestana_proveedores(rec):
    with st.container(border=True, key="tarjeta_fortalezas"):
        UI.titulo("Fortalezas y debilidades por proveedor",
                  "Modelo 1 · comparación frente al promedio de todos los proveedores")
        tarjetas = []
        for fila in rec.m1.ranking.itertuples():
            chips = (UI.chip(f"Confianza: {fila.confianza}", "azul") + UI.chip(f"Tendencia: {fila.tendencia}", "gris")
                     + UI.chip(f"{R.formatear_miles(fila.envios)} envíos", "gris")
                     + UI.chip(f"{fila.a_tiempo_bruto_pct:.0f} % a tiempo (bruto)", "verde"))
            componentes = [("Puntualidad", fila.puntualidad_ajustada), ("Retrasos cortos", fila.magnitud_retraso_ajustada),
                           ("Carga sin daños", fila.integridad_ajustada), ("Satisfacción", fila.satisfaccion_ajustada)]
            tarjetas.append(UI.tarjeta_proveedor_html(
                fila.posicion, fila.proveedor, fila.fiabilidad_ajustada,
                f"{fila.fiabilidad_ic95_inf:.1f} – {fila.fiabilidad_ic95_sup:.1f}", chips, componentes,
                fortalezas_y_debilidades(fila)))
        UI.tarjetas_proveedores(tarjetas)
        st.caption("Componentes ajustados por la dificultad de cada envío (0–100). Las de \"contexto específico\" "
                   "aplican solo en ciertas condiciones (por ejemplo, temporada alta o una velocidad de servicio). "
                   "Base simulada: no permite sacar conclusiones sobre las empresas reales.")
    with st.container(border=True, key="tarjeta_fiabilidad"):
        UI.titulo("Fiabilidad general (Modelo 1)")
        st.caption("Puntualidad, magnitud del retraso, daños y satisfacción, ajustados por la dificultad de cada envío.")
        st.dataframe(R.tabla_fiabilidad(rec), hide_index=True, width="stretch")
    with st.container(border=True, key="tarjeta_catalogo"):
        UI.titulo("Qué puede atender cada proveedor")
        st.caption("Derivado del historial; son los filtros duros del Modelo 2.")
        st.dataframe(R.tabla_catalogo(rec), hide_index=True, width="stretch")
    with st.container(border=True, key="tarjeta_cupos"):
        UI.titulo("Cupos de esta semana")
        st.caption("Simulados; se editan en "
                   f"`{(configuracion.DIR_M2 / 'capacidad_semana.csv').relative_to(configuracion.RAIZ).as_posix()}`")
        st.dataframe(R.tabla_cupos(rec), hide_index=True, width="stretch")


def barra_lateral(rec):
    base, info = R.describir_base(rec), info_modelo()
    UI.seccion("Fuente de datos", st.sidebar)
    st.sidebar.markdown(
        f'<div class="bg-datos"><b>Base:</b> <code>{info["base_datos"]}</code><br>'
        f'{R.formatear_miles(base["envios"])} envíos · {base["desde"]} a {base["hasta"]}<br>'
        f'{len(base["proveedores"])} proveedores · {base["ciudades"]} ciudades · '
        f'{", ".join(base["contenedores"])}</div>', unsafe_allow_html=True)
    st.sidebar.caption(f"Modelos entrenados el {info['entrenado_en'].replace('T', ' ')} con esta base.")
    st.sidebar.caption(configuracion.AVISO_DATOS)


def avisar_vista_pendiente(vista):
    """El mapa y el mundo 3D aún no están integrados: se dice claramente y se muestra el dashboard mientras tanto."""
    if vista == P.MUNDO_VIRTUAL:
        UI.aviso_vista_pendiente(
            "Elegiste el Mundo virtual 3D: todavía no muestra estos datos",
            "La solicitud activa ya se publica en el contrato compartido (app/static/contrato/solicitud_activa.json), "
            "pero el mundo 3D aún corre aparte con su base de demostración y no lo lee. Mientras tanto ves el "
            "dashboard. Puedes cambiar de entorno en Configuración.",
            "https://localhost:5173", "Abrir el mundo 3D actual (datos de demostración)")


def indicadores(rec, solicitudes, errores):
    base = R.describir_base(rec)
    UI.kpis([
        ("caja", R.formatear_miles(base["envios"]), "envíos en la base", "#E8EFFE", "#2F5BEA"),
        ("edificio", len(base["proveedores"]), "proveedores", "#FDECEE", "#D7263D"),
        ("mapa", base["ciudades"], "ciudades", "#E6F5EE", "#2E9E6A"),
        ("camion", len(base["contenedores"]), "tipos de contenedor", "#EEF2F8", "#0B1F4D"),
        ("lista", len(solicitudes), f"solicitudes válidas · {len(errores)} con error", "#FFF4D6", "#B07D00"),
    ])


# --- Página ---

UI.logo(st.sidebar)
# Elementos visuales de las pantallas de acceso: viven en contenedores temporales que se vacían al ingresar.
portada, lateral = st.empty(), st.sidebar.empty()
if not getattr(st.session_state.get("sesion"), "autenticado", False):
    limpiar_interfaz()   # la interfaz elegida (o pospuesta) pertenece a la sesión del operador que la eligió
if en_pantalla_de_acceso():
    with portada.container():
        estilo_acceso()
        UI.cabecera_acceso()
    with lateral.container():
        UI.navegacion_acceso()
if not exigir_acceso():
    st.stop()
portada.empty()
lateral.empty()

# Preferencia de interfaz: si el operador aún no tiene una, se muestra el onboarding y nada más.
id_operador = getattr(st.session_state.get("sesion"), "usuario", None)
vista = vista_del_operador(id_operador)
if vista is None:
    st.stop()
configuracion_lateral(id_operador, vista)

UI.encabezado("Recomendador de transportistas terrestres",
              "Elige una solicitud y compara los proveedores que cumplen sus requisitos.",
              usuario=usuario_actual(), rol="Equipo de operaciones",
              insignias=[UI.chip("Datos simulados", "ambar")])
try:
    huella = configuracion.huella_entrenamiento()
    rec, reentrenado = recomendador(huella)
except Exception as exc:  # noqa: BLE001 - frontera de la interfaz: se informa y se detiene, sin datos de reemplazo
    st.error("No se pudieron cargar la base de datos o el modelo de recomendación. No se muestran resultados "
             "para no presentar información incompleta. Revise la base y ejecute `python -m src.verificar_datos`.")
    st.caption(f"Detalle técnico: {type(exc).__name__}")
    st.stop()
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
UI.seccion("Solicitudes", st.sidebar)
archivo = st.sidebar.selectbox("Archivo de solicitudes", nombres, key="archivo",
                               index=nombres.index(predeterminado) if predeterminado in nombres else 0)
ruta = archivos[nombres.index(archivo)]
modificado = ruta.stat().st_mtime
solicitudes, errores = solicitudes_de(str(ruta), modificado, huella, cat)
avisar_vista_pendiente(vista)
indicadores(rec, solicitudes, errores)
mostrar_errores_de_carga(errores)

# Contexto común: UNA solicitud activa y UNA recomendación del motor para todas las vistas.
solicitud_activa = elegir_solicitud(rec, solicitudes)
r = R.recomendar(rec, solicitud_activa) if solicitud_activa is not None else None
contrato = C.construir(rec, r, coordenadas_referencia()) if r is not None else None
if contrato is not None:
    publicar_contrato(contrato)

pestanas = [":material/recommend: Recomendación", ":material/list_alt: Todas las solicitudes",
            ":material/local_shipping: Reparto del lote", ":material/warehouse: Proveedores"]
if vista == P.MAPA:
    mapa_tab, *resto = st.tabs([":material/map: Mapa"] + pestanas)
    with mapa_tab:
        mostrar_mapa(contrato, coordenadas_referencia())
else:
    resto = st.tabs(pestanas)
recomendar_tab, todas_tab, lote_tab, proveedores_tab = resto
with recomendar_tab:
    pestana_recomendacion(rec, r, contrato)
with todas_tab:
    pestana_todas(ruta, modificado, rec, solicitudes)
with lote_tab:
    pestana_lote(rec, solicitudes, archivo, modificado)
with proveedores_tab:
    pestana_proveedores(rec)
