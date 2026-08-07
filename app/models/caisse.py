"""
Modèle Caisse pour les mouvements de trésorerie
"""
from datetime import datetime
from app import db


class CaisseMovement(db.Model):
    __tablename__ = 'caisse_mouvements'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)
    libelle = db.Column(db.String(255), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    devise = db.Column(db.String(10), nullable=False, default='USD')
    taux_change = db.Column(db.Float, nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    solde_apres = db.Column(db.Float, nullable=False)
    vente_id = db.Column(db.Integer, db.ForeignKey('ventes.id'), nullable=True)
    notes = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'libelle': self.libelle,
            'montant': self.montant,
            'devise': self.devise,
            'taux_change': self.taux_change,
            'date': self.date.isoformat() if self.date else None,
            'solde_apres': self.solde_apres,
            'vente_id': self.vente_id,
            'notes': self.notes
        }

    def __repr__(self):
        return f'<CaisseMovement {self.type} {self.montant}>'
