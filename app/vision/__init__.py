"""
Configuration et utilitaires de base du module Vision (OCR, codes, YOLO, signatures).
Tous les imports lourds sont paresseux pour ne pas ralentir le démarrage de Flask.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TESSDATA_DIR = os.path.join(BASE_DIR, 'tessdata')
MODELS_DIR = os.path.join(BASE_DIR, 'models')
YOLO_MODEL_PATH = os.path.join(MODELS_DIR, 'yolov8n.pt')

# Pointage vers Tesseract installé (UB-Mannheim)
TESSERACT_CMD = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if not os.path.exists(TESSERACT_CMD):
    alt = r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    if os.path.exists(alt):
        TESSERACT_CMD = alt
    else:
        # Dernier recours : tesseract présent dans le PATH (winget/choco, Linux, etc.)
        import shutil
        TESSERACT_CMD = shutil.which('tesseract') or TESSERACT_CMD

os.environ['TESSDATA_PREFIX'] = TESSDATA_DIR


def get_cv2():
    """Retourne cv2 (OpenCV) s'il est installé, sinon None."""
    try:
        import cv2
        return cv2
    except Exception:
        return None


def get_pytesseract():
    """Retourne pytesseract configuré, sinon None."""
    try:
        import pytesseract
        if os.path.exists(TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        return pytesseract
    except Exception:
        return None


def get_yolo():
    """Charge le modèle YOLO une seule fois (singleton paresseux)."""
    global _YOLO_MODEL
    try:
        if _YOLO_MODEL is None:
            from ultralytics import YOLO
            path = YOLO_MODEL_PATH
            if not os.path.exists(path):
                path = 'yolov8n.pt'
            _YOLO_MODEL = YOLO(path)
        return _YOLO_MODEL
    except Exception:
        return None


_YOLO_MODEL = None


def imread_bytes(data: bytes):
    """Décode des octets image en image BGR (cv2) ou None."""
    cv2 = get_cv2()
    if cv2 is None:
        return None
    try:
        import numpy as np
        arr = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        return arr if arr is not None and arr.size > 0 else None
    except Exception:
        return None
