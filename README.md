# Recomendador de transportistas terrestres

MVP que recomienda qué proveedor de transporte terrestre debe atender cada solicitud, para el
equipo de operaciones de la naviera.

Flujo: **base de datos** (`data/base_simulada_mensajeria.xlsx`) → **Modelos 1 y 2**
(`sistema_proveedores/`: filtros del catálogo, precio y tiempo frente al mercado, fiabilidad
y pesos por contenedor) → **dashboard** con el top 3, su desglose y el reparto de un lote.

> La base es simulada (Monte Carlo a partir de anclas reales). Sirve para probar el método;
> no permite sacar conclusiones sobre las empresas reales.

## Instalación

Requiere Python 3.10 o superior.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Datos y modelos

| Qué | Dónde | Notas |
|---|---|---|
| Base de envíos | `data/base_simulada_mensajeria.xlsx` (hoja `Envios`) | Única fuente de verdad; ruta en `config/fuente_datos.yaml` |
| Solicitudes | `data/solicitudes*.csv` | Mismas columnas que la base (ver abajo) |
| Pesos y umbrales | `config/perfiles.yaml` | Se aplican sin reentrenar, salvo la sección `entrenamiento` |
| Modelo entrenado | `sistema_proveedores/salidas_m2/modelo2.pkl` | `fuente_modelo.json` guarda de qué base salió |
| Cupos de la semana | `sistema_proveedores/salidas_m2/capacidad_semana.csv` | Simulados; si se editan, la app los usa |

El modelo guardado solo se usa si corresponde a la base, los parámetros de entrenamiento, el
código de los modelos y las versiones de scikit-learn, pandas y numpy actuales. Si algo cambió, el dashboard
reentrena solo (unos 20 a 40 segundos) o se puede hacer a mano:

```powershell
python -m src.entrenar_modelos            # solo si hace falta
python -m src.entrenar_modelos --forzar   # siempre
```

### Columnas de un archivo de solicitudes

`id_envio, fecha_orden, origen, destino, categoria_carga, peso_por_bulto_kg, bultos_unidades,
valor_declarado_cop, fragil, seguro, nivel_velocidad, plazo_h, descripcion`

- `origen`, `destino` y `categoria_carga` deben existir en la base; la categoría define el
  contenedor (Dry, Reefer, Open Top o Flat Rack).
- `fecha_orden` en formato `AAAA-MM-DD`; `fragil` y `seguro` en 1/0; `nivel_velocidad` en
  `std`, `prio`, `exp` o `same`; `plazo_h` opcional (horas).
- El peso total no puede superar lo máximo que algún proveedor ha movido en ese contenedor.

Las filas con errores no detienen la carga: el dashboard las muestra con su motivo
(`data/solicitudes_invalidas.csv` trae un ejemplo de cada error).

## Acceso (reconocimiento facial + PIN)

1. Descargar los modelos faciales (una sola vez, ~40 MB):

   ```powershell
   python -m src.descargar_modelos
   ```

2. Registrar a cada operario autorizado (lo hace un administrador en el equipo de la app).
   Antes, la persona debe autorizar el tratamiento de su dato biométrico (Ley 1581 de 2012).
   Se abre la cámara: ESPACIO captura, ESC cancela. Luego se pide el PIN de respaldo.

   ```powershell
   python -m src.registrar_usuario --usuario jperez --nombre "Juana Pérez"
   python -m src.registrar_usuario --eliminar jperez     # borra su huella
   ```

Al entrar, el usuario se toma una foto (o usa su PIN). Mientras usa el dashboard, la cámara
aparece en la esquina inferior derecha; si no se detecta su rostro durante 10 segundos
(configurable en `config/seguridad.yaml`), la pantalla se bloquea hasta que el mismo
usuario se verifique de nuevo.

Notas:
- El navegador pide permiso de cámara. Solo funciona en `localhost` o con HTTPS.
- La vigilancia descarga MediaPipe desde internet la primera vez.
- Solo se guarda la huella numérica del rostro, nunca fotos, en `seguridad/usuarios.json`
  (excluido de git, igual que `modelos/`).

## Pruebas y verificación

```powershell
python -m pytest                 # todas las pruebas (incluye el dashboard con AppTest)
python -m src.verificar_datos    # coherencia base ↔ configuración ↔ solicitudes ↔ modelo
```

Validaciones propias de los modelos (ver `sistema_proveedores/README.md`):

```powershell
python sistema_proveedores/verificar_catalogo.py   # el catálogo no contradice el historial
python sistema_proveedores/validar_modelo2.py      # prueba retrospectiva (~1 min)
```

## Abrir la app

```powershell
python -m streamlit run app.py
```

Se abre en el navegador (por defecto http://localhost:8501). En la barra lateral se ve la base
con la que se entrenaron los modelos y se elige el archivo de solicitudes. Pestañas:

- **Recomendación**: una solicitud del archivo o un envío histórico de la base. Muestra los
  pesos aplicados, el top 3 (precio y tiempo frente al mercado, fiabilidad, % a tiempo y, si hay
  plazo, % en plazo), la explicación, el aporte de cada factor, los avisos, los excluidos con su
  motivo y, si nadie cumple, las alternativas. En un envío histórico, además, quién lo hizo y
  cómo le fue.
- **Todas las solicitudes**: el proveedor recomendado para cada una.
- **Reparto del lote**: asigna todas las solicitudes sin superar cupos ni el 35 % por proveedor.
- **Proveedores**: fiabilidad del Modelo 1, qué atiende cada proveedor y cupos de la semana.

## Estructura

| Ruta | Contenido |
|---|---|
| `config/fuente_datos.yaml` | Rutas de la base, las solicitudes y el modelo |
| `config/perfiles.yaml` | Pesos por contenedor, ajustes por velocidad y plazo, umbrales de avisos y de entrenamiento |
| `data/` | Base de datos y solicitudes |
| `sistema_proveedores/` | Modelos 1 y 2, validaciones y salidas |
| `src/motor.py` | Puente con el motor |
| `src/fuente_datos.py` | Lectura de la base, el modelo y los archivos |
| `src/solicitud.py` | Modelo y validación de solicitudes (catálogos derivados de la base) |
| `src/recomendacion.py` | Resultado del Modelo 2 en tablas para el dashboard |
| `src/verificar_datos.py` | Verificación de coherencia |
| `src/entrenar_modelos.py` | Reentrenamiento |
| `app.py` | Dashboard Streamlit |

Ver [CLAUDE.md](CLAUDE.md) para las convenciones del proyecto.
