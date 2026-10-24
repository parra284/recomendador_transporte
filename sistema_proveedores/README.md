# Sistema de selección de proveedores (Modelo 1 + Modelo 2)

El operario escribe el código de una solicitud y el sistema devuelve un top 3 de proveedores, con el puntaje explicado factor por factor. La decisión final sigue siendo de la persona de operaciones.

Funciona con la base **con contenedores** (`data/base_simulada_mensajeria.xlsx` en la raíz del proyecto, con la columna `tipo_contenedor`). Las rutas (base, solicitudes y carpeta del modelo) están en `config/fuente_datos.yaml` y los pesos y umbrales en `config/perfiles.yaml`; los dos los lee `configuracion.py`, igual que el dashboard (`app.py`), así que todos usan los mismos datos. Los scripts se pueden correr desde esta carpeta o desde la raíz.

`salidas_m2/fuente_modelo.json` guarda la huella del modelo entrenado (base, parámetros de entrenamiento, código de los modelos y versiones de scikit-learn, pandas y numpy). Si algo de eso cambia, `modelo2_recomendador.py` y el dashboard reentrenan solos.

## Cómo correrlo

```bash
pip install -r requirements.txt   # pandas numpy scikit-learn openpyxl pyyaml pulp highspy
python modelo1_fiabilidad.py                        # Modelo 1: ranking y fiabilidad (escribe salidas_m1/)
python validar_modelo1.py                           # las cuatro pruebas del Modelo 1
python modelo2_recomendador.py --entrenar           # entrena el Modelo 2 (incluye el Modelo 1)
python verificar_catalogo.py                        # comprueba que el catálogo no contradiga el historial
python modelo2_recomendador.py --codigo T-002       # recomienda una solicitud
python modelo2_recomendador.py --demo               # recomienda las 9 solicitudes de prueba
python modelo2_recomendador.py --lote T-001,T-002,T-009   # reparte un lote respetando cupos y el 35 %
python pruebas_lote.py                              # 4 pruebas de la asignación por lotes
python validar_modelo2.py                           # validación del Modelo 2 (prueba retrospectiva y 5 pruebas más, ~1 min)
python valor_negocio.py                             # valor anual: semanas de prueba repartidas con cupos y tope, escenarios conservador y esperado
python comparar_modelos.py                          # logística, árboles y Modelo 1 sobre los mismos envíos de prueba
python exito_recomendacion.py                       # % de veces que la #1 es la mejor opción real (95,5 %)
```

El código puede ser una solicitud de prueba (`T-001` a `T-009`, en `data/solicitudes_prueba.csv`) o un envío histórico (`S-000001` en adelante); en ese caso también muestra qué proveedor se eligió en su momento y cómo le fue.

## Cómo decide el Modelo 2

1. **Filtros duros** (catálogo derivado del historial, por proveedor y contenedor): contenedor, cobertura de ciudades, peso máximo atendido en ese contenedor, velocidades ofrecidas con ese contenedor (al menos 5 envíos), combinaciones velocidad-zona posibles y cupos de la semana. Cada exclusión queda con su motivo y el conteo que la respalda.
2. **Estimaciones**: precio y tiempo con modelos entrenados con el historial; fiabilidad con el Modelo 1.
3. **Puntaje con escalas fijas**: precio y tiempo se comparan con lo que costaría o tardaría un proveedor promedio en ese mismo envío (igual al mercado = 50 puntos, 20 % mejor = 70); la fiabilidad es el puntaje 0-100 del Modelo 1.
4. **Pesos por perfil**: base por tipo de contenedor; la velocidad pedida y un plazo ajustado suben el peso del tiempo.
5. **Plazo pedido**: si la solicitud trae plazo, la tabla muestra la probabilidad de llegar dentro de él (columna *En plazo*, calculada con el error del modelo de tiempo y calibrada en abr-sep 2026). *A tiempo* es otra cosa: cumplir lo que promete el propio proveedor, y esa promesa puede ser más larga que el plazo pedido. Hay aviso cuando un proveedor del top promete más que el plazo o lo cumple menos del 70 % de las veces. El plazo no cambia el puntaje.

Cada recomendación muestra el desglose del puntaje (puntos × peso = aporte) de los tres primeros y de cada alternativa, y el motivo de cada exclusión.

Si nadie cumple, propone alternativas (otra velocidad o un proveedor sin cupo). Avisa empates técnicos, probabilidad baja de cumplir el plazo o promesas más largas que el plazo, concentración de envíos en un proveedor y poco historial.

## Asignación por lotes (`--lote`)

Cuando llegan varias solicitudes juntas, `asignar_lote(codigos)` (en `asignacion_lote.py`, también como `rec.asignar_lote(...)`) las reparte entre proveedores **maximizando la suma de puntajes del Modelo 2**. La lógica de puntaje no cambia: cada solicitud se puntúa igual que con `--codigo`, pero sin el filtro de cupos, porque en el lote los cupos son una restricción conjunta. Las restricciones son dos:

- **Cupos:** cada proveedor recibe, por contenedor, como mucho sus cupos disponibles de `salidas_m2/capacidad_semana.csv`. Si editas ese archivo, el lote usa los nuevos cupos.
- **Concentración:** ningún proveedor recibe más del 35 % del lote, es decir, la parte entera de 0,35 × n (17 de 50). Con 1 o 2 solicitudes eso es menos de un envío, así que la regla no se aplica y se avisa.

