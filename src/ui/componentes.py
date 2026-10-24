"""Componentes visuales reutilizables (HTML + CSS del tema). Solo presentación.

Todo el HTML se arma en una sola línea: en st.markdown, una línea con sangría se
interpretaría como bloque de código.
"""

from html import escape

import streamlit as st

# Íconos de línea (trazos tipo Lucide) como SVG en línea.
_TRAZOS = {
    "camion": '<path d="M3 7h11v9H3z"/><path d="M14 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/>',
    "ruta": '<circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h8a3 3 0 0 0 0-6H8a3 3 0 0 1 0-6h8"/>',
    "caja": '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "edificio": '<path d="M3 21h18M5 21V8l7-4 7 4v13"/><path d="M9 21v-5h6v5"/>',
    "mapa": '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    "lista": '<path d="M9 6h12M9 12h12M9 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    "alerta": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
    "reloj": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "escudo": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    "estrella": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
    "candado": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "casa": '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    "barras": '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
    "persona": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    "rostro": '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><circle cx="9.5" cy="10" r=".6"/><circle cx="14.5" cy="10" r=".6"/><path d="M9.5 14.5a3.5 3.5 0 0 0 5 0"/>',
}


def icono(nombre, tam=22):
    return (f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_TRAZOS[nombre]}</svg>')


def html(contenido, destino=st):
    destino.markdown(contenido, unsafe_allow_html=True)


def logo_html(grande=False):
    clase = "bg-logo grande" if grande else "bg-logo"
    return (f'<div class="{clase}"><span class="l1">BEEP</span>'
            f'<span class="l2"><span class="amp">&amp;</span>GO<span class="fl">&#10140;</span></span>'
            f'<span class="sub">BY COSCO SHIPPING</span></div>')


def logo(destino=st, grande=False):
    html(logo_html(grande), destino)


def seccion(texto, destino=st):
    html(f'<div class="bg-seccion">{escape(texto)}</div>', destino)


def chip(texto, color="azul"):
    return f'<span class="bg-chip {color}">{escape(str(texto))}</span>'


def iniciales(nombre):
    partes = [p for p in str(nombre).split() if p]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def encabezado(titulo, subtitulo, usuario=None, rol=None, insignias=()):
    persona = ""
    if usuario:
        persona = (f'<div class="bg-usuario"><div class="av">{escape(iniciales(usuario))}</div>'
                   f'<div><div class="n">{escape(usuario)}</div><div class="r">{escape(rol or "")}</div></div></div>')
    html(f'<div class="bg-encabezado"><div class="tit"><div class="ico">{icono("camion", 24)}</div>'
         f'<div><h1>{escape(titulo)}</h1><div class="st">{escape(subtitulo)}</div></div></div>'
         f'<div class="der">{"".join(insignias)}{persona}</div></div>')


def kpis(items):
    """items: [(icono, valor, etiqueta, color_fondo, color_icono)]"""
    celdas = "".join(
        f'<div class="bg-kpi"><div class="ico" style="background:{fondo};color:{color}">{icono(ico)}</div>'
        f'<div><div class="v">{escape(str(valor))}</div><div class="e">{escape(etiqueta)}</div></div></div>'
        for ico, valor, etiqueta, fondo, color in items)
    html(f'<div class="bg-kpis">{celdas}</div>')


def pasos(items):
    """items: [(nombre, detalle, estado)] con estado en {'hecho', 'activo', 'error', ''}."""
    celdas = "".join(
        f'<div class="bg-paso {estado}"><div class="c">{"&#10003;" if estado == "hecho" else ("!" if estado == "error" else i)}</div>'
        f'<b>{escape(nombre)}</b>{escape(detalle)}</div>'
        for i, (nombre, detalle, estado) in enumerate(items, start=1))
    html(f'<div class="bg-pasos">{celdas}</div>')


def titulo(texto, subtitulo="", destino=st):
    sub = f'<span class="st">{escape(subtitulo)}</span>' if subtitulo else ""
    html(f'<div class="bg-titulo"><h3>{escape(texto)}</h3>{sub}</div>', destino)


def datos_solicitud(resumen):
    """Rejilla de datos de la solicitud (mismos textos que R.resumen_solicitud)."""
    celdas = "".join(f'<div class="bg-dato"><div class="e">{escape(k)}</div><div class="v">{escape(str(v))}</div></div>'
                     for k, v in resumen.items())
    html(f'<div class="bg-solicitud">{celdas}</div>')


