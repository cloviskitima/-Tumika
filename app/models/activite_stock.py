"""
Modèle ActiviteStock : journal de toutes les activités touchant un produit
(création, modification, réapprovisionnement, vente, épuisement, retour, suppression)
"""
from datetime import datetime
from app import db


class ActiviteStock(db.Model):
    """Une ligne = un événement sur un produit : qui, quoi, quand, stock avant/après."""
    __tablename__ = 'activite_stock'

    id = db.Column(db.Integer, primary_key=True)
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    # types : creation, modification, reapprovisionnement, vente, epuisement, retour, suppression
    quantite_avant = db.Column(db.Integer, default=0)
    quantite_apres = db.Column(db.Integer, default=0)
    variation = db.Column(db.Integer, default=0)
    description = db.Column(db.String(255), default='')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    produit = db.relationship('Produit')

    def to_dict(self):
        return {
            'id': self.id,
            'produit_id': self.produit_id,
            'produit_nom': self.produit.nom if self.produit else 'Produit supprimé',
            'type': self.type,
            'quantite_avant': self.quantite_avant,
            'quantite_apres': self.quantite_apres,
            'variation': self.variation,
            'description': self.description,
            'user_id': self.user_id,
            'date': self.date.isoformat() if self.date else None
        }

    def __repr__(self):
        return f'<ActiviteStock #{self.id} {self.type} produit={self.produit_id}>'