**Método:** programación entera con PuLP. Funciona con PuLP 2 (CBC incluido) y con PuLP 4 (`pip install pulp highspy` para el solver HiGHS). Si no hay solver, usa una heurística voraz por "arrepentimiento": en cada paso atiende la solicitud que más perdería si no recibe ya su mejor opción libre. Es más rápida, pero decide una a una y no deshace decisiones, así que no garantiza el óptimo. En el lote de 50 envíos sacó 46 puntos menos que el óptimo.

**Qué muestra:**
- Por solicitud: su primera opción, el proveedor asignado (y qué opción era para ella), los puntos perdidos y el motivo (sin cupos, cupos agotados en el lote o tope del 35 %).
- El puntaje total en cuatro escenarios: sin restricciones, solo cupos, solo tope y ambas.
- El reparto por proveedor antes y después, más el reparto histórico real si son envíos históricos.
- El uso de cupos y las comprobaciones de que nadie supera cupos ni tope.
- El detalle se guarda en `salidas_m2/asignacion_lote.csv`.

Ejemplo con 50 envíos históricos de la semana del 21 al 27 de sep-2026 (salida completa en `salidas_m2/lote_semana.txt`):

```bash
python modelo2_recomendador.py --lote S-030106,S-030110,S-030114,S-030162,S-030179,S-030182,S-030229,S-030231,S-030255,S-030350,S-030413,S-030463,S-030511,S-030512,S-030538,S-030548,S-030569,S-030585,S-030619,S-030635,S-030702,S-030721,S-030769,S-030812,S-030817,S-030853,S-030882,S-030891,S-030903,S-030937,S-030963,S-030975,S-030987,S-030997,S-031036,S-031041,S-031070,S-031119,S-031192,S-031211,S-031235,S-031242,S-031255,S-031257,S-031268,S-031326,S-031334,S-031365,S-031385,S-031386
```


## Archivos

| Archivo | Qué es |
|---|---|
| `modelo1_fiabilidad.py` | Modelo 1. Usa `tipo_contenedor` y `categoria_carga` automáticamente si la base las trae |
| `validar_modelo1.py` | Pruebas del Modelo 1 |
| `validar_modelo2.py` | Validación del Modelo 2: entrenado hasta 2026-03-31 y probado en abr-sep 2026, coherencia, sensibilidad, casos y recuperación de la hoja Supuestos |
| `comparar_modelos.py` | Modelo 1 frente a regresión logística, bosque aleatorio y gradient boosting, con intervalos de confianza |
| `exito_recomendacion.py` | Acierto de la recomendación contra los resultados reales de abr-sep 2026 |
| `valor_negocio.py` | Valor anual (puntualidad, flete, horas de operario) a partir de la validación; supuestos como argumentos |
| `VALIDACION_MODELO2.md` | Resultados, limitaciones y frases para la presentación |
| `salidas_validacion_m2/` | Tablas de la validación (`resumen.txt`, `por_envio.csv`, `sensibilidad_pesos.csv`, ...) |
| `modelo2_recomendador.py` | Modelo 2: catálogo, capacidad, cotizador y recomendador |
| `verificar_catalogo.py` | 10 comprobaciones: ninguna regla del catálogo contradice el historial |
| `MODELO_DATOS.md` | Revisión de la base, catálogo, capacidad, diagrama del modelo de datos y supuestos |
| `modelo_datos.png` / `.svg` | Diagrama entidad-relación |
| `asignacion_lote.py` | Asignación por lotes: programación entera (PuLP) o heurística voraz |
| `pruebas_lote.py` | Pruebas del lote: mejor proveedor sin cupos, competencia por un cupo, lote de 50 y heurística |
| `configuracion.py` | Rutas y pesos (de `config/`) y huella del modelo entrenado |
| `../data/solicitudes_prueba.csv` | 9 solicitudes de prueba con requisitos distintos |
| `salidas_m1/` | Ranking, contextos, serie mensual y validación del Modelo 1 |
| `salidas_m2/catalogo_proveedores.csv` | Qué puede atender cada proveedor por contenedor, con conteos (derivado del historial) |
| `salidas_m2/verificacion_catalogo.txt` | Resultado de `verificar_catalogo.py` |
| `salidas_m2/capacidad_semana.csv` | Cupos de la semana por proveedor y contenedor (**simulados**) |
| `salidas_m2/comparacion_modelos_precio_tiempo.csv` | Ridge frente a gradient boosting para precio y tiempo |
| `salidas_m2/demo.txt` | Resultado de las 9 solicitudes de prueba |
| `salidas_m2/lote_semana.txt` / `asignacion_lote.csv` | Asignación del lote de 50 envíos de ejemplo |
| `salidas_m2/modelo2.pkl` | Modelo 2 entrenado, para el prototipo |

## Uso desde Streamlit u otro script

```python
from modelo2_recomendador import Recomendador

rec = Recomendador.cargar("salidas_m2/modelo2.pkl")
resultado = rec.recomendar(rec.solicitud("T-002"))
resultado["ranking"]        # tabla ordenada con precio, tiempo, fiabilidad, puntos y aportes
resultado["explicacion"]    # por qué el primero y no el segundo
resultado["avisos"], resultado["excluidos"], resultado["alternativas"]

lote = rec.asignar_lote(["T-001", "T-002", "T-009"])
lote["detalle"]           # por solicitud: primera opción, asignado, pérdida y motivo
lote["resumen"]           # puntaje total por escenario
lote["reparto"], lote["uso_cupos"], lote["comprobaciones"]
```