def tarjeta_recomendado(nombre, puntaje, metricas, chips_html, ventaja=None, extra_html=""):
    """Tarjeta destacada del proveedor recomendado. metricas: [(etiqueta, valor)]."""
    mets = "".join(f'<div class="bg-dato"><div class="e">{escape(e)}</div><div class="v">{escape(str(v))}</div></div>'
                   for e, v in metricas)
    extra = f'<div class="ley">{escape(ventaja)}</div>' if ventaja else ""
    html(f'<div class="bg-reco"><div class="cab"><div class="prov"><div class="ico">{icono("camion", 26)}</div>'
         f'<div><div class="et">Recomendado</div><div class="nom">{escape(nombre)}</div></div></div>'
         f'<div class="pts"><div class="num">{puntaje:.1f}<small> /100</small></div>'
         f'<div class="ley">puntaje del Modelo 2 · no es una probabilidad</div>{extra}</div></div>'
         f'<div class="mets">{mets}</div><div class="chips">{chips_html}</div>{extra_html}</div>')


def partir_lista(texto):
    """'A (+1 pts); B (-2 pts)' -> ['A (+1 pts)', 'B (-2 pts)']; '—' o vacío -> []."""
    if not isinstance(texto, str) or texto.strip() in ("", "—", "-"):
        return []
    return [p.strip() for p in texto.split(";") if p.strip()]


def lista_fd(fortalezas, debilidades, contexto_f=(), contexto_d=()):
    """HTML de fortalezas (verde) y debilidades (rojo), con las de contexto específico aparte."""
    def items(lista, clase, marca):
        return "".join(f'<li class="{clase}"><span class="m">{marca}</span>{escape(t)}</li>' for t in lista)

    f = items(fortalezas, "f", "&#10003;") + items(contexto_f, "f ctx", "&#10003;")
    d = items(debilidades, "d", "!") + items(contexto_d, "d ctx", "!")
    f = f or '<li class="n">Sin fortalezas destacadas frente al promedio</li>'
    d = d or '<li class="n">Sin debilidades destacadas frente al promedio</li>'
    return (f'<div class="bg-fd"><div><div class="t f">Fortalezas</div><ul>{f}</ul></div>'
            f'<div><div class="t d">Debilidades</div><ul>{d}</ul></div></div>')


def barras_componentes(componentes):
    """componentes: [(etiqueta, valor 0-100)] -> barras horizontales."""
    filas = "".join(
        f'<div class="bg-barra"><span class="e">{escape(e)}</span>'
        f'<span class="b"><i style="width:{max(0.0, min(100.0, v)):.1f}%"></i></span>'
        f'<span class="v">{v:.1f}</span></div>'
        for e, v in componentes)
    return f'<div class="bg-barras">{filas}</div>'


def tarjeta_proveedor_html(posicion, nombre, fiabilidad, intervalo, chips_html, componentes, fd_html):
    return (f'<div class="bg-prov"><div class="cab"><div class="pos">#{posicion}</div>'
            f'<div class="nom">{escape(nombre)}</div>'
            f'<div class="fia"><b>{fiabilidad:.1f}</b><span>fiabilidad · IC 95 % {escape(intervalo)}</span></div></div>'
            f'<div class="chips">{chips_html}</div>{barras_componentes(componentes)}{fd_html}</div>')


def tarjetas_proveedores(tarjetas_html):
    html(f'<div class="bg-provs">{"".join(tarjetas_html)}</div>')


def navegacion_acceso(destino=st):
    """Menú de la barra lateral en las pantallas de acceso: solo 'Ingreso' está disponible antes de entrar."""
    bloqueadas = [("casa", "Inicio"), ("ruta", "Rutas"), ("camion", "Proveedores"), ("barras", "Análisis")]
    items = "".join(f'<div class="item bloq" title="Disponible después de ingresar">{icono(i, 20)}<span>{t}</span>'
                    f'{icono("candado", 14)}</div>' for i, t in bloqueadas)
    html(f'<nav class="bg-nav" aria-label="Navegación"><div class="item activo">{icono("candado", 20)}'
         f'<span>Ingreso</span></div>{items}<div class="nota">Las demás secciones se habilitan al ingresar.</div></nav>'
         f'<div class="bg-lema">DECISIONES<br>QUE MUEVEN<br>EL MUNDO</div><div class="bg-foto-lateral"></div>', destino)


