"""Entrena los Modelos 1 y 2 con la base de datos y los guarda con su huella.

Uso:
    python -m src.entrenar_modelos            # solo si el modelo guardado no está al día
    python -m src.entrenar_modelos --forzar   # siempre

Hace falta después de cambiar la base, los parámetros de `entrenamiento` en
config/perfiles.yaml, el código de los modelos o las versiones de scikit-learn, pandas o numpy. El
dashboard también lo detecta y reentrena solo, pero tarda en abrir la primera vez.
"""

import argparse
import sys

from src.fuente_datos import entrenar_y_guardar, info_modelo
from src.motor import configuracion


def main(argv=None):
    parser = argparse.ArgumentParser(description="Entrena los modelos con la base de datos.")
    parser.add_argument("--forzar", action="store_true", help="reentrena aunque el modelo esté al día")
    args = parser.parse_args(argv)

    if configuracion.modelo_al_dia() and not args.forzar:
        print("El modelo ya corresponde a la base, la configuración y el código actuales. "
              "Use --forzar para reentrenar de todos modos.")
    else:
        print(f"Entrenando con {configuracion.BASE_DATOS.relative_to(configuracion.RAIZ)}...")
        entrenar_y_guardar()
    info = info_modelo()
    envios = f"{info['envios']:,}".replace(",", ".")
    librerias = ", ".join(f"{k} {v}" for k, v in info["librerias"].items())
    print(f"Modelo: {configuracion.DIR_M2.relative_to(configuracion.RAIZ)} · base {info['base_datos']} · "
          f"{envios} envíos ({info['periodo'][0]} a {info['periodo'][1]}) · "
          f"entrenado el {info['entrenado_en']} con {librerias}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
