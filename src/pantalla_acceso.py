"""Pantallas de ingreso y bloqueo (Streamlit). Las reglas viven en src/sesion.py."""

import streamlit as st

from src.biometria import ReconocedorFacial, imagen_desde_bytes
from src.ui import componentes as UI  # solo presentación
from src.sesion import (
    EstadoSesion,
    bloquear,
    cerrar_sesion,
    desbloquear_con_pin,
    desbloquear_con_rostro,
    iniciar_con_rostro,
    iniciar_solo_con_pin,
    pin_disponible,
)
from src.usuarios import cargar_config_seguridad, cargar_usuarios
from src.vigilancia import vigilar

CLAVE_SESION = "sesion"
# Cada bloqueo o cierre cambia la clave de la cámara, para que una foto anterior
# nunca se reutilice para desbloquear.
CLAVE_RONDA = "ronda_camara"


@st.cache_resource
def _config():
    return cargar_config_seguridad()


@st.cache_resource
def _reconocedor(ruta_detector, ruta_reconocedor):
    return ReconocedorFacial(ruta_detector, ruta_reconocedor)


def _estado():
    return st.session_state.setdefault(CLAVE_SESION, EstadoSesion())


def _guardar(estado):
    st.session_state[CLAVE_SESION] = estado


def _nueva_ronda():
    st.session_state[CLAVE_RONDA] = st.session_state.get(CLAVE_RONDA, 0) + 1


def _clave_camara(nombre):
    return f"{nombre}_{st.session_state.get(CLAVE_RONDA, 0)}"


def _al_ausentarse():
    _guardar(bloquear(_estado()))
    _nueva_ronda()


def _al_cerrar_sesion():
    _guardar(cerrar_sesion(_estado()))
    _nueva_ronda()


def _huella_de_foto(foto, config):
    """(huella, error) a partir de la foto de st.camera_input."""
    imagen = imagen_desde_bytes(foto.getvalue())
    if imagen is None:
        return None, "No se pudo leer la foto."
    try:
        resultado = _reconocedor(config.ruta_detector, config.ruta_reconocedor).huella(imagen)
    except FileNotFoundError as exc:
        return None, str(exc)
    return resultado.huella, resultado.error


def _aplicar(resultado):
    """Guarda el nuevo estado; si hubo error lo muestra, si no, recarga la página."""
    nuevo, error = resultado
    _guardar(nuevo)
    if error:
        st.error(error)
    else:
        st.rerun()


def _intento_con_rostro(config, etiqueta, clave, accion):
    foto = st.camera_input(etiqueta, key=_clave_camara(clave))
    if foto is None:
        return
    huella, error = _huella_de_foto(foto, config)
    if error:
        st.error(error)
        return
    _aplicar(accion(huella))


def pantalla_ingreso(config, usuarios):
    formulario, informacion = st.columns([1.35, 1], gap="large")
    with informacion:
        UI.panel_ingreso_seguro()
    with formulario:
        _formulario_ingreso(config, usuarios)


def _formulario_ingreso(config, usuarios):
    UI.bienvenida()
    if not usuarios:
        st.error("No hay usuarios registrados. Un administrador debe ejecutar:\n\n"
                 "`python -m src.registrar_usuario --usuario <id> --nombre \"<Nombre>\"`")
        return
    rostro, pin = st.tabs([":material/face: Reconocimiento facial", ":material/lock: PIN de respaldo"])
    with rostro:
        UI.pista_camara()
        _intento_con_rostro(
            config, "Mire de frente a la cámara y tome la foto", "foto_ingreso",
            lambda huella: iniciar_con_rostro(_estado(), huella, usuarios, config.umbral_similitud))
    with pin:
        if not pin_disponible(_estado(), config.max_intentos_pin):
            st.warning("Se agotaron los intentos con PIN. Ingrese con reconocimiento facial.")
            return
        with st.form("ingreso_pin"):
            clave = st.text_input("PIN de seguridad", type="password", placeholder="Escriba su PIN")
            enviar = st.form_submit_button("Ingresar")
        if enviar:
            _aplicar(iniciar_solo_con_pin(_estado(), clave, usuarios, config.max_intentos_pin))


def pantalla_bloqueo(config, usuarios):
    estado = _estado()
    nombre = usuarios[estado.usuario].nombre
    st.title("Pantalla bloqueada")
    st.warning(f"Se bloqueó porque no se detectó a {nombre} frente a la cámara durante "
               f"{config.segundos_ausencia} segundos. Verifique su identidad para continuar.")
    rostro, pin = st.tabs(["Reconocimiento facial", "PIN de respaldo"])
    with rostro:
        _intento_con_rostro(
            config, "Tome una foto para desbloquear", "foto_desbloqueo",
            lambda huella: desbloquear_con_rostro(_estado(), huella, usuarios, config.umbral_similitud))
    with pin:
        if pin_disponible(estado, config.max_intentos_pin):
            with st.form("desbloqueo_pin"):
                clave = st.text_input(f"PIN de {nombre}", type="password")
                enviar = st.form_submit_button("Desbloquear")
            if enviar:
                _aplicar(desbloquear_con_pin(_estado(), clave, usuarios, config.max_intentos_pin))
        else:
            st.warning("Se agotaron los intentos con PIN. Desbloquee con reconocimiento facial.")
    st.button("Cerrar sesión", on_click=_al_cerrar_sesion)


def exigir_acceso():
    """Muestra ingreso o bloqueo si corresponde. Devuelve True si se puede ver el dashboard."""
    config = _config()
    usuarios = cargar_usuarios(config.archivo_usuarios)
    estado = _estado()
    if estado.autenticado and estado.usuario not in usuarios:  # el usuario fue eliminado
        _al_cerrar_sesion()
        estado = _estado()
    if not estado.autenticado:
        pantalla_ingreso(config, usuarios)
        return False
    if estado.bloqueado:
        pantalla_bloqueo(config, usuarios)
        return False

    resultado = vigilar(config.segundos_ausencia, _al_ausentarse)
    st.sidebar.markdown(f"Sesión: **{usuarios[estado.usuario].nombre}**")
    st.sidebar.button("Cerrar sesión", on_click=_al_cerrar_sesion)
    if getattr(resultado, "estado", None) == "sin_camara":
        st.sidebar.warning("Vigilancia de presencia inactiva: no hay acceso a la cámara. "
                           "El dashboard no se bloqueará por ausencia.")
    return True
