"""Descarga los modelos faciales de OpenCV (YuNet y SFace) a la carpeta modelos/.

Uso: python -m src.descargar_modelos
"""

import sys
import urllib.request

from src.usuarios import cargar_config_seguridad

BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
URLS = {
    "face_detection_yunet_2023mar.onnx": f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
TAMANO_MINIMO_BYTES = 100_000  # un puntero de Git LFS pesa ~130 bytes


def main():
    config = cargar_config_seguridad()
    for ruta in (config.ruta_detector, config.ruta_reconocedor):
        if ruta.exists() and ruta.stat().st_size > TAMANO_MINIMO_BYTES:
            print(f"Ya existe: {ruta.name}")
            continue
        ruta.parent.mkdir(parents=True, exist_ok=True)
        print(f"Descargando {ruta.name}...")
        urllib.request.urlretrieve(URLS[ruta.name], ruta)
        if ruta.stat().st_size <= TAMANO_MINIMO_BYTES:
            print(f"Error: {ruta.name} se descargó incompleto.")
            return 1
    print("Modelos listos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
