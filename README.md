# Recomendador de transportistas terrestres

MVP que recomienda qué proveedor de transporte terrestre de contenedores debe atender
cada solicitud, para el equipo de operaciones de la naviera.

Flujo: cargar solicitud → descartar proveedores que no cumplen restricciones →
puntuar a los elegibles con pesos por perfil → top 3 y dashboard.

## Instalación

Requiere Python 3.10 o superior.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Pruebas

```powershell
python -m pytest
```

Para revisar que los CSV de `data/` tienen las columnas y códigos correctos:

```powershell
python -m src.verificar_datos
```

## Abrir la app

```powershell
python -m streamlit run app.py
```

Se abre en el navegador (por defecto http://localhost:8501). En la barra lateral se elige
el archivo de solicitudes (`data/solicitudes_*.csv`) y arriba la solicitud a revisar.
La app muestra el perfil aplicado, el top 3 con su explicación, el aporte de cada variable,
los proveedores descartados con sus motivos y una tabla con todas las solicitudes.

## Estructura

| Ruta | Contenido |
|---|---|
| `config/catalogos.yaml` | Valores válidos (orígenes, destinos, contenedores, pesos máximos…) |
| `config/perfiles.yaml` | Pesos por perfil y parámetros de puntuación |
| `data/` | CSV ficticios de solicitudes, proveedores, rutas, tarifas, capacidad, historial y etiquetas |
| `src/solicitud.py` | Modelo y validación de solicitudes |
| `src/restricciones.py` | Reglas que descartan proveedores |
| `src/scoring.py` | Puntuación de elegibles |
| `src/ranking.py` | Top 3, desempates y explicaciones |
| `app.py` | Dashboard Streamlit |

Para cambiar la importancia de precio, tiempo, confiabilidad o etiquetas basta con editar
`config/perfiles.yaml` (los pesos de cada perfil deben sumar 1).

Ver [CLAUDE.md](CLAUDE.md) para las convenciones del proyecto.
