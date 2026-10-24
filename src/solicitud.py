"""Modelo de solicitud de transporte, validaciones y carga desde CSV."""

import csv
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ValidationError, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

RUTA_CATALOGOS = Path(__file__).resolve().parent.parent / "config" / "catalogos.yaml"
PRIORIDAD_POR_DEFECTO = "normal"


@lru_cache(maxsize=None)
def cargar_catalogos(ruta=RUTA_CATALOGOS):
    with open(ruta, encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


def _catalogos(info: ValidationInfo):
    """Catálogos del contexto de validación o, si no se pasaron, los del proyecto."""
    if info.context and "catalogos" in info.context:
        return info.context["catalogos"]
    return cargar_catalogos()


def _error(mensaje):
    return PydanticCustomError("regla_negocio", mensaje)


def _validar_en_catalogo(valor, lista, descripcion):
    if valor not in lista:
        opciones = ", ".join(str(x) for x in lista)
        raise _error(f"{descripcion} '{valor}' no existe. Valores permitidos: {opciones}.")
    return valor


class Solicitud(BaseModel):
    # El orden de los campos importa: las reglas cruzadas usan campos ya validados.
    id_solicitud: str
    origen: str
    destino: str
    fecha_cita: datetime
    tipo_contenedor: str
    peso_bruto_t: float
    imo: bool
    clase_imo: Optional[float] = None
    refrigerada: bool
    temperatura_c: Optional[float] = None
    extradimensionada: bool
    valor_declarado_usd: float
    modalidad_aduanera: Optional[str] = None
    prioridad: str = PRIORIDAD_POR_DEFECTO
    observaciones: Optional[str] = None

    @field_validator("origen")
    @classmethod
    def origen_en_catalogo(cls, valor, info):
        return _validar_en_catalogo(valor, _catalogos(info)["origenes"], "El origen")

    @field_validator("destino")
    @classmethod
    def destino_en_catalogo(cls, valor, info):
        return _validar_en_catalogo(valor, _catalogos(info)["destinos"], "El destino")

    @field_validator("tipo_contenedor")
    @classmethod
    def tipo_en_catalogo(cls, valor, info):
        return _validar_en_catalogo(valor, _catalogos(info)["tipos_contenedor"], "El tipo de contenedor")

    @field_validator("modalidad_aduanera")
    @classmethod
    def modalidad_en_catalogo(cls, valor, info):
        if valor is None:
            return None
        return _validar_en_catalogo(valor, _catalogos(info)["modalidades_aduaneras"], "La modalidad aduanera")

    @field_validator("prioridad", mode="before")
    @classmethod
    def prioridad_vacia_es_normal(cls, valor):
        return PRIORIDAD_POR_DEFECTO if valor in (None, "") else valor

    @field_validator("prioridad")
    @classmethod
    def prioridad_en_catalogo(cls, valor, info):
        return _validar_en_catalogo(valor, _catalogos(info)["prioridades"], "La prioridad")

    @field_validator("fecha_cita", mode="before")
    @classmethod
    def fecha_en_formato_iso(cls, valor, info):
        if isinstance(valor, datetime):
            return valor
        formato = _catalogos(info)["formato_fecha_cita"]
        try:
            return datetime.strptime(str(valor), formato)
        except ValueError:
            raise _error(f"La fecha de cita '{valor}' no es válida. Use el formato AAAA-MM-DDTHH:MM, "
                         "por ejemplo 2026-11-04T06:00.")

    @field_validator("peso_bruto_t")
    @classmethod
    def peso_dentro_del_maximo(cls, valor, info):
        if valor <= 0:
            raise _error("El peso bruto debe ser mayor que 0 toneladas.")
        tipo = info.data.get("tipo_contenedor")
        maximo = _catalogos(info)["peso_max_t"].get(tipo)
        if maximo is not None and valor > maximo:
            raise _error(f"El peso bruto ({valor} t) supera el máximo permitido para un "
                         f"contenedor {tipo} ({maximo} t).")
        return valor

    @field_validator("clase_imo")
    @classmethod
    def clase_obligatoria_si_imo(cls, valor, info):
        if not info.data.get("imo"):
            return valor
        if valor is None:
            raise _error("La carga es IMO (peligrosa): debe indicar la clase IMO (de 1 a 9).")
        if int(valor) not in _catalogos(info)["clases_imo"]:
            raise _error(f"La clase IMO {valor:g} no es válida: debe estar entre 1 y 9.")
        return valor

    @field_validator("refrigerada")
    @classmethod
    def refrigerada_requiere_contenedor_rf(cls, valor, info):
        tipo = info.data.get("tipo_contenedor")
        if valor and tipo and not tipo.endswith("RF"):
            raise _error(f"La carga refrigerada requiere contenedor refrigerado (20RF o 40RF), "
                         f"pero se indicó {tipo}.")
        return valor

    @field_validator("temperatura_c")
    @classmethod
    def temperatura_obligatoria_si_refrigerada(cls, valor, info):
        if info.data.get("refrigerada") and valor is None:
            raise _error("La carga es refrigerada: debe indicar la temperatura en °C.")
        return valor

    @field_validator("extradimensionada")
    @classmethod
    def extradimensionada_requiere_fr_u_ot(cls, valor, info):
        tipo = info.data.get("tipo_contenedor")
        if valor and tipo and not tipo.endswith(("FR", "OT")):
            raise _error(f"La carga extradimensionada requiere contenedor flat rack u open top "
                         f"(40FR o 40OT), pero se indicó {tipo}.")
        return valor

    @field_validator("valor_declarado_usd")
    @classmethod
    def valor_positivo(cls, valor):
        if valor <= 0:
            raise _error("El valor declarado debe ser mayor que 0 USD.")
        return valor


@dataclass(frozen=True)
class ErrorSolicitud:
    fila: int
    id_solicitud: str
    campo: str
    mensaje: str


# Mensajes en español para los errores de tipo que genera pydantic.
MENSAJES_POR_TIPO = {
    "bool_parsing": "debe ser true o false",
    "float_parsing": "debe ser un número (use punto como separador decimal)",
    "missing": "es obligatorio y no viene en el archivo",
}


def traducir_error(error):
    """Convierte un error de pydantic en un mensaje entendible para un operario."""
    campo = str(error["loc"][0]) if error["loc"] else "solicitud"
    if error["type"] == "regla_negocio":
        return campo, error["msg"]
    if error.get("input") is None:
        return campo, f"El campo {campo} es obligatorio y está vacío."
    detalle = MENSAJES_POR_TIPO.get(error["type"], "tiene un valor no válido")
    return campo, f"El campo {campo} {detalle}; se recibió '{error['input']}'."


def limpiar_fila(fila):
    """Celdas vacías del CSV pasan a None para que las reglas de opcionales funcionen."""
    return {campo: (valor.strip() or None) if isinstance(valor, str) else valor
            for campo, valor in fila.items()}


def validar_fila(fila, num_fila, catalogos):
    """Devuelve (Solicitud, []) si la fila es válida o (None, errores) si no."""
    datos = limpiar_fila(fila)
    try:
        return Solicitud.model_validate(datos, context={"catalogos": catalogos}), []
    except ValidationError as exc:
        id_solicitud = datos.get("id_solicitud") or ""
        errores = [ErrorSolicitud(num_fila, id_solicitud, *traducir_error(e)) for e in exc.errors()]
        return None, errores


def cargar_solicitudes(ruta_csv, catalogos=None):
    """Lee un CSV de solicitudes y devuelve (solicitudes_validas, errores).

    La fila se numera como en Excel: la 1 es el encabezado, la 2 es la primera solicitud.
    """
    catalogos = catalogos or cargar_catalogos()
    validas, errores = [], []
    with open(ruta_csv, encoding="utf-8", newline="") as archivo:
        for num_fila, fila in enumerate(csv.DictReader(archivo), start=2):
            solicitud, errores_fila = validar_fila(fila, num_fila, catalogos)
            if solicitud:
                validas.append(solicitud)
            errores += errores_fila
    return validas, errores
