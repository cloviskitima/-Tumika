"""
Reconnaissance de texte (OCR) via Tesseract.
Lit le texte d'une image, extrait les tokens ressemblant à des références de pièces
(ex. "B-RA-2458", "KD22B", "R15-2.5") et les lignes avec leur confiance.
"""
import re
import os
from . import get_pytesseract, imread_bytes, TESSDATA_DIR

# Token « référence pièce » : suite alphanumérique avec séparateurs courants,
# contenant au moins une lettre ET un chiffre (exclut mots purs et nombres purs).
REF_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9._\-/]{2,23})(?![A-Za-z0-9])')


def _est_reference(tok):
    return any(c.isalpha() for c in tok) and any(c.isdigit() for c in tok)


def _preparer(image):
    """Prétraitement rapide : gris + agrandissement des petites images."""
    cv2 = __import__('cv2', fromlist=['cvtColor'])
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if h < 400 or w < 600:
        scale = max(1.5, 700.0 / max(h, 1))
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    return gray


def ocr_image(data: bytes):
    """Analyse une image et retourne le texte détecté.

    Retourne un dict : {success, texte, lignes, references, conf_moyenne, langue}
    """
    pytesseract = get_pytesseract()
    image = imread_bytes(data)
    if pytesseract is None or image is None:
        return {'success': False, 'texte': '', 'lignes': [], 'references': [], 'conf_moyenne': 0.0, 'langue': 'inconnue'}

    try:
        gray = _preparer(image)
        config = '--psm 6 -l fra+eng'
        data_dict = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config=config)

        lignes = []
        refs = []
        confs = []
        for i in range(len(data_dict['text'])):
            txt = (data_dict['text'][i] or '').strip()
            conf = data_dict['conf'][i]
            if not txt or conf < 0:
                continue
            try:
                conf_f = float(conf)
            except (ValueError, TypeError):
                conf_f = 0.0
            x = data_dict['left'][i]
            y = data_dict['top'][i]
            w = data_dict['width'][i]
            h = data_dict['height'][i]
            lignes.append({'texte': txt, 'conf': conf_f, 'x': x, 'y': y, 'w': w, 'h': h})
            if conf_f >= 40:
                confs.append(conf_f)
            for tok in REF_TOKEN_RE.findall(txt):
                if _est_reference(tok):
                    refs.append({'texte': tok, 'conf': conf_f, 'x': x, 'y': y, 'w': w, 'h': h})

        # texte complet (lignes reconstruites)
        texte = '\n'.join(l.get('texte', '') for l in lignes)

        return {
            'success': True,
            'texte': texte,
            'lignes': lignes,
            'references': refs,
            'conf_moyenne': round(sum(confs) / len(confs), 1) if confs else 0.0,
            'langue': 'fra+eng',
        }
    except Exception:
        return {'success': False, 'texte': '', 'lignes': [], 'references': [], 'conf_moyenne': 0.0, 'langue': 'inconnue'}
