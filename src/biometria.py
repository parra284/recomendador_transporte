"""Detección y reconocimiento facial con OpenCV (YuNet + SFace)."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ResultadoHuella:
    huella: tuple | None
    error: str | None


@dataclass(frozen=True)
class Coincidencia:
    usuario: object     # Usuario
    similitud: float


class ReconocedorFacial:
    """Envuelve los modelos de OpenCV; se crea una sola vez porque cargarlos es lento."""

    def __init__(self, ruta_detector, ruta_reconocedor):
        for ruta in (ruta_detector, ruta_reconocedor):
            if not ruta.exists():
                raise FileNotFoundError(
                    f"Falta el modelo {ruta.name}. Ejecute: python -m src.descargar_modelos")
        self._detector = cv2.FaceDetectorYN.create(str(ruta_detector), "", (320, 320), 0.8)
        self._reconocedor = cv2.FaceRecognizerSF.create(str(ruta_reconocedor), "")

    def detectar(self, imagen_bgr):
        alto, ancho = imagen_bgr.shape[:2]
        self._detector.setInputSize((ancho, alto))
        _, rostros = self._detector.detect(imagen_bgr)
        return [] if rostros is None else list(rostros)

    def huella(self, imagen_bgr):
        """Extrae la huella del único rostro de la imagen, o explica por qué no se pudo."""
        rostros = self.detectar(imagen_bgr)
        error = error_por_cantidad_de_rostros(len(rostros))
        if error:
            return ResultadoHuella(None, error)
        alineado = self._reconocedor.alignCrop(imagen_bgr, rostros[0])
        vector = self._reconocedor.feature(alineado).flatten()
        return ResultadoHuella(tuple(float(x) for x in vector), None)


def imagen_desde_bytes(datos):
    """Decodifica una foto (JPG/PNG) a matriz BGR de OpenCV; None si no es una imagen."""
    return cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)


def error_por_cantidad_de_rostros(cantidad):
    if cantidad == 0:
        return "No se detectó ningún rostro. Mire de frente a la cámara con buena luz."
    if cantidad > 1:
        return "Se detectó más de un rostro. Debe aparecer solo la persona que inicia sesión."
    return None


def similitud_coseno(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def identificar(huella, usuarios, umbral):
    """Usuario registrado más parecido, si supera el umbral; None si nadie coincide."""
    candidatos = [Coincidencia(u, similitud_coseno(huella, u.huella)) for u in usuarios]
    aceptados = [c for c in candidatos if c.similitud >= umbral]
    return max(aceptados, key=lambda c: c.similitud, default=None)


def es_la_misma_persona(huella, usuario, umbral):
    return similitud_coseno(huella, usuario.huella) >= umbral
