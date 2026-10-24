"""Verifica que los CSV de data/ tengan las columnas esperadas y códigos del catálogo.

Uso: python -m src.verificar_datos
"""

import csv
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "data"
DIR_CONFIG = RAIZ / "config"

COLUMNAS_SOLICITUD = [
    "id_solicitud", "origen", "destino", "fecha_cita", "tipo_contenedor", "peso_bruto_t",
    "imo", "clase_imo", "refrigerada", "temperatura_c", "extradimensionada",
    "valor_declarado_usd", "modalidad_aduanera", "prioridad", "observaciones",
]

COLUMNAS_ESPERADAS = {
    "solicitudes_ejemplo.csv": COLUMNAS_SOLICITUD,
    "solicitudes_invalidas.csv": COLUMNAS_SOLICITUD,
    "proveedores.csv": [
        "id_proveedor", "nombre", "equipos", "peso_max_t", "permite_imo", "permite_refrigerada",
        "permite_extradimensionada", "poliza_monto_usd", "poliza_vence", "habilitacion_vence",
    ],
    "rutas_proveedor.csv": ["id_proveedor", "origen", "destino"],
    "tarifas.csv": ["id_proveedor", "origen", "destino", "tipo_contenedor", "precio_cop"],
    "capacidad.csv": ["id_proveedor", "fecha", "tipo_contenedor", "estado", "camiones_libres"],
    "historial_viajes.csv": [
        "id_viaje", "id_proveedor", "origen", "destino", "tipo_contenedor", "cargue", "entrega",
        "entrega_comprometida", "novedad",
    ],
    "etiquetas.csv": ["id_proveedor", "tipo", "etiqueta", "condicion"],
    "tiempos_base.csv": ["origen", "destino", "horas_base"],
}

# solicitudes_invalidas.csv solo se revisa por columnas: sus errores son intencionales.
ARCHIVOS_SIN_REVISION_DE_CODIGOS = {"solicitudes_invalidas.csv"}

ESTADOS_CAPACIDAD = {"confirmada", "sin_capacidad"}
TIPOS_ETIQUETA = {"fortaleza", "debilidad"}


def errores_de_columnas(nombre, columnas_reales, columnas_esperadas):
    """Devuelve errores si las columnas no coinciden exactamente (nombre y orden)."""
    if columnas_reales == columnas_esperadas:
        return []
    return [f"{nombre}: columnas {columnas_reales} != esperadas {columnas_esperadas}"]


def errores_de_codigo(nombre, num_fila, campo, valor, validos):
    """Devuelve un error si el valor no pertenece al conjunto de válidos."""
    if valor in validos:
        return []
    return [f"{nombre} fila {num_fila}: {campo}='{valor}' no está en el catálogo"]


def errores_de_condicion(nombre, num_fila, condicion):
    """Valida que la condición tenga formato campo=valor con un campo de la solicitud."""
    campo, separador, valor = condicion.partition("=")
    if not separador or not valor:
        return [f"{nombre} fila {num_fila}: condicion '{condicion}' no tiene formato campo=valor"]
    if campo not in COLUMNAS_SOLICITUD:
        return [f"{nombre} fila {num_fila}: condicion usa campo desconocido '{campo}'"]
    if "*" in valor[:-1]:
        return [f"{nombre} fila {num_fila}: '*' solo se admite al final en '{condicion}'"]
    return []


def errores_de_fila(nombre, num_fila, fila, catalogos, ids_proveedor):
    """Revisa los códigos de una fila según las columnas que tenga."""
    errores = []
    reglas = {
        "origen": set(catalogos["origenes"]),
        "destino": set(catalogos["destinos"]),
        "tipo_contenedor": set(catalogos["tipos_contenedor"]),
        "prioridad": set(catalogos["prioridades"]),
        "modalidad_aduanera": set(catalogos["modalidades_aduaneras"]) | {""},
        "estado": ESTADOS_CAPACIDAD,
        "tipo": TIPOS_ETIQUETA,
        "id_proveedor": ids_proveedor,
    }
    for campo, validos in reglas.items():
        if campo in fila and not (nombre == "proveedores.csv" and campo == "id_proveedor"):
            errores += errores_de_codigo(nombre, num_fila, campo, fila[campo], validos)
    if "equipos" in fila:
        for equipo in fila["equipos"].split("|"):
            errores += errores_de_codigo(nombre, num_fila, "equipos", equipo, reglas["tipo_contenedor"])
    if "condicion" in fila:
        errores += errores_de_condicion(nombre, num_fila, fila["condicion"])
    return errores


def errores_de_perfiles(perfiles):
    """Verifica que los pesos de cada perfil sumen 1."""
    errores = []
    for nombre, pesos in perfiles["perfiles"].items():
        total = sum(pesos.values())
        if abs(total - 1) > 1e-9:
            errores.append(f"perfiles.yaml: el perfil '{nombre}' suma {total}, debe sumar 1")
    return errores


def leer_csv(ruta):
    with open(ruta, encoding="utf-8", newline="") as archivo:
        lector = csv.DictReader(archivo)
        return list(lector.fieldnames or []), list(lector)


def leer_yaml(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


def verificar(dir_datos=DIR_DATOS, dir_config=DIR_CONFIG):
    """Revisa todos los archivos y devuelve la lista de errores encontrados."""
    catalogos = leer_yaml(dir_config / "catalogos.yaml")
    errores = errores_de_perfiles(leer_yaml(dir_config / "perfiles.yaml"))
    _, proveedores = leer_csv(dir_datos / "proveedores.csv")
    ids_proveedor = {p["id_proveedor"] for p in proveedores}

    for nombre, esperadas in COLUMNAS_ESPERADAS.items():
        ruta = dir_datos / nombre
        if not ruta.exists():
            errores.append(f"{nombre}: no existe")
            continue
        columnas, filas = leer_csv(ruta)
        errores_cols = errores_de_columnas(nombre, columnas, esperadas)
        errores += errores_cols
        if errores_cols or nombre in ARCHIVOS_SIN_REVISION_DE_CODIGOS:
            continue
        for num_fila, fila in enumerate(filas, start=2):
            errores += errores_de_fila(nombre, num_fila, fila, catalogos, ids_proveedor)
    return errores


def main():
    errores = verificar()
    for error in errores:
        print(error)
    print("OK: datos verificados sin errores." if not errores else f"{len(errores)} errores.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
