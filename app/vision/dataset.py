"""
Gestion du « dataset » visuel : à chaque enregistrement de produit avec photo,
on calcule et stocke sa signature (ProduitSignature). Ces signatures servent ensuite
de références pour la reconnaissance visuelle (matching rapide, sans entraînement).
"""
import os

from . import signatures


def _chemin_image(image_url, upload_folder):
    if not image_url:
        return None
    nom = os.path.basename(image_url)
    chemin = os.path.join(upload_folder, nom)
    return chemin if os.path.exists(chemin) else None


def signatures_produit(produit, upload_folder):
    """Calcule les signatures des images d'un produit.

    Retourne une liste de dicts {'image_key', 'signature_json'}.
    """
    resultat = []
    for key, url in (('1', produit.image_url_1), ('2', produit.image_url_2)):
        chemin = _chemin_image(url, upload_folder)
        if not chemin:
            continue
        try:
            with open(chemin, 'rb') as f:
                data = f.read()
            sig = signatures.signature_bytes(data)
            if sig:
                resultat.append({'image_key': key, 'signature_json': signatures.signature_json(sig)})
        except Exception:
            continue
    return resultat


def mettre_a_jour_signatures_produit(produit, upload_folder):
    """Enregistre (upsert) les signatures visuelles d'un produit dans le dataset."""
    from app.models.identification import ProduitSignature
    from app import db

    if not (produit.image_url_1 or produit.image_url_2):
        return 0

    calc = signatures_produit(produit, upload_folder)
    nb = 0
    for c in calc:
        sig_obj = ProduitSignature.query.filter_by(
            produit_id=produit.id, image_key=c['image_key']).first()
        if sig_obj:
            if sig_obj.signature != c['signature_json']:
                sig_obj.signature = c['signature_json']
                nb += 1
        else:
            db.session.add(ProduitSignature(
                produit_id=produit.id,
                image_key=c['image_key'],
                signature=c['signature_json'],
            ))
            nb += 1
    db.session.commit()
    return nb


def construire_dataset(upload_folder, limit=None):
    """Construit le dataset pour tous les produits ayant une image sans signature.

    Retourne le nombre de signatures créées/mises à jour.
    """
    from app.models.produit import Produit
    from app import db

    produits = Produit.query.filter(
        (Produit.image_url_1.isnot(None)) | (Produit.image_url_2.isnot(None))
    ).all()
    if limit:
        produits = produits[:limit]

    total = 0
    for p in produits:
        try:
            total += mettre_a_jour_signatures_produit(p, upload_folder)
        except Exception:
            db.session.rollback()
    return total