def cabecera_acceso():
    """Fila superior de la tarjeta de acceso: logo en línea, lema e insignia de estado (sin sesión)."""
    html('<div class="bg-cab-acceso"><div class="izq"><div class="bg-logo linea"><span class="l1">BEEP'
         '<span class="amp">&amp;</span>GO<span class="fl">&#10140;</span></span><span class="sub">BY COSCO SHIPPING</span></div>'
         '<span class="lema-acceso">Recomendador de transporte terrestre<br>Ingreso seguro con reconocimiento facial o PIN</span></div>'
         f'<div class="bg-top-acceso">{icono("escudo", 18)}<span><b>Acceso de operadores autorizados</b>'
         '<small>Sin sesión iniciada</small></span></div></div>')


def bienvenida():
    html('<div class="bg-bienvenida"><h2>Te damos la bienvenida</h2>'
         '<p>Inicia sesión para acceder a tu espacio de operaciones.</p></div>')


def pista_camara():
    html(f'<div class="bg-pista">{icono("rostro", 22)}<div><b>Buena iluminación y rostro descubierto</b>'
         f'<span>Permita el acceso a la cámara en el navegador si se lo pide.</span></div></div>')


def panel_ingreso_seguro():
    """Panel informativo. Cada afirmación corresponde a cómo funciona hoy el ingreso (ver CLAUDE.md)."""
    filas = [
        ("persona", "Reconocimiento facial", "Acceso para operadores registrados previamente por un administrador."),
        ("candado", "PIN de respaldo", "Alternativa si la cámara no está disponible, con intentos limitados."),
        ("escudo", "Protección de datos", "Solo se guarda una huella numérica del rostro, nunca fotos (Ley 1581 de 2012)."),
    ]
    items = "".join(f'<div class="fila"><div class="ico">{icono(i, 20)}</div><div><b>{escape(t)}</b>'
                    f'<span>{escape(d)}</span></div></div>' for i, t, d in filas)
    html(f'<aside class="bg-seguro"><div class="escudo">{icono("escudo", 34)}</div><h3>Ingreso seguro</h3>'
         f'<p>Protegemos el acceso a la información de operaciones.</p>{items}</aside>')


def encabezado_onboarding():
    html('<div class="bg-onb-cab"><span class="bg-chip rojo">Configuración inicial · paso único</span>'
         '<h1>¿Cómo prefieres explorar tu operación logística?</h1>'
         '<p>Personaliza tu experiencia para consultar rutas, comparar proveedores y tomar decisiones de la manera '
         'que te resulte más cómoda.</p></div>')


# Mapa ilustrativo de Colombia (contorno aproximado; NO es un mapa funcional).
_CONTORNO_CO = [(-77.3, 8.6), (-76.0, 9.4), (-75.5, 10.5), (-74.8, 11.0), (-73.5, 11.3), (-72.2, 12.4), (-71.2, 12.0),
                (-72.5, 11.0), (-72.4, 8.3), (-72.0, 7.0), (-70.1, 7.0), (-67.8, 6.2), (-67.5, 5.5), (-67.8, 4.0),
                (-67.3, 2.0), (-67.0, 1.2), (-69.8, 1.1), (-69.4, -1.5), (-69.9, -4.2), (-70.4, -3.8), (-70.0, -2.5),
                (-72.5, -2.4), (-74.0, -1.0), (-75.3, -0.1), (-77.0, 0.4), (-78.8, 1.4), (-77.5, 3.5), (-77.3, 4.5),
                (-77.4, 6.5), (-77.9, 7.2)]
_CIUDADES_CO = {"Bogotá": (-74.07, 4.71), "Barranquilla": (-74.80, 10.96), "Medellín": (-75.58, 6.24),
                "Cali": (-76.53, 3.45), "Bucaramanga": (-73.12, 7.12), "Cartagena": (-75.48, 10.39)}


def _xy(lon, lat):
    return (lon + 79.5) * 15, (12.8 - lat) * 15


