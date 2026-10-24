"""Vigilancia de presencia: cámara en una esquina y aviso si no hay rostro durante N segundos.

La detección corre en el navegador (MediaPipe Face Detector); solo se envía a Python
el evento "ausente". Ninguna imagen sale del navegador.
"""

import streamlit as st

MEDIAPIPE = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14"
MODELO = ("https://storage.googleapis.com/mediapipe-models/face_detector/"
          "blaze_face_short_range/float16/1/blaze_face_short_range.tflite")

CSS = """
.vigilancia-caja {
    position: fixed; right: 16px; bottom: 16px; z-index: 999990;
    width: 200px; border-radius: 8px; overflow: hidden;
    background: #111; color: #fff; font: 12px/1.4 sans-serif;
    box-shadow: 0 2px 10px rgba(0, 0, 0, .35);
}
.vigilancia-caja video { display: block; width: 100%; transform: scaleX(-1); }
.vigilancia-estado { padding: 4px 8px; }
.vigilancia-estado.ok { background: #136f3a; }
.vigilancia-estado.alerta { background: #a33a00; }
.vigilancia-estado.error { background: #6b6b6b; }
"""

JS = f"""
const MEDIAPIPE = "{MEDIAPIPE}";
const MODELO = "{MODELO}";

// Un solo vigilante por pestaña: sobrevive a los reruns de Streamlit para no
// reiniciar la cámara cada vez que el usuario cambia un filtro.
function obtenerVigilante() {{
    if (window.__vigilancia) return window.__vigilancia;
    const caja = document.createElement("div");
    caja.className = "vigilancia-caja";
    caja.innerHTML = '<video autoplay muted playsinline></video>' +
                     '<div class="vigilancia-estado error">Iniciando cámara…</div>';
    const v = {{
        caja, video: caja.querySelector("video"), estado: caja.querySelector(".vigilancia-estado"),
        ultimoVisto: performance.now(), avisado: false, segundos: 10,
        enviar: () => {{}}, temporizador: null, cierrePendiente: null, stream: null,
    }};
    window.__vigilancia = v;
    iniciar(v);
    return v;
}}

function mostrar(v, clase, texto) {{
    v.estado.className = "vigilancia-estado " + clase;
    v.estado.textContent = texto;
}}

async function crearDetector() {{
    const vision = await import(MEDIAPIPE + "/vision_bundle.mjs");
    const archivos = await vision.FilesetResolver.forVisionTasks(MEDIAPIPE + "/wasm");
    const opciones = (delegate) => ({{
        baseOptions: {{ modelAssetPath: MODELO, delegate }},
        runningMode: "VIDEO", minDetectionConfidence: 0.5,
    }});
    try {{
        return await vision.FaceDetector.createFromOptions(archivos, opciones("GPU"));
    }} catch (e) {{
        return await vision.FaceDetector.createFromOptions(archivos, opciones("CPU"));
    }}
}}

async function iniciar(v) {{
    try {{
        v.stream = await navigator.mediaDevices.getUserMedia({{ video: {{ width: 320, height: 240 }} }});
        v.video.srcObject = v.stream;
        const detector = await crearDetector();
        v.ultimoVisto = performance.now();
        v.temporizador = setInterval(() => revisar(v, detector), 250);
    }} catch (e) {{
        mostrar(v, "error", "Vigilancia inactiva: " + (e.name === "NotAllowedError"
            ? "permiso de cámara denegado" : "no se pudo iniciar"));
        v.enviar("estado", "sin_camara");
    }}
}}

function revisar(v, detector) {{
    if (v.avisado || v.video.readyState < 2) return;
    const ahora = performance.now();
    const rostros = detector.detectForVideo(v.video, ahora).detections.length;
    if (rostros > 0) v.ultimoVisto = ahora;
    const restante = v.segundos - (ahora - v.ultimoVisto) / 1000;
    if (restante <= 0) {{
        v.avisado = true;
        mostrar(v, "alerta", "Sin rostro: bloqueado");
        v.enviar("ausente", Date.now());
    }} else if (rostros > 0) {{
        mostrar(v, "ok", "Presencia verificada");
    }} else {{
        mostrar(v, "alerta", `Sin rostro: bloqueo en ${{Math.ceil(restante)}} s`);
    }}
}}

function detener(v) {{
    clearInterval(v.temporizador);
    if (v.stream) v.stream.getTracks().forEach((t) => t.stop());
    v.caja.remove();
    window.__vigilancia = null;
}}

export default function (component) {{
    const {{ data, parentElement, setTriggerValue, setStateValue }} = component;
    const v = obtenerVigilante();
    clearTimeout(v.cierrePendiente);
    v.segundos = data.segundos;
    v.enviar = (nombre, valor) => nombre === "ausente"
        ? setTriggerValue(nombre, valor) : setStateValue(nombre, valor);
    parentElement.appendChild(v.caja);
    // Si el componente desaparece (pantalla de bloqueo, cierre de sesión) se apaga
    // la cámara; la espera evita apagarla en un rerun normal que lo vuelve a montar.
    return () => {{ v.cierrePendiente = setTimeout(() => detener(v), 1500); }};
}}
"""

def vigilar(segundos_ausencia, al_ausentarse):
    """Monta la vigilancia; llama `al_ausentarse` cuando no hay rostro durante N segundos."""
    # Se registra en cada ejecución (registrar la misma definición no tiene costo) para
    # que el componente exista aunque Streamlit reinicie su registro o recargue módulos.
    componente = st.components.v2.component("vigilancia_presencia", css=CSS, js=JS, isolate_styles=False)
    return componente(
        key="vigilancia_presencia",
        data={"segundos": segundos_ausencia},
        on_ausente_change=al_ausentarse,
        on_estado_change=lambda: None,
    )
