# CLAUDE.md

## Objetivo
MVP en Python que recomienda qué proveedor de transporte terrestre de contenedores debe
atender cada solicitud. Usuarios: equipo de operaciones de la naviera.

## Flujo
1. **Cargar solicitud** (origen, destino, tipo de contenedor, fecha, etc.).
2. **Filtrar**: descartar los proveedores que no cumplen las restricciones de la solicitud.
3. **Puntuar** a los elegibles con pesos configurables por perfil (YAML en `config/`).
4. **Ranking top 3** y dashboard simple en Streamlit.

## Estructura
- `config/`: pesos por perfil y demás parámetros (YAML).
- `data/`: datos de entrada (CSV de proveedores y solicitudes).
- `src/`: lógica de negocio y de acceso.
- `tests/`: pruebas con pytest.
- `app.py`: dashboard Streamlit (solo presentación; delega en `src/`).

## Convenciones
- Código, nombres de variables/funciones y comentarios **en español**.
- Funciones pequeñas y puras; la E/S (lectura de archivos, Streamlit) va separada de la lógica.
- **Toda regla de negocio debe tener al menos una prueba** en `tests/`.
- Fuera del alcance del MVP: **cuotas contractuales** y **machine learning en la recomendación**
  (filtro, scoring y ranking son reglas explícitas). El acceso usa modelos faciales
  preentrenados de OpenCV y MediaPipe; no se entrena ningún modelo.

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
python -m pytest                              # correr pruebas
python -m streamlit run app.py                # correr el dashboard
```