def _preview_mapa():
    contorno = " ".join(f"{x:.0f},{y:.0f}" for x, y in (_xy(*p) for p in _CONTORNO_CO))
    puntos = "".join(f'<circle cx="{_xy(*c)[0]:.0f}" cy="{_xy(*c)[1]:.0f}" r="3.5" fill="#2F5BEA"/>'
                     for n, c in _CIUDADES_CO.items() if n not in ("Bogotá", "Barranquilla"))
    (x1, y1), (x2, y2) = _xy(*_CIUDADES_CO["Bogotá"]), _xy(*_CIUDADES_CO["Barranquilla"])
    return (f'<svg viewBox="0 0 400 260" role="img" aria-label="Vista previa ilustrativa de un mapa de Colombia con una ruta">'
            f'<rect width="400" height="260" fill="#DCEBFA"/>'
            f'<polygon points="{contorno}" fill="#F4F8FD" stroke="#9DB7DE" stroke-width="2" transform="translate(70,22) scale(.92)"/>'
            f'<g transform="translate(70,22) scale(.92)">{puntos}'
            f'<path d="M{x1:.0f} {y1:.0f} Q {x1 - 40:.0f} {(y1 + y2) / 2:.0f} {x2:.0f} {y2:.0f}" fill="none" stroke="#D7263D" '
            f'stroke-width="4" stroke-dasharray="9 6" stroke-linecap="round"/>'
            f'<circle cx="{x1:.0f}" cy="{y1:.0f}" r="7" fill="#2F5BEA" stroke="#fff" stroke-width="3"/>'
            f'<circle cx="{x2:.0f}" cy="{y2:.0f}" r="7" fill="#D7263D" stroke="#fff" stroke-width="3"/></g>'
            f'<g transform="translate(250,150)"><rect width="138" height="92" rx="12" fill="#fff" stroke="#E3E8F0"/>'
            f'<text x="12" y="22" font-size="11" font-weight="700" fill="#0B1F4D">Bogotá → Barranquilla</text>'
            f'<text x="12" y="42" font-size="9.5" fill="#6B7A90">Origen · Destino</text>'
            f'<rect x="12" y="52" width="114" height="7" rx="3.5" fill="#EEF2F8"/><rect x="12" y="52" width="80" height="7" rx="3.5" fill="#2F5BEA"/>'
            f'<rect x="12" y="68" width="114" height="7" rx="3.5" fill="#EEF2F8"/><rect x="12" y="68" width="56" height="7" rx="3.5" fill="#D7263D"/></g>'
            f'</svg>')


_PREVIEWS = {
    "dashboard": ('<img src="app/static/onboarding_dashboard.png" alt="Captura del dashboard actual de BEEP &amp; GO">',
                  "Captura real del dashboard actual"),
    "mapa": (None, "Vista previa ilustrativa · el mapa se construye en la siguiente fase"),
    "mundo_virtual": ('<img src="app/static/onboarding_mundo3d.png" alt="Captura del mundo virtual 3D existente">',
                      "Captura real del mundo 3D existente"),
}
_ICONO_VISTA = {"dashboard": "barras", "mapa": "mapa", "mundo_virtual": "caja"}


def tarjeta_onboarding(vista, titulo, descripcion, seleccionada=False):
    imagen, nota = _PREVIEWS[vista]
    imagen = imagen or _preview_mapa()
    marca = '<span class="sel">&#10003; Seleccionada</span>' if seleccionada else ""
    clase = "bg-onb seleccionada" if seleccionada else "bg-onb"
    html(f'<div class="{clase}" aria-selected="{str(seleccionada).lower()}"><div class="prev">{imagen}{marca}</div>'
         f'<div class="cuerpo"><div class="tit"><span class="ico">{icono(_ICONO_VISTA[vista], 18)}</span>{escape(titulo)}</div>'
         f'<p>{escape(descripcion)}</p><span class="nota">{escape(nota)}</span></div></div>')


def aviso_vista_pendiente(titulo, texto, enlace=None, texto_enlace=None):
    boton = (f'<a class="bg-pend-link" href="{escape(enlace)}" target="_blank" rel="noopener">{escape(texto_enlace)} ↗</a>'
             if enlace else "")
    html(f'<div class="bg-pend"><div class="ico">{icono("alerta", 22)}</div><div><b>{escape(titulo)}</b>'
         f'<p>{escape(texto)}</p>{boton}</div></div>')


def estrellas(calificacion):
    """Chip con estrellas SOLO si hay calificación real de clientes (satisfaccion_1a5); si no, 'No disponible'."""
    if not calificacion or calificacion.get("promedio") is None:
        return chip("Calificación de clientes: No disponible", "gris")
    p, n = calificacion["promedio"], calificacion["n"]
    llenas = int(round(p))
    n_txt = f"{n:,}".replace(",", ".")
    return (f'<span class="bg-chip ambar" title="Promedio de {n_txt} calificaciones de clientes (1 a 5)">'
            f'{"&#9733;" * llenas}{"&#9734;" * (5 - llenas)} {p:.1f} · {n_txt} calificaciones</span>')


def portada_acceso():
    html(f'<div class="bg-acceso">{logo_html(grande=True)}'
         '<p>Recomendador de transporte terrestre · Ingreso seguro con reconocimiento facial o PIN</p></div>')
