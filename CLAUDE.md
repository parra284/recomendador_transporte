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
- `src/`: lógica de negocio.
- `tests/`: pruebas con pytest.
- `app.py`: dashboard Streamlit (solo presentación; delega en `src/`).

## Convenciones
- Código, nombres de variables/funciones y comentarios **en español**.
- Funciones pequeñas y puras; la E/S (lectura de archivos, Streamlit) va separada de la lógica.
- **Toda regla de negocio debe tener al menos una prueba** en `tests/`.
- Fuera del alcance del MVP: **cuotas contractuales** y **machine learning**.

## Comandos
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest                # correr pruebas
python -m streamlit run app.py    # correr el dashboard
```
