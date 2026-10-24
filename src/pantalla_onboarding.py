"""Onboarding y configuración de la interfaz preferida (Streamlit). Las reglas viven en src/preferencias.py.

Flujo: ingreso → preferencia guardada del operador → si no tiene, onboarding → vista elegida.
En la barra lateral, "Configuración" permite cambiar de entorno en cualquier momento (y se guarda).
"""

import streamlit as st

from src import preferencias as P
from src.ui import componentes as UI

CLAVE_INTERFAZ = "interfaz"          # {"usuario": id, "vista": ..., "guardada": bool} de la sesión actual
CLAVE_ELECCION = "onboarding_eleccion"
CLAVE_ERROR = "onboarding_error"

OPCIONES = {
    P.DASHBOARD: ("Dashboard inteligente",
                  "Compara proveedores con tarjetas visuales, indicadores y recomendaciones explicadas."),
    P.MAPA: ("Mapa de Colombia",
             "Explora rutas, ciudades, orígenes, destinos y proveedores en un mapa geográfico."),
    P.MUNDO_VIRTUAL: ("Mundo virtual 3D",
                      "Explora el entorno logístico mediante una experiencia inmersiva conectada con las gafas."),
}


def nombre_vista(vista):
    return OPCIONES.get(vista, ("Dashboard inteligente",))[0]


def limpiar_interfaz():
    """Se llama sin sesión iniciada: la elección pospuesta o la de otro operador no pasan a la siguiente sesión."""
    for clave in (CLAVE_INTERFAZ, CLAVE_ELECCION, CLAVE_ERROR, "config_vista", "config_error", "config_ok"):
        st.session_state.pop(clave, None)


def _fijar(usuario, vista, guardada):
    st.session_state[CLAVE_INTERFAZ] = {"usuario": usuario, "vista": vista, "guardada": guardada}


def _elegir(usuario, vista):
    st.session_state[CLAVE_ELECCION] = (usuario, vista)
    st.session_state.pop(CLAVE_ERROR, None)


def _continuar(usuario):
    _, vista = st.session_state.get(CLAVE_ELECCION, (None, None))
    if vista not in P.VISTAS:
        return
    try:
        P.guardar_preferencia(usuario, vista)
    except P.ErrorPreferencias as exc:
        st.session_state[CLAVE_ERROR] = str(exc)
        return
    _fijar(usuario, vista, guardada=True)
    st.session_state.pop(CLAVE_ELECCION, None)


def _posponer(usuario):
    # Solo para esta sesión: no se guarda nada y la próxima vez se vuelve a preguntar.
    _fijar(usuario, P.VISTA_PREDETERMINADA, guardada=False)
    st.session_state.pop(CLAVE_ELECCION, None)


def vista_del_operador(usuario):
    """Vista a mostrar, o None si se está mostrando el onboarding (el llamador debe detenerse)."""
    if not usuario:                       # sin operador identificado (p. ej. pruebas): vista por defecto
        return P.VISTA_PREDETERMINADA
    actual = st.session_state.get(CLAVE_INTERFAZ)
    if actual and actual["usuario"] == usuario:
        return actual["vista"]
    error_lectura = None
    try:
        guardada = P.preferencia_de(usuario)
    except P.ErrorPreferencias as exc:
        guardada, error_lectura = None, str(exc)
    if guardada:
        _fijar(usuario, guardada, guardada=True)
        return guardada
    pantalla_onboarding(usuario, error_lectura)
    return None


def pantalla_onboarding(usuario, error_lectura=None):
    eleccion_usuario, eleccion = st.session_state.get(CLAVE_ELECCION, (None, None))
    if eleccion_usuario != usuario:
        eleccion = None
    UI.encabezado_onboarding()
    if error_lectura:
        st.error(f"{error_lectura} No se pudo recuperar su preferencia; elíjala de nuevo.")
    columnas = st.columns(3, gap="medium")
    for columna, (vista, (titulo, descripcion)) in zip(columnas, OPCIONES.items()):
        with columna, st.container(key=f"tarjeta_onb_{vista}"):
            UI.tarjeta_onboarding(vista, titulo, descripcion, seleccionada=(vista == eleccion))
            st.button("Seleccionada" if vista == eleccion else "Elegir esta interfaz", key=f"elegir_{vista}",
                      icon=":material/check_circle:" if vista == eleccion else None,
                      type="primary" if vista == eleccion else "secondary", width="stretch",
                      on_click=_elegir, args=(usuario, vista))
    if st.session_state.get(CLAVE_ERROR):
        st.error(st.session_state[CLAVE_ERROR])
    izquierda, centro, derecha = st.columns([1, 1.2, 1])
    with centro:
        st.button("Continuar con esta interfaz", key="onboarding_continuar", type="primary", width="stretch",
                  disabled=eleccion is None, on_click=_continuar, args=(usuario,),
                  help=None if eleccion else "Seleccione una tarjeta para continuar")
        st.button("Lo decidiré más adelante", key="onboarding_posponer", type="tertiary", width="stretch",
                  on_click=_posponer, args=(usuario,))
        if eleccion is None:
            st.caption("Seleccione una tarjeta para continuar. Podrá cambiarla luego en Configuración.")


def _guardar_desde_configuracion(usuario):
    vista = st.session_state.get("config_vista")
    if vista not in P.VISTAS:
        return
    try:
        P.guardar_preferencia(usuario, vista)
    except P.ErrorPreferencias as exc:
        st.session_state["config_error"] = str(exc)
        return
    st.session_state.pop("config_error", None)
    st.session_state["config_ok"] = vista
    _fijar(usuario, vista, guardada=True)


def configuracion_lateral(usuario, vista_actual):
    """Configuración en la barra lateral: muestra el entorno actual y permite cambiarlo (se guarda)."""
    if not usuario:
        return
    actual = st.session_state.get(CLAVE_INTERFAZ, {})
    with st.sidebar.expander(":material/settings: Configuración", expanded=False):
        estado = "guardada" if actual.get("guardada", True) else "solo en esta sesión"
        st.caption(f"Entorno actual: **{nombre_vista(vista_actual)}** ({estado})")
        st.radio("Entorno de trabajo", list(P.VISTAS), key="config_vista", format_func=nombre_vista,
                 index=list(P.VISTAS).index(vista_actual))
        st.button("Guardar entorno", key="config_guardar", type="primary", width="stretch",
                  on_click=_guardar_desde_configuracion, args=(usuario,))
        if st.session_state.get("config_error"):
            st.error(st.session_state["config_error"])
        elif st.session_state.pop("config_ok", None):
            st.success("Preferencia guardada.")
