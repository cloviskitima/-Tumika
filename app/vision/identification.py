"""
Pipeline d'identification des produits — algorithme combiné.

Priorité : Code-barres/QR → OCR (référence) → Recherche texte floue →
Reconnaissance visuelle (dataset de signatures) → YOLO → Historique des corrections.

Chaque méthode produit un score de confiance (0..1). Si le meilleur score est sous le
seuil, on retourne les 5 meilleurs candidats avec leur pourcentage. Les corrections du
vendeur sont mémorisées (CorrectionIdentification) et boostent les prochaines recherches.
"""
import hashlib
import re

from rapidfuzz import fuzz

from . import detection, ocr, signatures


SEUIL_CERTAIN = 0.85
SEUIL_PROPOSITION = 0.60
LIMITE_ALTERNATIVES = 5


def _norm(s):
    """Normalise une chaîne pour comparaison (majuscules, sans espaces ni signes)."""
    if not s:
        return ''
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def _cle_code(data):
    return 'code:' + (data or '').strip()


def _cle_ref(token):
    return 'ref:' + _norm(token)


def _cle_texte(texte):
    norm = _norm(texte)
    if not norm:
        return None
    return 'texte:' + hashlib.sha1(norm.encode('utf-8')).hexdigest()[:16]


def _indices_produits():
    """Retourne (index_id, index_reference_norm, liste_produits)."""
    from app.models.produit import Produit
    produits = Produit.query.all()
    index_id = {p.id: p for p in produits}
    index_ref = {}
    for p in produits:
        for valeur in (p.reference, p.code_barres):
            if valeur:
                index_ref.setdefault(_norm(valeur), []).append(p.id)
    return index_id, index_ref, produits


def _match_texte(texte, index_id, produits):
    """Recherche floue (rapidfuzz) sur nom/référence/code-barres.

    Retourne {produit_id: (score, methode)}.
    """
    if not texte:
        return {}
    q = texte.strip()
    scores = {}
    for p in produits:
        best = 0.0
        # code-barres exact → max
        if p.code_barres and _norm(p.code_barres) == _norm(q):
            best = 1.0
        else:
            noms = [p.nom or '', p.reference or '', p.code_barres or '', p.categorie or '']
            for champ in noms:
                if not champ:
                    continue
                r = max(
                    fuzz.token_set_ratio(q, champ),
                    fuzz.partial_ratio(q, champ),
                    fuzz.ratio(q, champ),
                )
                if r > best * 100:
                    best = r / 100.0
        if best > 0:
            # convertir la ressemblance brute en score de confiance
            conf = 0.4 + 0.55 * best
            conf = min(conf, 0.95)
            scores[p.id] = (round(conf, 4), 'recherche' if best < 1.0 else 'code-barres')
    return scores


def _match_ocr(ocr_result, index_ref, index_id):
    """Fait correspondre les références OCR aux références produits.

    Retourne (candidats, cles_historique) avec candidats = {produit_id: (score, 'ocr')}.
    """
    candidats = {}
    cles = []
    tokens = ocr_result.get('references', []) if ocr_result else []
    for tok in tokens:
        t = _norm(tok['texte'])
        if not t:
            continue
        cles.append(_cle_ref(tok['texte']))
        if t in index_ref:
            for pid in index_ref[t]:
                cur = candidats.get(pid, (0.0, 'ocr'))
                if 0.97 > cur[0]:
                    candidats[pid] = (0.97, 'ocr')
        else:
            # ressemblance partielle
            for ref, ids in index_ref.items():
                if len(t) >= 4 and (t in ref or ref in t):
                    r = fuzz.ratio(t, ref) / 100.0
                    conf = 0.5 + 0.45 * r
                    for pid in ids:
                        cur = candidats.get(pid, (0.0, 'ocr'))
                        if conf > cur[0]:
                            candidats[pid] = (round(conf, 4), 'ocr')
    return candidats, cles


def _candidats_visuels(sig_requete, signatures_list):
    """Reconnaissance par dataset : retourne {produit_id: (score, 'visuel')}."""
    resultat = {}
    if not sig_requete:
        return resultat
    try:
        matches = signatures.trouver_similaires(sig_requete, signatures_list, top=LIMITE_ALTERNATIVES + 2)
        for pid, sim in matches:
            if sim >= 0.35:
                resultat[pid] = (round(min(0.62 * sim + 0.30, 0.92), 4), 'visuel')
    except Exception:
        pass
    return resultat


def _appliquer_historique(candidats, cles_historique):
    """Ajoute le bonus d'apprentissage aux candidats concernés."""
    if not cles_historique:
        return
    from app.models.identification import CorrectionIdentification
    boosts = CorrectionIdentification.boost_par_cle(cles_historique)
    for pid, bonus in boosts.items():
        if pid in candidats:
            score, methode = candidats[pid]
            candidats[pid] = (round(min(score + bonus, 1.0), 4), methode)


def _fusionner(*sources):
    """Fusionne plusieurs dicts {produit_id: (score, methode)} en prenant le max par produit."""
    fusion = {}
    for src in sources:
        for pid, (score, methode) in src.items():
            if score <= 0:
                continue
            if pid not in fusion or score > fusion[pid][0]:
                fusion[pid] = (score, methode)
    return fusion


