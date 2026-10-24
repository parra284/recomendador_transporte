"""Solicitud de transporte: modelo, validaciones y carga desde CSV.

Las columnas son las mismas de la base de datos (hoja Envios) y de las solicitudes
que entiende el Modelo 2. Los valores válidos (ciudades, categorías de carga y su
contenedor, peso máximo por contenedor) se derivan de la propia base, para que una
solicitud nunca use un código que los modelos no conocen.
"""

import csv
from dataclasses import dataclass
from datetime import date
from typing import Optional

from pydantic import BaseModel, ValidationError, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from src.motor import configuracion

COLUMNAS = [
    "id_envio", "fecha_orden", "origen", "destino", "categoria_carga", "peso_por_bulto_kg",
    "bultos_unidades", "valor_declarado_cop", "fragil", "seguro", "nivel_velocidad", "plazo_h",
    "descripcion",
]
NOMBRE_VELOCIDAD = {"same": "mismo día", "exp": "exprés", "prio": "prioritaria", "std": "estándar"}
VERDADERO = {"1", "true", "si", "sí"}
FALSO = {"0", "false", "no"}


# --- Catálogos derivados de la base ---

@dataclass(frozen=True)
class Catalogos:
    ciudades: tuple                 # ciudades con historial
    rutas: frozenset                # {(origen, destino)} con historial
    contenedor_de_categoria: dict   # categoría de carga -> tipo de contenedor
    velocidades: tuple              # niveles de velocidad que entiende el Modelo 2
    peso_max_kg: dict               # contenedor -> máximo movido por algún proveedor que lo ofrece


def catalogos_desde_envios(envios, min_servicios):
    """Catálogos a partir del historial, con las mismas reglas del catálogo del Modelo 2."""
    servicios = envios.groupby(["proveedor", "tipo_contenedor"]).size()
    ofrecidos = set(servicios[servicios >= min_servicios].index)
    de_ofrecidos = envios[[par in ofrecidos for par in zip(envios.proveedor, envios.tipo_contenedor)]]
    return Catalogos(
        ciudades=tuple(sorted(set(envios.origen) | set(envios.destino))),
        rutas=frozenset(zip(envios.origen, envios.destino)),
        contenedor_de_categoria=envios.groupby("categoria_carga")["tipo_contenedor"]
        .agg(lambda s: s.mode().iat[0]).to_dict(),
        velocidades=tuple(configuracion.VELOCIDADES),
        peso_max_kg=de_ofrecidos.groupby("tipo_contenedor")["peso_total_kg"].max().to_dict(),
    )


# --- Modelo ---

def _catalogos(info: ValidationInfo):
    return info.context["catalogos"]


def _error(mensaje):
    return PydanticCustomError("regla_negocio", mensaje)


def _en_catalogo(valor, opciones, descripcion):
    if valor not in opciones:
        raise _error(f"{descripcion} '{valor}' no existe en la base. Valores permitidos: {', '.join(opciones)}.")
    return valor


def _miles(numero):
    return f"{numero:,.0f}".replace(",", ".")


