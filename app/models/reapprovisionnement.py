"""
Modèle Reapprovisionnement : historique de chaque entrée de stock
"""
from datetime import datetime
from app import db


class Reapprovisionnement(db.Model):
    """Enregistre chaque réapprovisionnement de stock (une ligne par opération)."""
    __tablename__ = 'reapprovisionnement'

    id = db.Column(db.Integer, primary_key=True)
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'), nullable=False)
    quantite = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    produit = db.relationship('Produit', backref='reapprovisionnements')

    def to_dict(self):
        return {
            'id': self.id,
            'produit_id': self.produit_id,
            'quantite': self.quantite,
            'date': self.date.isoformat() if self.date else None,
            'user_id': self.user_id,
            'produit_nom': self.produit.nom if self.produit else 'Produit supprimé'
        }

    def __repr__(self):
        return f'<Reapprovisionnement produit={self.produit_id} +{self.quantite}>'
