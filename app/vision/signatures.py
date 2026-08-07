"""
Signatures visuelles pour la reconnaissance par « dataset ».
Chaque photo de produit enregistrée devient une référence. À la reconnaissance,
on compare la signature de l'image scannée à toutes les références du dataset.

Signature = dHash (64 bits, robuste échelle/couleur) + histogramme couleur normalisé.
La comparaison est vectorisée (numpy) => très rapide même avec beaucoup de produits.
"""
import json
from . import get_cv2, imread_bytes


def _dhash(gray, size=8):
    cv2 = get_cv2()
    resized = cv2.resize(gray, (size + 1, size))
    diff = resized[:, 1:] > resized[:, :-1]
    val = 0
    for i, b in enumerate(diff.flatten()):
        val |= (int(b) & 1) << i
    return val


def _hist(image):
    cv2 = get_cv2()
    try:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hists = []
        for i, ch in enumerate([0, 1, 2]):
            hist = cv2.calcHist([hsv], [i], None, [8], [0, 256])
            cv2.normalize(hist, hist)
            hists.extend(float(v[0]) for v in hist)
        return hists
    except Exception:
        return [0.0] * 24


def signature_image(image):
    """Calcule la signature (dhash + hist) d'une image cv2."""
    cv2 = get_cv2()
    if cv2 is None or image is None:
        return None
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return {'dhash': _dhash(gray), 'hist': _hist(image)}
    except Exception:
        return None


def signature_bytes(data: bytes):
    image = imread_bytes(data)
    if image is None:
        return None
    return signature_image(image)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _corr_hist(h1, h2):
    try:
        import math
        # corrélation cosinus entre deux vecteurs d'histogrammes
        num = sum(x * y for x, y in zip(h1, h2))
        d1 = math.sqrt(sum(x * x for x in h1))
        d2 = math.sqrt(sum(y * y for y in h2))
        if d1 == 0 or d2 == 0:
            return 0.0
        return num / (d1 * d2)
    except Exception:
        return 0.0


def similitude(sig_a, sig_b):
    """Score 0..1 entre deux signatures. 1.0 = identiques."""
    if not sig_a or not sig_b:
        return 0.0
    dh_score = 1.0 - (hamming(sig_a['dhash'], sig_b['dhash']) / 64.0)
    hist_score = _corr_hist(sig_a.get('hist') or [], sig_b.get('hist') or [])
    return round(0.6 * dh_score + 0.4 * hist_score, 4)


def trouver_similaires(sig_requete, signatures, top=5):
    """Compare la signature requête à une liste de signatures références.

    `signatures` : liste de dicts {'produit_id', 'dhash', 'hist'}
    Retourne la liste des `top` meilleurs produits (dédupliqués) avec leur score.
    """
    if not sig_requete or not signatures:
        return []
    try:
        import numpy as np
        dhashes = np.array([s['dhash'] for s in signatures], dtype=np.int64)
        # Hamming vectorisé (bits de différence)
        diffs = np.bitwise_xor(dhashes, int(sig_requete['dhash']))
        counts = np.zeros(len(diffs), dtype=np.int64)
        v = diffs
        while v.any():
            counts += v & 1
            v >>= 1
        scores = 0.6 * (1.0 - counts / 64.0)
        # + histogramme pour départager
        for i, s in enumerate(signatures):
            scores[i] += 0.4 * _corr_hist(sig_requete.get('hist') or [], s.get('hist') or [])
        scores = np.round(scores, 4)
        order = np.argsort(-scores)
    except Exception:
        scored = [(similitude(sig_requete, s), s) for s in signatures]
        scored.sort(key=lambda x: -x[0])
        order = [s['produit_id'] for _, s in scored[:top]]
        return [(pid, score) for score, s in scored[:top] for pid in [s['produit_id']]]

    resultats = []
    vus = set()
    for idx in order:
        pid = signatures[int(idx)]['produit_id']
        if pid in vus:
            continue
        vus.add(pid)
        resultats.append((pid, round(float(scores[int(idx)]), 4)))
        if len(resultats) >= top:
            break
    return resultats


def signature_json(sig):
    """Sérialise une signature pour la base de données."""
    return json.dumps({'dhash': sig['dhash'], 'hist': sig['hist']})


def signature_from_json(s):
    try:
        d = json.loads(s)
        return {'dhash': int(d['dhash']), 'hist': [float(x) for x in d.get('hist', [])]}
    except Exception:
        return None
