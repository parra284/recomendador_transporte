"""Registra (o actualiza) un operario autorizado: huella facial + PIN de respaldo.

Uso (lo corre un administrador, en el equipo donde está la app):
    python -m src.registrar_usuario --usuario jperez --nombre "Juana Pérez"
    python -m src.registrar_usuario --usuario jperez --nombre "Juana Pérez" --foto ruta.jpg
    python -m src.registrar_usuario --eliminar jperez

Antes de registrar, la persona debe autorizar el tratamiento de su dato biométrico
(Ley 1581 de 2012). Solo se guarda la huella numérica, nunca la foto.
"""

import argparse
import getpass
import sys
from pathlib import Path

import cv2

from src.biometria import ReconocedorFacial
from src.usuarios import (
    cargar_config_seguridad,
    cargar_usuarios,
    crear_usuario,
    error_formato_pin,
    guardar_usuarios,
    pin_en_uso,
)


def capturar_desde_camara():
    """Abre la cámara; ESPACIO captura, ESC cancela. Devuelve la imagen o None."""
    camara = cv2.VideoCapture(0)
    if not camara.isOpened():
        print("No se pudo abrir la cámara.")
        return None
    imagen = None
    try:
        while True:
            ok, cuadro = camara.read()
            if not ok:
                print("No se pudo leer la cámara.")
                break
            cv2.imshow("Registro facial - ESPACIO captura, ESC cancela", cuadro)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla == 32:
                imagen = cuadro
                break
            if tecla == 27:
                break
    finally:
        camara.release()
        cv2.destroyAllWindows()
    return imagen


def pedir_pin(config, usuarios, usuario):
    while True:
        pin = getpass.getpass("PIN de respaldo: ")
        error = error_formato_pin(pin, config.pin_min_digitos, config.pin_max_digitos)
        if error:
            print(error)
            continue
        if pin_en_uso(usuarios, pin, excepto=usuario):
            # El ingreso es solo con PIN: dos personas con el mismo PIN no se podrían distinguir.
            print("Ese PIN ya lo usa otra persona. Elija uno diferente.")
            continue
        if getpass.getpass("Repita el PIN: ") != pin:
            print("Los PIN no coinciden.")
            continue
        return pin


def confirmar_autorizacion(nombre):
    respuesta = input(f"¿{nombre} autorizó el tratamiento de su dato biométrico? (s/n): ")
    return respuesta.strip().lower() == "s"


def registrar(args, config):
    if not confirmar_autorizacion(args.nombre):
        print("Registro cancelado: se requiere autorización.")
        return 1
    imagen = cv2.imread(str(args.foto)) if args.foto else capturar_desde_camara()
    if imagen is None:
        print("No se obtuvo ninguna imagen.")
        return 1
    reconocedor = ReconocedorFacial(config.ruta_detector, config.ruta_reconocedor)
    resultado = reconocedor.huella(imagen)
    if resultado.error:
        print(resultado.error)
        return 1
    usuarios = cargar_usuarios(config.archivo_usuarios)
    pin = pedir_pin(config, usuarios, args.usuario)
    accion = "actualizado" if args.usuario in usuarios else "registrado"
    usuarios[args.usuario] = crear_usuario(args.usuario, args.nombre, resultado.huella, pin)
    guardar_usuarios(usuarios, config.archivo_usuarios)
    print(f"Usuario {args.usuario} {accion}.")
    return 0


def eliminar(usuario, config):
    usuarios = cargar_usuarios(config.archivo_usuarios)
    if usuarios.pop(usuario, None) is None:
        print(f"No existe el usuario {usuario}.")
        return 1
    guardar_usuarios(usuarios, config.archivo_usuarios)
    print(f"Usuario {usuario} eliminado (su huella fue borrada).")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--usuario")
    parser.add_argument("--nombre")
    parser.add_argument("--foto", type=Path, help="Foto del rostro en vez de usar la cámara")
    parser.add_argument("--eliminar", metavar="USUARIO")
    args = parser.parse_args()
    config = cargar_config_seguridad()
    if args.eliminar:
        return eliminar(args.eliminar, config)
    if not (args.usuario and args.nombre):
        parser.error("indique --usuario y --nombre (o --eliminar)")
    return registrar(args, config)


if __name__ == "__main__":
    sys.exit(main())
