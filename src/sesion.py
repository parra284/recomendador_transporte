"""Reglas de la sesión: inicio con rostro o PIN, bloqueo por ausencia y desbloqueo.

Funciones puras: reciben el estado y devuelven (nuevo_estado, mensaje_de_error | None).
"""

from dataclasses import dataclass, replace

from src.biometria import es_la_misma_persona, identificar
from src.usuarios import verificar_pin


@dataclass(frozen=True)
class EstadoSesion:
    usuario: str | None = None       # id del usuario autenticado
    bloqueado: bool = False
    intentos_pin: int = 0

    @property
    def autenticado(self):
        return self.usuario is not None


def pin_disponible(estado, max_intentos):
    return estado.intentos_pin < max_intentos


def _entrar(estado, usuario):
    return replace(estado, usuario=usuario, bloqueado=False, intentos_pin=0)


def iniciar_con_rostro(estado, huella, usuarios, umbral):
    coincidencia = identificar(huella, list(usuarios.values()), umbral)
    if coincidencia is None:
        return estado, "Rostro no reconocido. Intente de nuevo o use su PIN."
    return _entrar(estado, coincidencia.usuario.usuario), None


def iniciar_con_pin(estado, id_usuario, pin, usuarios, max_intentos):
    if not pin_disponible(estado, max_intentos):
        return estado, "Demasiados intentos con PIN. Ingrese con reconocimiento facial."
    usuario = usuarios.get(id_usuario)
    if usuario is None or not verificar_pin(usuario, pin):
        intentos = estado.intentos_pin + 1
        restantes = max_intentos - intentos
        mensaje = (f"Usuario o PIN incorrecto. Le quedan {restantes} intento(s)." if restantes > 0
                   else "Demasiados intentos con PIN. Ingrese con reconocimiento facial.")
        return replace(estado, intentos_pin=intentos), mensaje
    return _entrar(estado, id_usuario), None


def bloquear(estado):
    return replace(estado, bloqueado=True) if estado.autenticado else estado


def desbloquear_con_rostro(estado, huella, usuarios, umbral):
    """Solo la misma persona que inició sesión puede desbloquear."""
    usuario = usuarios.get(estado.usuario)
    if usuario is None or not es_la_misma_persona(huella, usuario, umbral):
        return estado, "El rostro no coincide con el usuario de la sesión."
    return _entrar(estado, usuario.usuario), None


def desbloquear_con_pin(estado, pin, usuarios, max_intentos):
    return iniciar_con_pin(estado, estado.usuario, pin, usuarios, max_intentos)


def cerrar_sesion(estado):
    # Conserva los intentos fallidos para que cerrar sesión no sirva para reintentar PIN.
    return EstadoSesion(intentos_pin=estado.intentos_pin)
