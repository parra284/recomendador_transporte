# CLAUDE.md

## Objetivo
MVP en Python que recomienda qué proveedor de transporte terrestre debe atender cada
solicitud. Usuarios: equipo de operaciones de la naviera.

## Flujo (input → transformación → output)
1. **Input**: la base de datos `data/base_simulada_mensajeria.xlsx` (hoja `Envios`) es la única
   fuente de verdad. Las solicitudes son CSV en `data/solicitudes*.csv`, con las mismas columnas
   de la base, o códigos de envíos históricos (`S-000001`…). Rutas en `config/fuente_datos.yaml`.
2. **Transformación**: los Modelos 1 y 2 de `sistema_proveedores/`, entrenados con la base.
   - Filtros duros: catálogo derivado del historial (contenedor, ciudades, peso y velocidad por
     contenedor, velocidad-zona) y cupos de `salidas_m2/capacidad_semana.csv`.
   - Puntaje: precio y tiempo estimados frente al mercado + fiabilidad del Modelo 1, con los
     pesos por contenedor de `config/perfiles.yaml`.
3. **Output**: top 3 con desglose, avisos, excluidos y alternativas; vista general; reparto de
   un lote con cupos y tope de concentración; ranking de proveedores. Dashboard en Streamlit.

## Estructura
- `config/`: `fuente_datos.yaml` (rutas), `perfiles.yaml` (pesos y umbrales), `seguridad.yaml`.
- `data/`: base de datos y CSV de solicitudes.
- `sistema_proveedores/`: motor (Modelos 1 y 2), su configuración compartida (`configuracion.py`),
  validaciones y salidas (`salidas_m2/modelo2.pkl` + `fuente_modelo.json` con la huella).
- `src/`: capa de la app. `motor.py` (puente con el motor), `fuente_datos.py` (E/S),
  `solicitud.py` (validación), `recomendacion.py` (tablas para mostrar), `verificar_datos.py`.
- `tests/`: pruebas con pytest (incluye coherencia base ↔ modelo y el dashboard con AppTest).
- `app.py`: dashboard Streamlit (solo presentación; delega en `src/`).

## Convenciones
- Código, nombres de variables/funciones y comentarios **en español**.
- Funciones pequeñas y puras; la E/S (lectura de archivos, Streamlit) va separada de la lógica.
- **Toda regla de negocio debe tener al menos una prueba** en `tests/`.
- Pesos y umbrales en `config/perfiles.yaml`, nunca escritos en el código. Los parámetros de
  `entrenamiento` exigen reentrenar; los demás se aplican al recomendar.
- Catálogos (ciudades, categorías, contenedores) se derivan de la base, no se escriben a mano.
- El modelo guardado solo se usa si su huella coincide con la base, la configuración de
  entrenamiento, el código de los modelos y las versiones de scikit-learn, pandas y numpy;
  si no, se reentrena.
- La base es simulada: no permite sacar conclusiones sobre las empresas reales.
- Fuera del alcance del MVP: **cuotas contractuales** (el tope de concentración del lote es
  un aviso operativo, no una cuota).

## Acceso y seguridad
- Ingreso con reconocimiento facial (OpenCV YuNet + SFace, en el servidor) y PIN de respaldo.
- Vigilancia de presencia en el navegador (MediaPipe): sin rostro durante
  `segundos_ausencia` (config/seguridad.yaml) se bloquea el dashboard; solo el mismo
  usuario desbloquea (rostro o PIN).
- Reglas de sesión en `src/sesion.py` (puras, con pruebas); pantallas en `src/pantalla_acceso.py`.
- El rostro es dato sensible (Ley 1581 de 2012): se guarda solo la huella numérica, nunca
  fotos, en `seguridad/usuarios.json`. `seguridad/` y `modelos/` nunca van a git.
- Los usuarios los registra un administrador con `python -m src.registrar_usuario`.

## Comandos
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.descargar_modelos               # una vez: modelos faciales
python -m src.registrar_usuario --usuario <id> --nombre "<Nombre>"
python -m src.entrenar_modelos                # (re)entrena con la base si no está al día
python -m src.verificar_datos                 # coherencia base ↔ config ↔ solicitudes ↔ modelo
python -m pytest                              # correr pruebas
python -m streamlit run app.py                # correr el dashboard
```