def _classer(candidats, index_id):
    """Trie les candidats et construit la réponse finale."""
    classe = sorted(candidats.items(), key=lambda x: -x[1][0])
    resultat = []
    for pid, (score, methode) in classe:
        p = index_id.get(pid)
        if p is None:
            continue
        resultat.append({
            'produit': p.to_dict(),
            'confiance': score,
            'pourcentage': round(score * 100),
            'methode': methode,
        })
        if len(resultat) >= LIMITE_ALTERNATIVES:
            break
    return resultat


def analyser_image(data: bytes, signaler_progres=None):
    """Analyse une image et identifie le produit (algorithme combiné complet)."""
    index_id, index_ref, produits = _indices_produits()

    # 1. Code-barres / QR
    codes = detection.detecter_codes(data)
    candidats = {}
    cles_hist = []
    for c in codes:
        cle = _cle_code(c['data'])
        cles_hist.append(cle)
        norm = _norm(c['data'])
        if norm in index_ref:
            for pid in index_ref[norm]:
                candidats[pid] = (1.0, 'code-barres' if c['type'] != 'QRCODE' else 'QR')
        else:
            # un code peut correspondre à une référence saisie à la main
            for p in produits:
                if p.reference and _norm(p.reference) == norm:
                    candidats[p.id] = (0.97, 'code-barres')

    # 2. OCR
    ocr_result = ocr.ocr_image(data)
    candidats_ocr, cles_ocr = _match_ocr(ocr_result, index_ref, index_id)
    cles_hist += cles_ocr
    candidats = _fusionner(candidats, candidats_ocr)

    # 3. Reconnaissance visuelle (dataset)
    sig = signatures.signature_bytes(data)
    visuels = []
    if sig is not None:
        from app.models.identification import ProduitSignature
        sig_records = ProduitSignature.query.filter(ProduitSignature.signature.isnot(None)).all()
        sig_list = []
        for r in sig_records:
            sig = signatures.signature_from_json(r.signature)
            if sig:
                sig_list.append({'produit_id': r.produit_id, **sig})
        if sig_list:
            candidats_visuels = _candidats_visuels(sig, sig_list)
            visuels = [{'produit_id': pid, 'score': sc} for pid, (sc, _m) in candidats_visuels.items()]
            candidats = _fusionner(candidats, candidats_visuels)

    # 4. YOLO (signal informatif + éventuel boost historique par label)
    objets_yolo = detection.detecter_objets(data)
    labels = [o['label'] for o in objets_yolo]
    if labels:
        cles_yolo = ['yolo:' + l.lower() for l in labels]
        from app.models.identification import CorrectionIdentification
        boosts_yolo = CorrectionIdentification.boost_par_cle(cles_yolo)
        for pid, bonus in boosts_yolo.items():
            score, methode = candidats.get(pid, (0.0, 'visuel'))
            candidats[pid] = (round(min(score + bonus, 1.0), 4), 'yolo')
        cles_hist += cles_yolo

    # 5. Historique des corrections (apprentissage)
    _appliquer_historique(candidats, cles_hist)

    classes = _classer(candidats, index_id)
    return _construire_reponse(classes, 'image', {
        'codes': codes,
        'ocr': ocr_result,
        'visuels': visuels,
        'objets_yolo': objets_yolo,
    }, cles_hist)


def identifier_par_texte(texte: str):
    """Identifie par recherche texte floue (nom, référence, code-barres)."""
    index_id, _index_ref, produits = _indices_produits()
    candidats = _match_texte(texte, index_id, produits)
    cle = _cle_texte(texte)
    if cle:
        _appliquer_historique(candidats, [cle])
    classes = _classer(candidats, index_id)
    return _construire_reponse(classes, 'texte', {'texte_saisi': texte}, [cle] if cle else [])


def identifier_par_code(code: str):
    """Identifie par un code saisi manuellement (code-barres ou QR)."""
    index_id, index_ref, produits = _indices_produits()
    candidats = {}
    norm = _norm(code)
    if norm in index_ref:
        for pid in index_ref[norm]:
            candidats[pid] = (1.0, 'code-barres')
    if not candidats:
        candidats = _match_texte(code, index_id, produits)
    cle = _cle_code(code)
    _appliquer_historique(candidats, [cle])
    classes = _classer(candidats, index_id)
    return _construire_reponse(classes, 'code', {'code_saisi': code}, [cle])


def _construire_reponse(classes, mode, detail=None, cles_signature=None):
    """Construit la réponse JSON finale avec détermination et top 5 si incertain."""
    if not classes:
        return {
            'success': True,
            'mode': mode,
            'determination': 'aucun',
            'confiance': 0.0,
            'produit': None,
            'alternatives': [],
            'cles_signature': cles_signature or [],
            'detail_analyse': detail or {},
        }
    top = classes[0]
    determination = 'certain' if top['confiance'] >= SEUIL_CERTAIN else (
        'probable' if top['confiance'] >= SEUIL_PROPOSITION else 'incertain')
    return {
        'success': True,
        'mode': mode,
        'determination': determination,
        'confiance': top['confiance'],
        'methode': top['methode'],
        'produit': top['produit'] if top['confiance'] >= SEUIL_PROPOSITION else None,
        'alternatives': classes if top['confiance'] < SEUIL_CERTAIN else [top],
        'cles_signature': cles_signature or [],
        'detail_analyse': detail or {},
    }
