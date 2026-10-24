"""Usuarios autorizados: huella facial, PIN de respaldo y configuración de seguridad.

Solo se guarda la huella numérica del rostro (vector de 128 valores), nunca fotos.
"""

import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
RUTA_SEGURIDAD = RAIZ / "config" / "seguridad.yaml"
ITERACIONES_PBKDF2 = 200_000


@dataclass(frozen=True)
class ConfigSeguridad:
    segundos_ausencia: int
    umbral_similitud: float
    max_intentos_pin: int
    pin_min_digitos: int
    pin_max_digitos: int
    archivo_usuarios: Path
    ruta_detector: Path
    ruta_reconocedor: Path


@dataclass(frozen=True)
class Usuario:
    usuario: str
    nombre: str
    huella: tuple       # vector facial SFace
    pin_hash: str
    sal: str


def cargar_config_seguridad(ruta=RUTA_SEGURIDAD, raiz=RAIZ):
    with open(ruta, encoding="utf-8") as archivo:
        c = yaml.safe_load(archivo)
    dir_modelos = raiz / c["dir_modelos"]
    return ConfigSeguridad(
        segundos_ausencia=int(c["segundos_ausencia"]),
        umbral_similitud=float(c["umbral_similitud"]),
        max_intentos_pin=int(c["max_intentos_pin"]),
        pin_min_digitos=int(c["pin_min_digitos"]),
        pin_max_digitos=int(c["pin_max_digitos"]),
        archivo_usuarios=raiz / c["archivo_usuarios"],
        ruta_detector=dir_modelos / c["modelo_detector"],
        ruta_reconocedor=dir_modelos / c["modelo_reconocedor"],
    )


# --- PIN ---

def error_formato_pin(pin, min_digitos, max_digitos):
    """Mensaje de error si el PIN no tiene el formato permitido; None si es válido."""
    if not pin.isdigit():
        return "El PIN solo puede tener números."
    if not min_digitos <= len(pin) <= max_digitos:
        return f"El PIN debe tener entre {min_digitos} y {max_digitos} dígitos."
    return None


def hash_pin(pin, sal):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(sal), ITERACIONES_PBKDF2).hex()


def nueva_sal():
    return secrets.token_hex(16)


def verificar_pin(usuario, pin):
    return hmac.compare_digest(hash_pin(pin, usuario.sal), usuario.pin_hash)


def crear_usuario(usuario, nombre, huella, pin):
    sal = nueva_sal()
    return Usuario(usuario, nombre, tuple(float(x) for x in huella), hash_pin(pin, sal), sal)


# --- Archivo de usuarios ---

def cargar_usuarios(ruta):
    """{usuario: Usuario}; vacío si el archivo aún no existe."""
    ruta = Path(ruta)
    if not ruta.exists():
        return {}
    with open(ruta, encoding="utf-8") as archivo:
        filas = json.load(archivo)
    return {f["usuario"]: Usuario(**{**f, "huella": tuple(f["huella"])}) for f in filas}


def guardar_usuarios(usuarios, ruta):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    filas = [{**asdict(u), "huella": list(u.huella)} for u in usuarios.values()]
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(filas, archivo, ensure_ascii=False, indent=2)
