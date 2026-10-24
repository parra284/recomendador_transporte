"""Pruebas de usuarios, biometría y reglas de sesión (ingreso, bloqueo y desbloqueo)."""

from pathlib import Path

import numpy as np
import pytest

from src.biometria import (
    ReconocedorFacial,
    error_por_cantidad_de_rostros,
    es_la_misma_persona,
    identificar,
    imagen_desde_bytes,
    similitud_coseno,
)
from src.sesion import (
    EstadoSesion,
    bloquear,
    cerrar_sesion,
    desbloquear_con_pin,
    desbloquear_con_rostro,
    iniciar_con_pin,
    iniciar_con_rostro,
    iniciar_solo_con_pin,
    pin_disponible,
)
from src.usuarios import (
    cargar_config_seguridad,
    cargar_usuarios,
    crear_usuario,
    error_formato_pin,
    guardar_usuarios,
    pin_en_uso,
    usuarios_con_pin,
    verificar_pin,
)

UMBRAL = 0.363
MAX_INTENTOS = 3

# Huellas sintéticas: ortogonales entre sí (similitud 0).
HUELLA_ANA = (1.0, 0.0, 0.0)
HUELLA_LUIS = (0.0, 1.0, 0.0)
HUELLA_DESCONOCIDA = (0.0, 0.0, 1.0)


@pytest.fixture(scope="module")
def usuarios():
    return {
        "ana": crear_usuario("ana", "Ana Gómez", HUELLA_ANA, "1234"),
        "luis": crear_usuario("luis", "Luis Mora", HUELLA_LUIS, "5678"),
    }


# --- Configuración ---

def test_config_seguridad_del_proyecto():
    config = cargar_config_seguridad()
    assert config.segundos_ausencia == 10
    assert config.umbral_similitud == pytest.approx(0.363)


# --- PIN ---

@pytest.mark.parametrize("pin, valido", [("1234", True), ("12345678", True), ("123", False),
                                         ("123456789", False), ("12a4", False), ("", False)])
def test_formato_pin(pin, valido):
    assert (error_formato_pin(pin, 4, 8) is None) is valido


def test_pin_se_guarda_con_hash_y_se_verifica(usuarios):
    ana = usuarios["ana"]
    assert "1234" not in ana.pin_hash
    assert verificar_pin(ana, "1234") and not verificar_pin(ana, "4321")


def test_misma_clave_distinta_sal_da_hash_distinto():
    a = crear_usuario("a", "A", HUELLA_ANA, "1234")
    b = crear_usuario("b", "B", HUELLA_ANA, "1234")
    assert a.pin_hash != b.pin_hash


# --- Archivo de usuarios ---

def test_guardar_y_cargar_usuarios(tmp_path, usuarios):
    ruta = tmp_path / "seguridad" / "usuarios.json"
    guardar_usuarios(usuarios, ruta)
    assert cargar_usuarios(ruta) == usuarios


def test_archivo_inexistente_da_cero_usuarios(tmp_path):
    assert cargar_usuarios(tmp_path / "no_existe.json") == {}


# --- Biometría ---

def test_similitud_coseno():
    assert similitud_coseno((1, 0), (2, 0)) == pytest.approx(1)
    assert similitud_coseno((1, 0), (0, 1)) == pytest.approx(0)


def test_identificar_elige_al_mas_parecido_sobre_el_umbral(usuarios):
    huella = (0.9, 0.3, 0.0)  # parecida a Ana, algo a Luis
    assert identificar(huella, list(usuarios.values()), UMBRAL).usuario.usuario == "ana"


def test_identificar_nadie_bajo_el_umbral(usuarios):
    assert identificar(HUELLA_DESCONOCIDA, list(usuarios.values()), UMBRAL) is None


def test_identificar_sin_usuarios():
    assert identificar(HUELLA_ANA, [], UMBRAL) is None


def test_es_la_misma_persona(usuarios):
    assert es_la_misma_persona(HUELLA_ANA, usuarios["ana"], UMBRAL)
    assert not es_la_misma_persona(HUELLA_LUIS, usuarios["ana"], UMBRAL)


@pytest.mark.parametrize("cantidad, hay_error", [(0, True), (1, False), (2, True)])
def test_error_por_cantidad_de_rostros(cantidad, hay_error):
    assert (error_por_cantidad_de_rostros(cantidad) is not None) is hay_error


def test_bytes_que_no_son_imagen():
    assert imagen_desde_bytes(b"esto no es una foto") is None


def test_modelo_faltante_explica_como_descargarlo(tmp_path):
    with pytest.raises(FileNotFoundError, match="descargar_modelos"):
        ReconocedorFacial(tmp_path / "a.onnx", tmp_path / "b.onnx")


def test_imagen_sin_rostro():
    config = cargar_config_seguridad()
    if not config.ruta_reconocedor.exists():
        pytest.skip("modelos no descargados")
    reconocedor = ReconocedorFacial(config.ruta_detector, config.ruta_reconocedor)
    resultado = reconocedor.huella(np.full((240, 320, 3), 128, dtype=np.uint8))
    assert resultado.huella is None and "ningún rostro" in resultado.error


# --- Ingreso ---

