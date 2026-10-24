# Contexto completo de BEEP & GO by COSCO SHIPPING (para retomar el trabajo)

> Léelo completo antes de hacer cambios. Resume todo lo hecho hasta el commit `cfb06ee`
> (rama `feat/interfaz-beep-and-go`). Fecha: 24 de octubre de 2026.

## Reto y producto
- Sabana Hack 2026, reto COSCO SHIPPING: recomendar, para cada solicitud de transporte terrestre, el
  proveedor más adecuado de forma rápida, consistente, explicable y basada en datos. El operador decide.
- 7 factores: precio, tránsito, tipo de vehículo, capacidad, desempeño histórico, puntualidad, fortalezas/debilidades.
- Nombre: **BEEP & GO by COSCO SHIPPING** (antes "ARGO"). Plan estratégico en Claude Docs:
  https://claude.ai/artifact/1sn6p4WNHxPoS3GwaDnESh (puede no ser accesible desde otra cuenta).

## Dos proyectos en el computador
| Proyecto | Ruta | Tecnología | Git |
|---|---|---|---|
| Recomendador (principal) | `Documents\recomendador_transporte` | Python 3.13 + Streamlit 1.66 | Sí (GitHub parra284/recomendador_transporte) |
| Mundo 3D / gafas | `Documents\argo-vr` | Vite + Three.js + WebXR (+ A-Frame en mapa.html) | **NO** (pendiente versionarlo) |