class Solicitud(BaseModel):
    # El orden importa: las reglas cruzadas usan campos ya validados (info.data).
    id_envio: str
    fecha_orden: date
    origen: str
    destino: str
    categoria_carga: str
    bultos_unidades: int
    peso_por_bulto_kg: float
    valor_declarado_cop: float
    fragil: bool
    seguro: bool
    nivel_velocidad: str
    plazo_h: Optional[float] = None
    descripcion: Optional[str] = None

    @field_validator("fecha_orden", mode="before")
    @classmethod
    def fecha_iso(cls, valor):
        if isinstance(valor, date):
            return valor
        try:
            return date.fromisoformat(str(valor))
        except ValueError:
            raise _error(f"La fecha '{valor}' no es válida. Use el formato AAAA-MM-DD, por ejemplo 2026-10-26.")

    @field_validator("origen")
    @classmethod
    def origen_en_base(cls, valor, info):
        return _en_catalogo(valor, _catalogos(info).ciudades, "La ciudad de origen")

    @field_validator("destino")
    @classmethod
    def destino_en_base(cls, valor, info):
        catalogos = _catalogos(info)
        _en_catalogo(valor, catalogos.ciudades, "La ciudad de destino")
        origen = info.data.get("origen")
        if origen and (origen, valor) not in catalogos.rutas:
            raise _error(f"La ruta {origen} → {valor} no tiene historial en la base.")
        return valor

    @field_validator("categoria_carga")
    @classmethod
    def categoria_en_base(cls, valor, info):
        return _en_catalogo(valor, sorted(_catalogos(info).contenedor_de_categoria), "La categoría de carga")

    @field_validator("bultos_unidades")
    @classmethod
    def bultos_positivos(cls, valor):
        if valor < 1:
            raise _error("El número de bultos debe ser al menos 1.")
        return valor

    @field_validator("peso_por_bulto_kg")
    @classmethod
    def peso_dentro_del_mercado(cls, valor, info):
        if valor <= 0:
            raise _error("El peso por bulto debe ser mayor que 0 kg.")
        catalogos = _catalogos(info)
        contenedor = catalogos.contenedor_de_categoria.get(info.data.get("categoria_carga"))
        bultos = info.data.get("bultos_unidades")
        maximo = catalogos.peso_max_kg.get(contenedor)
        if bultos and maximo is not None and valor * bultos > maximo:
            raise _error(f"El peso total ({bultos} × {valor:g} kg = {_miles(valor * bultos)} kg) supera lo máximo "
                         f"que ha movido cualquier proveedor en {contenedor} ({_miles(maximo)} kg).")
        return valor

    @field_validator("valor_declarado_cop")
    @classmethod
    def valor_positivo(cls, valor):
        if valor <= 0:
            raise _error("El valor declarado debe ser mayor que 0 COP.")
        return valor

    @field_validator("fragil", "seguro", mode="before")
    @classmethod
    def si_o_no(cls, valor, info):
        texto = str(valor).strip().lower()
        if texto in VERDADERO:
            return True
        if texto in FALSO:
            return False
        raise _error(f"El campo {info.field_name} debe ser 1 o 0 (sí o no); se recibió '{valor}'.")

    @field_validator("nivel_velocidad")
    @classmethod
    def velocidad_valida(cls, valor, info):
        opciones = _catalogos(info).velocidades
        if valor not in opciones:
            texto = ", ".join(f"{v} ({NOMBRE_VELOCIDAD[v]})" for v in opciones)
            raise _error(f"La velocidad '{valor}' no existe. Valores permitidos: {texto}.")
        return valor

    @field_validator("plazo_h")
    @classmethod
    def plazo_positivo(cls, valor):
        if valor is not None and valor <= 0:
            raise _error("El plazo debe ser mayor que 0 horas (o quedar vacío si no hay plazo).")
        return valor

    def como_dict(self):
        """La solicitud en el formato que recibe el Modelo 2."""
        return {
            "id_envio": self.id_envio,
            "fecha_orden": self.fecha_orden.isoformat(),
            "origen": self.origen,
            "destino": self.destino,
            "categoria_carga": self.categoria_carga,
            "peso_por_bulto_kg": self.peso_por_bulto_kg,
            "bultos_unidades": self.bultos_unidades,
            "valor_declarado_cop": self.valor_declarado_cop,
            "fragil": int(self.fragil),
            "seguro": int(self.seguro),
            "nivel_velocidad": self.nivel_velocidad,
            "plazo_h": self.plazo_h,
            "descripcion": self.descripcion,
        }


# --- Carga desde CSV ---

@dataclass(frozen=True)
class ErrorSolicitud:
    fila: int
    id_envio: str
    campo: str
    mensaje: str


# Mensajes en español para los errores de tipo que genera pydantic.
MENSAJES_POR_TIPO = {
    "float_parsing": "debe ser un número (use punto como separador decimal)",
    "int_parsing": "debe ser un número entero",
    "int_from_float": "debe ser un número entero",
    "missing": "es obligatorio y no viene en el archivo",
}


def traducir_error(error):
    """Convierte un error de pydantic en (campo, mensaje) entendible para un operario."""
    campo = str(error["loc"][0]) if error["loc"] else "solicitud"
    if error["type"] == "regla_negocio":
        return campo, error["msg"]
    if error.get("input") is None:
        return campo, f"El campo {campo} es obligatorio y está vacío."
    detalle = MENSAJES_POR_TIPO.get(error["type"], "tiene un valor no válido")
    return campo, f"El campo {campo} {detalle}; se recibió '{error['input']}'."


def limpiar_fila(fila):
    """Celdas vacías pasan a None para que las reglas de campos opcionales funcionen."""
    return {campo: (valor.strip() or None) if isinstance(valor, str) else valor
            for campo, valor in fila.items() if campo is not None}


def validar_fila(fila, num_fila, catalogos):
    """(Solicitud, []) si la fila es válida o (None, errores) si no."""
    datos = limpiar_fila(fila)
    try:
        return Solicitud.model_validate(datos, context={"catalogos": catalogos}), []
    except ValidationError as exc:
        id_envio = datos.get("id_envio") or ""
        return None, [ErrorSolicitud(num_fila, id_envio, *traducir_error(e)) for e in exc.errors()]


def validar_filas(filas, catalogos):
    """Valida filas (dicts) numeradas como en Excel: la 1 es el encabezado. Devuelve (válidas, errores)."""
    validas, errores, vistos = [], [], {}
    for num_fila, fila in enumerate(filas, start=2):
        solicitud, errores_fila = validar_fila(fila, num_fila, catalogos)
        if solicitud and solicitud.id_envio in vistos:
            errores_fila = [ErrorSolicitud(num_fila, solicitud.id_envio, "id_envio",
                                           f"El código {solicitud.id_envio} ya se usó en la fila "
                                           f"{vistos[solicitud.id_envio]}.")]
            solicitud = None
        if solicitud:
            vistos[solicitud.id_envio] = num_fila
            validas.append(solicitud)
        errores += errores_fila
    return validas, errores


def cargar_solicitudes(ruta_csv, catalogos):
    """Lee un CSV de solicitudes y devuelve (solicitudes_validas, errores)."""
    with open(ruta_csv, encoding="utf-8-sig", newline="") as archivo:
        return validar_filas(csv.DictReader(archivo), catalogos)
