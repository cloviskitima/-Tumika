"""
Modèles de l'identification des produits :
- ProduitSignature : « dataset » visuel (une signature par photo de produit).
- CorrectionIdentification : historique d'apprentissage des corrections du vendeur.
"""
from datetime import datetime
from app import db


class ProduitSignature(db.Model):
    """Signature visuelle d'un produit = référence du dataset de reconnaissance."""
    __tablename__ = 'produit_signature'
    __table_args__ = (db.UniqueConstraint('produit_id', 'image_key', name='uq_sig_produit_image'),)

    id = db.Column(db.Integer, primary_key=True)
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'), nullable=False, index=True)
    image_key = db.Column(db.String(10), default='1')  # '1' ou '2' (image_url_1/2)
    signature = db.Column(db.Text)                      # JSON {dhash, hist}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    produit = db.relationship('Produit', backref=db.backref('signatures', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'produit_id': self.produit_id,
            'image_key': self.image_key,
            'signature': self.signature,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CorrectionIdentification(db.Model):
    """Mémorise une association (signature détectée -> produit choisi par le vendeur)."""
    __tablename__ = 'correction_identification'

    id = db.Column(db.Integer, primary_key=True)
    cle_signature = db.Column(db.String(255), nullable=False, index=True)
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'), nullable=False, index=True)
    methode = db.Column(db.String(30), default='ocr')  # ocr, code, texte, visuel
    occurences = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    produit = db.relationship('Produit', backref=db.backref('corrections', lazy='dynamic'))

    @classmethod
    def enregistrer(cls, cle, produit_id, methode):
        """Enregistre/incrémente une correction (apprentissage)."""
        obj = cls.query.filter_by(cle_signature=cle, produit_id=produit_id, methode=methode).first()
        if obj:
            obj.occurences += 1
        else:
            obj = cls(cle_signature=cle, produit_id=produit_id, methode=methode, occurences=1)
            db.session.add(obj)
        db.session.commit()
        return obj

    @classmethod
    def boost_par_cle(cls, cles):
        """Retourne {produit_id: bonus} d'après les corrections connues."""
        if not cles:
            return {}
        resultats = {}
        for obj in cls.query.filter(cls.cle_signature.in_(list(cles))).all():
            bonus = min(0.20, 0.05 + (obj.occurences - 1) * 0.05)
            resultats[obj.produit_id] = max(resultats.get(obj.produit_id, 0.0), bonus)
        return resultats
