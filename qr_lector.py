import cv2
from typing import Optional

def decodificar_qr(imagen):
    detector = cv2.QRCodeDetector()
    texto, _puntos, _rectificado = detector.detectAndDecode(imagen)
    if not texto:
        return None
    return texto.strip() or None


def _procesar_con_detector(imagen) -> Optional[str]:
    return decodificar_qr(imagen)


def pipeline_decodificacion(imagen_bgr):
    """
    Orden obligatorio:
    1) Grises
    2) Threshold fijo
    3) Threshold adaptativo gaussiano
    """
    gris = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY)
    texto = _procesar_con_detector(gris)
    if texto:
        return texto, "Fase 1: Escala de grises"

    _, fijo = cv2.threshold(gris, 127, 255, cv2.THRESH_BINARY)
    texto = _procesar_con_detector(fijo)
    if texto:
        return texto, "Fase 2: Threshold fijo"

    adaptativo = cv2.adaptiveThreshold(
        gris,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    texto = _procesar_con_detector(adaptativo)
    if texto:
        return texto, "Fase 3: Threshold adaptativo gaussiano"

    return None, None
