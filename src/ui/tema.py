"""Tema visual BEEP & GO: CSS inyectado una vez por página. Solo apariencia."""

import streamlit as st

COLORES = {
    "marino": "#0B1F4D",
    "azul": "#2F5BEA",
    "rojo": "#D7263D",
    "fondo": "#F3F6FB",
    "borde": "#E3E8F0",
    "gris": "#6B7A90",
    "verde": "#2E9E6A",
    "ambar": "#E0A100",
}

# Colores de los factores del puntaje en los gráficos (precio, tiempo, fiabilidad).
COLORES_FACTORES = ["#2F5BEA", "#F2A93B", "#2E9E6A"]

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root { --marino:#0B1F4D; --azul:#2F5BEA; --azul-suave:#E8EFFE; --rojo:#D7263D; --rojo-suave:#FDECEE;
  --verde:#2E9E6A; --verde-suave:#E6F5EE; --ambar:#B07D00; --ambar-suave:#FFF4D6; --gris:#6B7A90;
  --gris-suave:#EEF2F8; --borde:#E3E8F0; --texto:#14213D;
  --sombra:0 8px 24px rgba(11,31,77,.07), 0 1px 3px rgba(11,31,77,.05); }
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, button, input, select, textarea { font-family: 'Inter', system-ui, 'Segoe UI', sans-serif; }
/* los íconos de Streamlit usan su propia fuente: no la pisamos */
[data-testid="stIconMaterial"], .material-symbols-rounded, span[class*="material"] { font-family: 'Material Symbols Rounded' !important; }
.stApp { background: radial-gradient(1200px 500px at 85% -10%, #E3ECFD 0%, rgba(243,246,251,0) 60%), #F3F6FB; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1380px; }
h1, h2, h3, h4 { color: var(--marino); letter-spacing: -.01em; }
h1 { font-weight: 800; }

/* ---------- barra lateral */
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid var(--borde); }
[data-testid="stSidebar"] .block-container, [data-testid="stSidebarContent"] { padding-top: .6rem; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--gris); }

