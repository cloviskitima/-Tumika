"""
Modèle Vente pour l'application
"""
from datetime import datetime
from app import db

class Vente(db.Model):
    __tablename__ = 'ventes'
    
    id = db.Column(db.Integer, primary_key=True)
    client = db.Column(db.String(255), nullable=True)
    telephone = db.Column(db.String(50), nullable=True)
    montant = db.Column(db.Float, nullable=False)
    mode_paiement = db.Column(db.String(50), default='cash')
    statut = db.Column(db.String(50), default='completed')
    devise = db.Column(db.String(10), default='USD')
    taux_change = db.Column(db.Float, nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    date_echeance = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relation avec les produits vendus
    produits_vendus = db.relationship('ProduitVendu', backref='vente', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'client': self.client,
            'telephone': self.telephone,
            'montant': self.montant,
            'mode_paiement': self.mode_paiement,
            'statut': self.statut,
            'devise': self.devise,
            'taux_change': self.taux_change,
            'date': self.date.isoformat() if self.date else None,
            'date_echeance': self.date_echeance.isoformat() if self.date_echeance else None,
            'produits_count': len(self.produits_vendus),
            'est_credit': self.mode_paiement == 'credit' or self.statut == 'pending',
            'produits': [pv.to_dict() for pv in self.produits_vendus]
        }

class ProduitVendu(db.Model):
    __tablename__ = 'produits_vendus'
    
    id = db.Column(db.Integer, primary_key=True)
    vente_id = db.Column(db.Integer, db.ForeignKey('ventes.id'), nullable=False)
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'), nullable=False)
    quantite = db.Column(db.Integer, nullable=False)
    prix_vente = db.Column(db.Float, nullable=False)
    prix_achat = db.Column(db.Float, nullable=True)
    
    # Relation avec le produit
    produit = db.relationship('Produit', backref='produits_vendus')
    
    def to_dict(self):
        return {
            'id': self.id,
            'produit_id': self.produit_id,
            'nom': self.produit.nom if self.produit else 'Produit supprimé',
            'reference': self.produit.reference if self.produit else '',
            'quantite': self.quantite,
            'prix_vente': self.prix_vente,
            'prix_achat': self.prix_achat
        }