def test_ingreso_con_rostro_reconocido(usuarios):
    estado, error = iniciar_con_rostro(EstadoSesion(), HUELLA_LUIS, usuarios, UMBRAL)
    assert error is None and estado.usuario == "luis" and not estado.bloqueado


def test_ingreso_con_rostro_desconocido(usuarios):
    estado, error = iniciar_con_rostro(EstadoSesion(), HUELLA_DESCONOCIDA, usuarios, UMBRAL)
    assert error and not estado.autenticado


def test_ingreso_con_pin_correcto_reinicia_intentos(usuarios):
    estado, error = iniciar_con_pin(EstadoSesion(intentos_pin=2), "ana", "1234", usuarios, MAX_INTENTOS)
    assert error is None and estado.usuario == "ana" and estado.intentos_pin == 0


@pytest.mark.parametrize("usuario, pin", [("ana", "0000"), ("nadie", "1234")])
def test_ingreso_con_pin_incorrecto_suma_intento(usuarios, usuario, pin):
    estado, error = iniciar_con_pin(EstadoSesion(), usuario, pin, usuarios, MAX_INTENTOS)
    assert not estado.autenticado and estado.intentos_pin == 1 and "2 intento" in error


def test_pin_se_agota_tras_max_intentos(usuarios):
    estado = EstadoSesion()
    for _ in range(MAX_INTENTOS):
        estado, _ = iniciar_con_pin(estado, "ana", "0000", usuarios, MAX_INTENTOS)
    assert not pin_disponible(estado, MAX_INTENTOS)
    estado, error = iniciar_con_pin(estado, "ana", "1234", usuarios, MAX_INTENTOS)  # PIN correcto
    assert not estado.autenticado and "reconocimiento facial" in error


def test_ingreso_solo_con_pin_identifica_al_usuario(usuarios):
    estado, error = iniciar_solo_con_pin(EstadoSesion(intentos_pin=1), "5678", usuarios, MAX_INTENTOS)
    assert error is None and estado.usuario == "luis" and estado.intentos_pin == 0


def test_ingreso_solo_con_pin_incorrecto_suma_intento(usuarios):
    estado, error = iniciar_solo_con_pin(EstadoSesion(), "0000", usuarios, MAX_INTENTOS)
    assert not estado.autenticado and estado.intentos_pin == 1 and "2 intento" in error


def test_ingreso_solo_con_pin_repetido_no_adivina_el_usuario():
    repetidos = {"a": crear_usuario("a", "A", HUELLA_ANA, "1111"), "b": crear_usuario("b", "B", HUELLA_LUIS, "1111")}
    estado, error = iniciar_solo_con_pin(EstadoSesion(), "1111", repetidos, MAX_INTENTOS)
    assert not estado.autenticado and estado.intentos_pin == 1 and "reconocimiento facial" in error


def test_ingreso_solo_con_pin_respeta_el_limite_de_intentos(usuarios):
    estado = EstadoSesion(intentos_pin=MAX_INTENTOS)
    estado, error = iniciar_solo_con_pin(estado, "1234", usuarios, MAX_INTENTOS)  # PIN correcto
    assert not estado.autenticado and "reconocimiento facial" in error


def test_pin_en_uso_por_otro_usuario(usuarios):
    assert pin_en_uso(usuarios, "1234")                      # es el de Ana
    assert not pin_en_uso(usuarios, "1234", excepto="ana")   # Ana puede conservar su propio PIN
    assert not pin_en_uso(usuarios, "9999")
    assert usuarios_con_pin(usuarios, "5678") == ["luis"]


def test_rostro_sigue_disponible_con_pin_agotado(usuarios):
    estado = EstadoSesion(intentos_pin=MAX_INTENTOS)
    estado, error = iniciar_con_rostro(estado, HUELLA_ANA, usuarios, UMBRAL)
    assert error is None and estado.usuario == "ana"


# --- Bloqueo y desbloqueo ---

def test_bloquear_sesion_activa():
    assert bloquear(EstadoSesion(usuario="ana")).bloqueado


def test_bloquear_sin_sesion_no_hace_nada():
    assert bloquear(EstadoSesion()) == EstadoSesion()


def test_desbloquear_con_rostro_de_la_misma_persona(usuarios):
    estado, error = desbloquear_con_rostro(EstadoSesion("ana", True), HUELLA_ANA, usuarios, UMBRAL)
    assert error is None and not estado.bloqueado


def test_otra_persona_registrada_no_desbloquea(usuarios):
    estado, error = desbloquear_con_rostro(EstadoSesion("ana", True), HUELLA_LUIS, usuarios, UMBRAL)
    assert error and estado.bloqueado and estado.usuario == "ana"


def test_desbloquear_con_pin_solo_del_usuario_de_la_sesion(usuarios):
    bloqueada = EstadoSesion("ana", True)
    estado, error = desbloquear_con_pin(bloqueada, "5678", usuarios, MAX_INTENTOS)  # PIN de Luis
    assert error and estado.bloqueado
    estado, error = desbloquear_con_pin(bloqueada, "1234", usuarios, MAX_INTENTOS)
    assert error is None and not estado.bloqueado


def test_cerrar_sesion_conserva_intentos_fallidos():
    estado = cerrar_sesion(EstadoSesion("ana", True, intentos_pin=2))
    assert not estado.autenticado and not estado.bloqueado and estado.intentos_pin == 2
