"""Vista "Mapa de Colombia": dibuja la MISMA recomendación que el dashboard, leyendo el contrato compartido.

No recalcula nada. Limitaciones (dichas también en pantalla):
- La base no trae coordenadas: se usan las de referencia de config/ciudades.yaml (aproximadas, sin verificar).
- No hay geometría vial: la ruta es una línea recta entre ciudades, no la carretera.
- Los proveedores no tienen ubicación en la base: se listan en el panel, no se ubican en el mapa.
- El mapa base (Carto) se descarga de internet; sin conexión se ven las capas sobre fondo vacío.
"""

import unicodedata

import pydeck as pdk
import streamlit as st

from src import recomendacion as R
from src.ui import componentes as UI

AZUL, ROJO, GRIS = [47, 91, 234], [215, 38, 61], [107, 122, 144]


def _ascii(texto):
    """Etiqueta del TextLayer sin tildes: su atlas de fuentes solo trae ASCII y pydeck no permite ampliarlo
    (character_set se interpreta como expresión). El tooltip conserva el nombre con tildes."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _capas(contrato, coordenadas):
    s = contrato["solicitud"]
    puntos = [{"ciudad": n, "etiqueta": _ascii(n), "lat": c["lat"], "lon": c["lon"],
               "rol": "Origen" if n == s["origen"] else "Destino" if n == s["destino"] else "Ciudad de la base",
               "color": AZUL if n == s["origen"] else ROJO if n == s["destino"] else GRIS,
               "radio": 16000 if n in (s["origen"], s["destino"]) else 7000}
              for n, c in coordenadas["ciudades"].items()]
    capas = [
        pdk.Layer("ScatterplotLayer", puntos, get_position="[lon, lat]", get_fill_color="color",
                  get_radius="radio", radius_min_pixels=4, pickable=True, stroked=True,
                  get_line_color=[255, 255, 255], line_width_min_pixels=2),
        pdk.Layer("TextLayer", puntos, get_position="[lon, lat]", get_text="etiqueta", get_size=13,
                  get_color=[11, 31, 77], get_pixel_offset=[0, -16], font_weight=600),
    ]
    geo = contrato.get("geografia") or {}
    if geo.get("origen") and geo.get("destino"):
        o, d = geo["origen"], geo["destino"]
        ruta = [{"desde": [o["lon"], o["lat"]], "hasta": [d["lon"], d["lat"]],
                 "ciudad": f"{s['origen']} → {s['destino']}", "rol": "Línea recta (no es la carretera)"}]
        capas.insert(0, pdk.Layer("LineLayer", ruta, get_source_position="desde", get_target_position="hasta",
                                  get_color=ROJO, get_width=5, pickable=True))
    return capas


def _panel(contrato):
    s = contrato["solicitud"]
    UI.titulo(f"{s['origen']} → {s['destino']}", f"Solicitud {s['id'] or ''}")
    distancia = f"{s['distancia_km']:,.0f} km".replace(",", ".") if s["distancia_km"] is not None else "No disponible"
    filas = [("Distancia (base)", distancia), ("Zona", s["zona"] or "No disponible"),
             ("Contenedor", s["tipo_contenedor"] or "No disponible"),
             ("Tipo de vehículo", "No disponible"), ("Estado de la vía", "No disponible")]
    UI.html('<div class="bg-mapa-datos">' + "".join(
        f'<div><span>{e}</span><b>{v}</b></div>' for e, v in filas) + "</div>")
    if contrato["estado"] != "ok":
        st.error("Ningún proveedor cumple todos los requisitos de esta solicitud.")
        return
    top = contrato["elegibles"][0]
    st.success(f"Recomendado: **{top['proveedor']}** · {R.formatear_cop(top['precio_cop'])} · "
               f"{R.formatear_horas(top['tiempo_esperado_h'])} · puntaje {top['puntaje']:.1f}")
    UI.html('<div class="bg-mapa-lista">' + "".join(
        f'<div class="{"top" if e["posicion"] == 1 else ""}"><span>#{e["posicion"]} {e["proveedor"]}</span>'
        f'<b>{e["puntaje"]:.1f}</b></div>' for e in contrato["elegibles"]) + "</div>")
    if contrato["excluidos"]:
        st.caption(f"{len(contrato['excluidos'])} proveedor(es) excluido(s) por requisitos obligatorios "
                   "(ver pestaña Recomendación).")


def mostrar_mapa(contrato, coordenadas):
    if contrato is None:
        st.info("Seleccione una solicitud válida para verla en el mapa.")
        return
    if coordenadas is None:
        st.error("No se pudieron leer las coordenadas de referencia (config/ciudades.yaml): no se dibuja el mapa.")
        return
    faltan = [c for c in (contrato["solicitud"]["origen"], contrato["solicitud"]["destino"])
              if c not in coordenadas["ciudades"]]
    with st.container(border=True, key="tarjeta_mapa"):
        UI.titulo("Mapa de Colombia", "La misma solicitud y recomendación que el dashboard")
        mapa, panel = st.columns([1.7, 1], gap="medium")
        with mapa:
            if faltan:
                st.warning(f"Sin coordenadas de referencia para {', '.join(faltan)}: no se dibuja la ruta.")
            st.pydeck_chart(pdk.Deck(
                layers=_capas(contrato, coordenadas), map_provider="carto", map_style="light",
                initial_view_state=pdk.ViewState(latitude=6.4, longitude=-74.6, zoom=4.7),
                tooltip={"text": "{ciudad}\n{rol}"}), height=500, key="mapa_colombia")
            st.caption("Línea recta entre ciudades: no representa la carretera. Coordenadas de referencia "
                       "aproximadas (sin verificar), no provienen de la base. Los proveedores no tienen "
                       "ubicación en la base, por eso se listan a la derecha.")
        with panel:
            _panel(contrato)