/* ---------- tarjetas (contenedores con borde) */
[data-testid="stVerticalBlockBorderWrapper"], div[class*="st-key-tarjeta"] {
  background: #FFFFFF; border: 1px solid var(--borde) !important; border-radius: 18px !important; box-shadow: var(--sombra); }

/* ---------- métricas nativas */
[data-testid="stMetric"] { background: var(--gris-suave); border-radius: 14px; padding: 12px 14px; }
[data-testid="stMetricLabel"] p { color: var(--gris); font-size: 12px; font-weight: 600; }
[data-testid="stMetricValue"] { color: var(--marino); font-size: 20px; font-weight: 700; }

/* ---------- avisos */
[data-testid="stAlert"], [data-testid="stAlertContainer"] { border-radius: 14px; border: 0; }
[data-testid="stAlertContentSuccess"], [data-testid="stAlertContentInfo"], [data-testid="stAlertContentWarning"], [data-testid="stAlertContentError"] { font-size: 14px; line-height: 1.5; }

/* ---------- pestañas como píldoras (Streamlit 1.66: role=tablist / data-testid=stTab) */
[data-testid="stTabs"] [role="tablist"] { gap: 6px; background: #FFFFFF; padding: 6px; border-radius: 14px; border: 1px solid var(--borde); box-shadow: var(--sombra); width: fit-content; max-width: 100%; }
[data-testid="stTabs"] [role="tablist"]::after, [data-testid="stTabs"] [role="tablist"]::before { display: none; }
[data-testid="stTab"] { border-radius: 10px !important; padding: 8px 16px !important; color: var(--gris); border: 0 !important; margin: 0 !important; }
[data-testid="stTab"] p { font-weight: 600; font-size: 14px; }
[data-testid="stTab"]:hover { background: var(--gris-suave); }
[data-testid="stTab"][aria-selected="true"] { background: var(--azul) !important; color: #FFFFFF !important; box-shadow: 0 4px 12px rgba(47,91,234,.25); }
[data-testid="stTab"][aria-selected="true"] p, [data-testid="stTab"][aria-selected="true"] span { color: #FFFFFF !important; }
[data-testid="stTabs"] [role="tabpanel"] { padding-top: 18px; }

/* ---------- botones */
.stButton button, .stFormSubmitButton button { border-radius: 10px; font-weight: 600; padding: 8px 18px; border: 1px solid var(--borde); transition: transform .15s, box-shadow .15s; }
.stButton button:hover, .stFormSubmitButton button:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(47,91,234,.18); }
.st-key-lote button, .stFormSubmitButton button { background: var(--rojo); color: #FFFFFF; border: 0; box-shadow: 0 6px 16px rgba(215,38,61,.25); }
.st-key-lote button:hover, .stFormSubmitButton button:hover { background: #B81D31; color: #FFFFFF; }

/* ---------- tablas, expansores y controles */
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid var(--borde); }
[data-testid="stExpander"] details { border-radius: 14px; border: 1px solid var(--borde); background: #FFFFFF; }
[data-testid="stExpander"] summary p { font-weight: 600; color: var(--marino); }
[data-baseweb="select"] > div, [data-testid="stTextInput"] input { border-radius: 10px; }
[data-testid="stCameraInput"] { border-radius: 16px; overflow: hidden; }

/* ---------- componentes propios (src/ui/componentes.py) */
.bg-logo { display: flex; flex-direction: column; line-height: .92; padding: 4px 2px 10px; }
.bg-logo .l1, .bg-logo .l2 { font-weight: 900; font-size: 30px; color: var(--marino); letter-spacing: -.02em; }
.bg-logo .l2 .amp, .bg-logo .l2 .fl { color: var(--rojo); }
.bg-logo .sub { font-size: 10.5px; font-weight: 700; letter-spacing: .14em; color: var(--marino); margin-top: 8px; }
.bg-logo.grande .l1, .bg-logo.grande .l2 { font-size: 46px; }
.bg-logo.grande .sub { font-size: 13px; }
.bg-seccion { font-size: 11px; font-weight: 700; letter-spacing: .08em; color: var(--gris); text-transform: uppercase; margin: 14px 0 6px; }
.bg-datos { background: var(--gris-suave); border-radius: 14px; padding: 12px 14px; font-size: 13px; line-height: 1.55; color: var(--texto); }
.bg-datos code { background: #FFFFFF; color: var(--azul); border-radius: 6px; padding: 1px 6px; font-size: 10.5px; white-space: nowrap; display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
.bg-encabezado { display: flex; align-items: center; justify-content: space-between; gap: 18px; background: #FFFFFF; border: 1px solid var(--borde); border-radius: 20px; padding: 18px 22px; box-shadow: var(--sombra); margin-bottom: 14px; }
.bg-encabezado .tit { display: flex; gap: 14px; align-items: center; }
.bg-encabezado .ico { width: 46px; height: 46px; border-radius: 14px; background: var(--azul-suave); color: var(--azul); display: grid; place-items: center; flex: none; }
.bg-encabezado h1 { font-size: 22px; margin: 0; padding: 0; line-height: 1.2; }
.bg-encabezado .st { color: var(--gris); font-size: 13.5px; margin-top: 2px; }
.bg-encabezado .der { display: flex; gap: 12px; align-items: center; flex: none; }
.bg-usuario { display: flex; gap: 10px; align-items: center; }
.bg-usuario .av { width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, var(--azul), var(--marino)); color: #FFFFFF; font-weight: 700; display: grid; place-items: center; font-size: 14px; }
.bg-usuario .n { font-weight: 700; color: var(--marino); font-size: 14px; }
.bg-usuario .r { font-size: 12px; color: var(--gris); }
.bg-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; padding: 5px 11px; border-radius: 999px; white-space: nowrap; }
.bg-chip.rojo { background: var(--rojo-suave); color: var(--rojo); }
.bg-chip.azul { background: var(--azul-suave); color: var(--azul); }
.bg-chip.verde { background: var(--verde-suave); color: var(--verde); }
.bg-chip.ambar { background: var(--ambar-suave); color: var(--ambar); }
.bg-chip.gris { background: var(--gris-suave); color: var(--gris); }
.bg-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
.bg-kpi { background: #FFFFFF; border: 1px solid var(--borde); border-radius: 16px; padding: 14px 16px; display: flex; gap: 12px; align-items: center; box-shadow: var(--sombra); }
.bg-kpi .ico { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; flex: none; }
.bg-kpi .v { font-size: 20px; font-weight: 800; color: var(--marino); line-height: 1.1; }
.bg-kpi .e { font-size: 12px; color: var(--gris); margin-top: 2px; }
.bg-pasos { display: flex; align-items: flex-start; justify-content: space-between; margin: 4px 6px 18px; position: relative; }
.bg-paso { flex: 1; text-align: center; position: relative; font-size: 12.5px; color: var(--gris); }
.bg-paso:not(:last-child)::after { content: ""; position: absolute; top: 17px; left: calc(50% + 22px); right: calc(-50% + 22px); height: 3px; border-radius: 3px; background: var(--borde); }
.bg-paso.hecho:not(:last-child)::after { background: var(--azul); }
.bg-paso .c { width: 36px; height: 36px; border-radius: 50%; margin: 0 auto 6px; display: grid; place-items: center; font-weight: 800; background: #FFFFFF; border: 2px solid var(--borde); color: var(--gris); }
.bg-paso.hecho .c { background: var(--azul); border-color: var(--azul); color: #FFFFFF; }
.bg-paso.activo .c { background: var(--rojo); border-color: var(--rojo); color: #FFFFFF; box-shadow: 0 0 0 6px rgba(215,38,61,.14); }
.bg-paso.error .c { background: var(--rojo-suave); border-color: var(--rojo); color: var(--rojo); }
.bg-paso b { display: block; color: var(--marino); font-size: 13px; }
.bg-titulo { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin: 2px 0 10px; }
.bg-titulo h3 { margin: 0; padding: 0; font-size: 18px; font-weight: 800; }
.bg-titulo .st { color: var(--gris); font-size: 13px; }
.bg-solicitud { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.bg-dato { background: var(--gris-suave); border-radius: 12px; padding: 10px 12px; }
.bg-dato .e { font-size: 11.5px; color: var(--gris); font-weight: 600; }
.bg-dato .v { font-size: 15px; color: var(--marino); font-weight: 700; margin-top: 2px; }
.bg-reco { border: 1px solid var(--borde); border-left: 5px solid var(--rojo); border-radius: 16px; padding: 16px 18px; background: linear-gradient(180deg, #FFFFFF 0%, #FFFAFB 100%); }
.bg-reco .cab { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.bg-reco .prov { display: flex; gap: 12px; align-items: center; }
.bg-reco .ico { width: 50px; height: 50px; border-radius: 14px; background: var(--azul-suave); color: var(--azul); display: grid; place-items: center; flex: none; }
.bg-reco .et { font-size: 11px; font-weight: 800; letter-spacing: .08em; color: var(--rojo); text-transform: uppercase; }
.bg-reco .nom { font-size: 22px; font-weight: 800; color: var(--marino); line-height: 1.15; }
.bg-reco .pts { text-align: right; }
.bg-reco .pts .num { font-size: 34px; font-weight: 800; color: var(--marino); line-height: 1; }
.bg-reco .pts .num small { font-size: 14px; color: var(--gris); font-weight: 600; }
.bg-reco .pts .ley { font-size: 10.5px; color: var(--gris); }
.bg-reco .mets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 14px; }
.bg-reco .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.bg-fd { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 14px; }
.bg-fd .t { font-size: 11px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 6px; }
.bg-fd .t.f { color: var(--verde); }
.bg-fd .t.d { color: var(--rojo); }
.bg-fd ul { list-style: none; margin: 0; padding: 0; }
.bg-fd li { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; line-height: 1.35; padding: 7px 10px; border-radius: 10px; margin-bottom: 6px; color: var(--texto); }
.bg-fd li .m { width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 800; flex: none; margin-top: 1px; color: #FFFFFF; }
.bg-fd li.f { background: var(--verde-suave); }
.bg-fd li.f .m { background: var(--verde); }
.bg-fd li.d { background: var(--rojo-suave); }
.bg-fd li.d .m { background: var(--rojo); }
.bg-fd li.ctx { border: 1px dashed var(--borde); }
.bg-fd li.ctx::after { content: "contexto específico"; margin-left: auto; font-size: 10px; color: var(--gris); white-space: nowrap; padding-left: 6px; }
.bg-fd li.n { background: var(--gris-suave); color: var(--gris); font-size: 12.5px; }
.bg-provs { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 14px; }
.bg-prov { background: #FFFFFF; border: 1px solid var(--borde); border-radius: 16px; padding: 16px 18px; box-shadow: var(--sombra); height: 100%; }
.bg-prov .cab { display: flex; align-items: center; gap: 12px; }
.bg-prov .pos { width: 38px; height: 38px; border-radius: 12px; background: var(--azul-suave); color: var(--azul); font-weight: 800; display: grid; place-items: center; flex: none; }
.bg-prov .nom { font-size: 18px; font-weight: 800; color: var(--marino); flex: 1; line-height: 1.2; }
.bg-prov .fia { text-align: right; }
.bg-prov .fia b { display: block; font-size: 26px; color: var(--marino); line-height: 1; }
.bg-prov .fia span { font-size: 10.5px; color: var(--gris); }
.bg-prov .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 4px; }
.bg-barras { margin-top: 10px; }
.bg-barra { display: grid; grid-template-columns: 120px 1fr 40px; align-items: center; gap: 10px; font-size: 12.5px; margin-bottom: 7px; }
.bg-barra .e { color: var(--gris); font-weight: 600; }
.bg-barra .b { height: 8px; background: var(--gris-suave); border-radius: 99px; overflow: hidden; }
.bg-barra .b i { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--azul), #5B8DEF); }
.bg-barra .v { text-align: right; font-weight: 700; color: var(--marino); }
.bg-reco .bg-fd { margin-top: 12px; }
.bg-acceso { text-align: center; padding: 26px 0 8px; }
.bg-acceso .bg-logo { align-items: center; }
.bg-acceso p { color: var(--gris); font-size: 14.5px; margin: 10px 0 0; }
.bg-nav { margin-top: 18px; display: flex; flex-direction: column; gap: 4px; }
.bg-nav .item { display: flex; align-items: center; gap: 12px; padding: 11px 14px; border-radius: 14px; font-weight: 600; font-size: 15px; color: var(--marino); }
.bg-nav .item.activo { background: var(--rojo-suave); color: var(--marino); box-shadow: inset 4px 0 0 var(--rojo); }
.bg-nav .item.activo svg:first-child { color: var(--rojo); }
.bg-nav .item.bloq { color: #93A0B4; cursor: not-allowed; }
.bg-nav .item.bloq svg:last-child { margin-left: auto; opacity: .7; }
.bg-nav .nota { font-size: 11.5px; color: var(--gris); padding: 6px 14px 0; }
.bg-lema { margin: 26px 14px 10px; font-size: 12.5px; font-weight: 700; letter-spacing: .22em; line-height: 1.7; color: var(--marino); }
.bg-foto-lateral { height: 170px; margin: 8px 6px 0; border-radius: 18px; background: url("app/static/puerto.webp") 72% 60% / cover no-repeat; box-shadow: var(--sombra); }
.bg-top-acceso { position: relative; width: fit-content; margin: 0 0 -46px auto; z-index: 5; display: flex; align-items: center; gap: 10px; background: rgba(255,255,255,.88); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,.8); border-radius: 999px; padding: 8px 16px 8px 12px; box-shadow: var(--sombra); color: var(--azul); }
.bg-top-acceso b { display: block; color: var(--marino); font-size: 13px; }
.bg-top-acceso small { color: var(--gris); font-size: 11.5px; }
.bg-bienvenida h2 { font-size: 34px; font-weight: 800; color: var(--marino); margin: 4px 0 2px; padding: 0; letter-spacing: -.02em; }
.bg-bienvenida p { color: var(--gris); font-size: 15.5px; margin: 0 0 14px; }
.bg-pista { display: flex; gap: 12px; align-items: center; background: #FFFFFF; border: 1px solid var(--borde); border-radius: 16px; padding: 12px 16px; margin: 4px 0 12px; color: var(--azul); }
.bg-pista b { display: block; color: var(--marino); font-size: 14px; }
.bg-pista span { color: var(--gris); font-size: 12.5px; }
.bg-seguro { border-left: 1px solid var(--borde); padding: 8px 0 8px 28px; text-align: center; height: 100%; }
.bg-seguro .escudo { width: 84px; height: 84px; border-radius: 50%; margin: 6px auto 12px; display: grid; place-items: center; color: var(--azul); background: radial-gradient(circle, #FFFFFF 0%, var(--azul-suave) 100%); box-shadow: 0 8px 22px rgba(47,91,234,.18); }
.bg-seguro h3 { font-size: 22px; font-weight: 800; margin: 0; padding: 0; }
.bg-seguro p { color: var(--gris); font-size: 14px; margin: 6px 0 18px; }
.bg-seguro .fila { display: flex; gap: 14px; align-items: center; text-align: left; background: #FFFFFF; border: 1px solid var(--borde); border-radius: 16px; padding: 14px 16px; margin-bottom: 12px; box-shadow: 0 4px 14px rgba(11,31,77,.05); }
.bg-seguro .fila .ico { width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; flex: none; color: var(--azul); background: var(--azul-suave); }
.bg-seguro .fila b { display: block; color: var(--marino); font-size: 14.5px; }
.bg-seguro .fila span { color: var(--gris); font-size: 13px; line-height: 1.4; }
/* ---------- onboarding de interfaz */
.bg-onb-cab { text-align: center; margin: -1.2rem auto clamp(8px, 1.6dvh, 20px); max-width: 860px; }
.bg-onb-cab h1 { font-size: clamp(24px, 3.6dvh, 34px); margin: 10px 0 6px; padding: 0; }
.bg-onb-cab p { color: var(--gris); font-size: 15px; margin: 0; }
.bg-onb { background: #FFFFFF; border: 2px solid var(--borde); border-radius: 18px; overflow: hidden; box-shadow: var(--sombra); transition: border-color .15s, box-shadow .15s, transform .15s; }
.bg-onb:hover { transform: translateY(-2px); }
.bg-onb.seleccionada { border-color: var(--rojo); box-shadow: 0 0 0 4px rgba(215,38,61,.12), var(--sombra); }
.bg-onb .prev { position: relative; aspect-ratio: 400 / 205; background: #DCEBFA; overflow: hidden; border-bottom: 1px solid var(--borde); }
.bg-onb .prev img, .bg-onb .prev svg { width: 100%; height: 100%; object-fit: cover; object-position: center top; display: block; }
.bg-onb .sel { position: absolute; top: 10px; right: 10px; background: var(--rojo); color: #FFFFFF; font-size: 12px; font-weight: 700; padding: 5px 10px; border-radius: 999px; box-shadow: 0 4px 10px rgba(215,38,61,.3); }
.bg-onb .cuerpo { padding: clamp(10px, 1.6dvh, 16px) 16px; }
.bg-onb .tit { display: flex; align-items: center; gap: 10px; font-size: 17px; font-weight: 800; color: var(--marino); }
.bg-onb .tit .ico { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; background: var(--azul-suave); color: var(--azul); }
.bg-onb p { color: var(--texto); font-size: 14px; line-height: 1.45; margin: 6px 0 4px; min-height: 2.9em; }
.bg-onb .nota { display: block; min-height: 2.8em; font-size: 11.5px; line-height: 1.4; color: var(--gris); font-style: italic; }
div[class*="st-key-tarjeta_onb_"] { gap: 10px; }
.st-key-onboarding_continuar button { background: var(--rojo); border: 0; color: #FFFFFF; padding: 10px; font-size: 15px; box-shadow: 0 8px 18px rgba(215,38,61,.25); }
.st-key-onboarding_continuar button:disabled { background: #C8D1DF; color: #FFFFFF; box-shadow: none; }
.bg-pend { display: flex; gap: 14px; align-items: flex-start; background: #FFFFFF; border: 1px solid var(--borde); border-left: 5px solid var(--ambar); border-radius: 16px; padding: 14px 18px; margin-bottom: 14px; box-shadow: var(--sombra); }
.bg-pend .ico { color: var(--ambar); flex: none; }
.bg-pend b { color: var(--marino); font-size: 15px; }
.bg-pend p { margin: 4px 0 6px; color: var(--texto); font-size: 14px; }
.bg-pend-link { font-weight: 700; color: var(--azul); text-decoration: none; }
.bg-mapa-datos { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.bg-mapa-datos div { background: var(--gris-suave); border-radius: 12px; padding: 8px 10px; }
.bg-mapa-datos span { display: block; font-size: 11.5px; color: var(--gris); font-weight: 600; }
.bg-mapa-datos b { color: var(--marino); font-size: 14px; }
.bg-mapa-lista div { display: flex; justify-content: space-between; padding: 8px 10px; border-bottom: 1px solid var(--borde); font-size: 14px; }
.bg-mapa-lista div.top { background: var(--rojo-suave); border-radius: 10px; border: 0; font-weight: 700; }
.bg-mapa-lista b { font-family: ui-monospace, Consolas, monospace; color: var(--marino); }
@media (max-width: 640px) { .bg-seguro { border-left: 0; border-top: 1px solid var(--borde); padding: 20px 0 0; } }
@media (max-width: 1100px) { .bg-solicitud, .bg-reco .mets { grid-template-columns: repeat(2, 1fr); } .bg-encabezado { flex-wrap: wrap; } }
"""


def aplicar_tema():
    """Inyecta el CSS del tema (una vez por ejecución de la página)."""
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


# Pantallas de ingreso y bloqueo: fondo del puerto (static/puerto.webp, servido en app/static/)
# con velo azul claro, y el contenido principal como una tarjeta de vidrio.
_CSS_ACCESO = """
/* Todo cabe en una pantalla: tamaños ligados al alto visible (dvh) con mínimos legibles. */
.stApp {
  background:
    linear-gradient(180deg, rgba(236,243,255,.30) 0%, rgba(236,243,255,.12) 45%, rgba(11,31,77,.18) 100%),
    url("app/static/puerto.webp") center 62% / cover no-repeat fixed;
}
[data-testid="stSidebar"] { background: rgba(255,255,255,.80); backdrop-filter: blur(14px) saturate(140%); border-right: 1px solid rgba(255,255,255,.6); }
.block-container {
  max-width: 1080px; margin: clamp(10px, 3.5dvh, 44px) auto clamp(8px, 2dvh, 24px);
  padding: clamp(12px, 2.2dvh, 24px) clamp(18px, 2.6vw, 36px) clamp(14px, 2.4dvh, 26px) !important;
  background: rgba(255,255,255,.86); backdrop-filter: blur(16px) saturate(150%); -webkit-backdrop-filter: blur(16px) saturate(150%);
  border: 1px solid rgba(255,255,255,.75); border-radius: 26px; box-shadow: 0 30px 70px rgba(11,31,77,.20), 0 2px 8px rgba(11,31,77,.06);
}
.block-container [data-testid="stVerticalBlock"] { gap: clamp(.4rem, 1.1dvh, .9rem); }
/* encabezado de la tarjeta: logo en línea + lema + insignia */
.bg-cab-acceso { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-bottom: clamp(6px, 1.2dvh, 12px); border-bottom: 1px solid var(--borde); }
.bg-cab-acceso .izq { display: flex; align-items: center; gap: 18px; }
.bg-logo.linea { padding: 0; }
.bg-logo.linea .l1 { font-size: clamp(24px, 3.4dvh, 32px); }
.bg-logo.linea .amp, .bg-logo.linea .fl { color: var(--rojo); }
.bg-logo.linea .sub { margin-top: 4px; font-size: 10px; }
.lema-acceso { color: var(--gris); font-size: 13px; line-height: 1.45; border-left: 1px solid var(--borde); padding-left: 18px; }
.bg-top-acceso { margin: 0; }
/* columna del formulario */
.bg-bienvenida h2 { font-size: clamp(24px, 3.6dvh, 34px); margin: 0; }
.bg-bienvenida p { margin: 0 0 clamp(4px, 1dvh, 10px); font-size: clamp(13.5px, 1.8dvh, 15.5px); }
[data-testid="stTabs"] [role="tablist"] { width: 100%; background: var(--gris-suave); box-shadow: none; border: 0; padding: 4px; }
[data-testid="stTab"] { flex: 1; justify-content: center; padding: clamp(7px, 1.2dvh, 11px) 16px !important; }
[data-testid="stTabs"] [role="tabpanel"] { padding-top: clamp(8px, 1.4dvh, 16px); }
.bg-pista { padding: clamp(6px, 1dvh, 12px) 14px; margin: 0 0 clamp(18px, 2.4dvh, 24px); }  /* compensa el margen negativo que Streamlit pone a los bloques HTML */
.bg-pista b { font-size: 13.5px; }
/* cámara: su alto (4:3) se limita al alto disponible de la ventana */
[data-testid="stCameraInput"] { background: #FFFFFF; border: 1px solid var(--borde); border-radius: 18px; padding: 8px; box-shadow: var(--sombra);
  max-width: max(300px, calc((100dvh - 385px) * 4 / 3 + 18px)); margin: 0 auto; }
[data-testid="stCameraInput"] label p { font-size: 13px; }
[data-testid="stCameraInput"] video, [data-testid="stCameraInput"] img { border-radius: 12px; }
[data-testid="stCameraInput"] button { width: 100%; border-radius: 12px; border: 0; padding: clamp(8px, 1.3dvh, 13px); font-size: 15.5px; font-weight: 700;
  background: linear-gradient(90deg, #E8394F, var(--rojo)); color: #FFFFFF; box-shadow: 0 10px 22px rgba(215,38,61,.28); margin-top: 6px; }
[data-testid="stCameraInput"] button:hover { filter: brightness(.95); color: #FFFFFF; }
[data-testid="stCameraInput"] button:disabled { background: #C8D1DF; box-shadow: none; }
/* formulario PIN */
[data-testid="stForm"] { background: #FFFFFF; border: 1px solid var(--borde); border-radius: 18px; padding: clamp(12px, 2dvh, 20px); box-shadow: var(--sombra); }
.stFormSubmitButton, [data-testid="stFormSubmitButton"] { width: 100%; }
.stFormSubmitButton button, [data-testid="stFormSubmitButton"] button { width: 100%; padding: 11px; font-size: 15px; }
/* panel derecho compacto */
.bg-seguro { padding: 4px 0 4px 26px; }
.bg-seguro .escudo { width: clamp(52px, 8dvh, 80px); height: clamp(52px, 8dvh, 80px); margin: 0 auto clamp(6px, 1.2dvh, 12px); }
.bg-seguro h3 { font-size: clamp(18px, 2.6dvh, 22px); }
.bg-seguro p { margin: 4px 0 clamp(8px, 1.6dvh, 16px); font-size: 13.5px; }
.bg-seguro .fila { padding: clamp(8px, 1.4dvh, 14px) 14px; margin-bottom: clamp(6px, 1.2dvh, 12px); }
.bg-seguro .fila .ico { width: clamp(36px, 5dvh, 46px); height: clamp(36px, 5dvh, 46px); }
/* barra lateral compacta */
.bg-nav { margin-top: clamp(6px, 1.6dvh, 18px); }
.bg-nav .item { padding: clamp(7px, 1.25dvh, 11px) 14px; }
.bg-lema { margin: clamp(12px, 2.6dvh, 26px) 14px clamp(6px, 1dvh, 10px); }
.bg-foto-lateral { height: clamp(70px, 19dvh, 170px); }
@media (max-width: 1180px) {
  .block-container [data-testid="stHorizontalBlock"] { flex-direction: column; gap: 18px; }
  .block-container [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; }
  .bg-seguro { border-left: 0; border-top: 1px solid var(--borde); padding: 18px 0 0; }
}
@media (max-width: 900px) {
  .block-container { margin: 12px 8px; border-radius: 20px; }
  .bg-cab-acceso { flex-wrap: wrap; } .lema-acceso { border-left: 0; padding-left: 0; }
  [data-testid="stCameraInput"] { max-width: 100%; }
}
"""


def estilo_acceso():
    """CSS de las pantallas de ingreso y bloqueo (se quita al ingresar porque vive en un contenedor temporal)."""
    st.markdown(f"<style>{_CSS_ACCESO}</style>", unsafe_allow_html=True)