### Ejecutar
- Recomendador: `cd $HOME\Documents\recomendador_transporte` → `.venv\Scripts\python.exe -m streamlit run app.py` → http://localhost:8501
- Mundo 3D: `cd $HOME\Documents\argo-vr` → `npm.cmd run dev` → https://localhost:5173 (gafas: https://<IP del portátil>:5173, botón "Ver en AR")
- En PowerShell usar `npm.cmd` (los scripts .ps1 están bloqueados) y `.venv\Scripts\python.exe` (no `python`).
- **Tras editar `src/ui/*` reiniciar Streamlit** (no recarga esos módulos solo; causó un error de `lista_fd`).
- Pruebas: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` → 148 deben pasar.
  Mundo 3D: `node tools/probar_contrato.mjs <T-001.json> <T-004.json>` (contratos de `python -m src.contrato --solicitud T-00X --salida archivo.json`) → 5 pasan.

## Recomendador: lo que ya existía (del equipo)
- Base **v1** `data/base_simulada_mensajeria.xlsx` (hoja `Envios`, 31.386 envíos, 6 empresas de mensajería REALES con
  desempeño SIMULADO, 15 ciudades, contenedores Dry/Reefer/Open Top/Flat Rack). Única fuente de verdad del repo.
- Modelo 1 (`sistema_proveedores/modelo1_fiabilidad.py`): fiabilidad = puntualidad 40 % + magnitud del retraso 20 % +
  integridad 25 % + satisfacción 15 %, ajustada por dificultad; IC, tendencia, fortalezas/debilidades.
- Modelo 2 (`sistema_proveedores/modelo2_recomendador.py`, `Recomendador.recomendar()`): filtros duros del catálogo
  (contenedor, ciudades, peso máx., velocidad, velocidad-zona, cupos) → precio/tiempo vs mercado (Ridge/GB) →
  puntaje 0-100 con pesos por contenedor de `config/perfiles.yaml` → explicación, avisos (empate < 2 pts,
  concentración > 35 %, plazo), alternativas si nadie cumple. Cupos SIMULADOS (`capacidad_simulada`).
- Reparto del lote (PuLP/HiGHS), ingreso facial (YuNet+SFace, umbral 0,363), vigilancia de presencia (10 s, MediaPipe
  por internet), PIN de 4-8 dígitos con 5 intentos. Usuarios en `seguridad/usuarios.json` (fuera de git).
- **NO cambiar reglas de negocio (pesos, filtros, puntaje) sin aprobación del equipo.**

## Lo que hicimos (commit cfb06ee)
1. **Rediseño visual** (solo presentación): `src/ui/tema.py` (todo el CSS), `src/ui/componentes.py` (HTML: logo,
   encabezado, KPIs, pasos, tarjeta del recomendado, fortalezas/debilidades, etc.), `.streamlit/config.toml`.
   Paleta: marino #0B1F4D, azul #2F5BEA, rojo #D7263D, fondo #F3F6FB. Las pruebas exigen conservar: primer
   `st.dataframe` = top 3, explicación en `st.success`, claves `origen`, `solicitud`, `archivo`, `lote`.
2. **Fortalezas y debilidades** por proveedor (pestaña Proveedores) y en la tarjeta del recomendado (Modelo 1).
3. **Pantalla de ingreso**: fondo `static/puerto.webp` (Streamlit sirve `static/` en `app/static/`), tarjeta de vidrio,
   menú lateral con secciones bloqueadas, panel "Ingreso seguro"; sin scroll a 1366×768 y 1920×1080.
   Código: `src/pantalla_acceso.py` (solo presentación) + `_CSS_ACCESO` en tema.py.
4. **Ingreso solo con PIN** (sin usuario): `iniciar_solo_con_pin` en `src/sesion.py`; si el PIN coincide con varios
   usuarios no entra; `registrar_usuario` rechaza PIN repetidos (`pin_en_uso` en `src/usuarios.py`).
5. **Onboarding (Fase 2)**: tras ingresar, si el operador no tiene preferencia elige Dashboard / Mapa / Mundo 3D.
   `src/preferencias.py` (guarda en `seguridad/preferencias.json`, ids `dashboard`, `mapa`, `mundo_virtual`),
   `src/pantalla_onboarding.py` (pantalla + ⚙ Configuración en la barra lateral para cambiar de entorno).
   "Lo decidiré más adelante" no guarda. Vistas previas: `static/onboarding_dashboard.png`, `static/onboarding_mundo3d.png`.
6. **Datos compartidos (Fase 3)**: `src/contrato.py` convierte UNA recomendación del motor en un dict/JSON con
   procedencia (real/calculado/simulado/referencia/no_disponible). Selector de solicitud común sobre las pestañas;
   la recomendación se calcula una vez. Estrellas = promedio real de `satisfaccion_1a5`. Cupos marcados simulados.
   Pestaña **Mapa** (`src/vista_mapa.py`, pydeck): coordenadas de referencia `config/ciudades.yaml` (aprox., sin
   verificar), ruta en línea recta rotulada, etiquetas sin tildes (limitación de deck.gl). La app publica
   `static/contrato/solicitud_activa.json` (fuera de git). Error de carga → mensaje, nunca datos de reemplazo.

## Mundo 3D (argo-vr)
- Escena (`src/world.js`): puerto (4 terminales, grúas, 3 barcos), 28 camiones en 14 corredores, centro de operaciones,
  12 depósitos de proveedores, centro de análisis, patio y aeropuerto ilustrativos, ciudades.
- Interfaz (`src/main.js`): planificador, 13 casos, perfiles, comparador, seguimiento, modo 2D (`?modo=2d`).
- Motor PROPIO en JS (`src/engine.js`) — **distinto al de Python**; cuando se conecte, debe dejar de decidir.
- Datos: base **v2** ficticia (`data/base_simulada_transporte_v2.xlsx`, generador `tools/generar_base_v2.py`,
  exportación `tools/exportar_datos.py` → `public/data/demo_v2.json`): 15.974 servicios, 12 proveedores `SYN_`,
  14 corredores, 6 vehículos, flota, tarifas, disponibilidad, homologación, IMO, 13 casos de prueba.
  OJO: el Excel tiene SYN_P01 al 41,9 % (versión corregida); el generador quedó con los valores originales (59 %).
- AR/VR (Quest 3): maqueta a 0,5 m bajo los ojos y 0,9 m al frente; botón de agarre = recolocar; láser en controles;
  nombres 3D; gatillo en puerto→ciudad = recomendar; gatillo en depósito = ficha; botones de prioridad; panel flotante.
- `src/contrato.js`: adaptador del contrato de Python (validación, sin datos de reemplazo). **Aún no conectado a world.js.**
- Conexión gafas: solo HTTPS por wifi (Vite + certificado autofirmado, `host: true`) + WebXR. La IP cambia con la red.

## Pendientes (en orden sugerido)
1. Hacer push del commit y abrir PR hacia main.
2. Versionar `argo-vr` (no está en git).
3. Decidir con el equipo la base única (v1 del repo vs v2 del mundo 3D). Recomendación: v1.
4. Conectar el mundo 3D al contrato (sin cambiar aún la red de las gafas sin acordarlo).
5. Registrar la decisión final del operador (trazabilidad; no existe).
6. Mapa: carreteras reales, coordenadas verificadas (DANE/IGAC), ubicación de proveedores (no existen en la base).
7. Pulir lo visual de cada vista.
- Limitaciones conocidas: botón "Take Photo" en inglés (Streamlit no lo permite cambiar); cuenta de Meta nueva puede
  bloquearse; la IP de las gafas cambia.

## Forma de trabajar que pidió el equipo
- Español; no inventar datos (marcar simulados/no disponibles); no cambiar lógica de negocio sin aprobación;
  verificar con pruebas y en el navegador; explicar en pasos simples (la usuaria no es experta en consola).
