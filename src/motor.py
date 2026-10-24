"""Puente con el motor de recomendación: Modelos 1 y 2 de sistema_proveedores/.

Los módulos del motor se importan entre sí por nombre (p. ej. `import configuracion`)
y modelo2.pkl guarda sus clases con esos nombres, así que la carpeta del motor se
agrega a sys.path una sola vez, aquí. El resto de src/ importa el motor desde este módulo.
"""

import sys
from pathlib import Path

DIR_MOTOR = Path(__file__).resolve().parent.parent / "sistema_proveedores"
if str(DIR_MOTOR) not in sys.path:
    sys.path.insert(0, str(DIR_MOTOR))

import asignacion_lote  # noqa: E402
import configuracion  # noqa: E402
import modelo2_recomendador  # noqa: E402
from modelo2_recomendador import Recomendador  # noqa: E402

__all__ = ["DIR_MOTOR", "Recomendador", "asignacion_lote", "configuracion", "modelo2_recomendador"]
