"""
Détection de codes-barres / QR et reconnaissance d'objets (YOLO).
"""
from . import get_cv2, get_yolo, imread_bytes


def detecter_codes(data: bytes):
    """Détecte les codes-barres et QR codes dans une image.

    Retourne une liste de dicts : {type: 'QRCODE'|'CODE128'|..., data: str, conf: float}
    """
    cv2 = get_cv2()
    image = imread_bytes(data)
    if cv2 is None or image is None:
        return []

    codes = []
    try:
        import pyzbar.pyzbar as pyzbar
    except Exception:
        pyzbar = None

    if pyzbar is not None:
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            decoded = pyzbar.decode(gray)
            if not decoded:
                # essai avec binarisation si rien trouvé
                _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                decoded = pyzbar.decode(th)
            for d in decoded:
                codes.append({
                    'type': d.type or 'CODE',
                    'data': (d.data or b'').decode('utf-8', errors='ignore'),
                    'conf': 0.95,
                })
        except Exception:
            pass

    # Repli OpenCV pour les QR
    if not any(c['type'] == 'QRCODE' for c in codes):
        try:
            detector = cv2.QRCodeDetector()
            data, pts, _ = detector.detectAndDecode(image)
            if data and data.strip():
                codes.append({'type': 'QRCODE', 'data': data.strip(), 'conf': 0.9})
        except Exception:
            pass

    return codes


def detecter_objets(data: bytes, seuil: float = 0.4):
    """Détecte les objets avec YOLO (modèle pré-entraîné COCO).

    Retourne une liste de dicts : {label, conf, box: [x1,y1,x2,y2]}.
    Retourne [] si YOLO est indisponible ou si rien n'est détecté.
    """
    yolo = get_yolo()
    cv2 = get_cv2()
    image = imread_bytes(data)
    if yolo is None or cv2 is None or image is None:
        return []

    try:
        res = yolo(image, verbose=False, conf=seuil)
        objets = []
        for r in res:
            for box in r.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                objets.append({
                    'label': r.names[cls],
                    'conf': round(conf, 3),
                    'box': [x1, y1, x2, y2],
                })
        return objets
    except Exception:
        return []
