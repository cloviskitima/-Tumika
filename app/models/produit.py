"""
Modèle Produit pour la gestion du stock
"""
from datetime import datetime
import random
import string
from app import db


class Produit(db.Model):
    """Modèle de produit pour la gestion du stock"""
    __tablename__ = 'produit'
    
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    nom = db.Column(db.String(200), nullable=False)
    categorie = db.Column(db.String(100))
    fournisseur = db.Column(db.String(100))
    code_barres = db.Column(db.String(50), unique=True)
    devise = db.Column(db.String(10), default='XAF')
    prix_achat = db.Column(db.Float, nullable=False)
    prix_vente = db.Column(db.Float, nullable=False)
    quantite = db.Column(db.Integer, default=0)
    stock_min = db.Column(db.Integer, default=5)
    image_url_1 = db.Column(db.String(512))
    image_url_2 = db.Column(db.String(512))
    compatibilites = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def statut(self):
        """Calcule le statut du stock"""
        if self.quantite == 0:
            return 'épuisé'
        elif self.quantite <= self.stock_min:
            return 'faible'
        else:
            return 'disponible'
    
    def generer_reference(self):
        """Génère une référence automatique en local"""
        if not self.reference:
            # Utiliser un compteur basé sur la date et un nombre aléatoire
            prefix = 'PRD'
            timestamp = datetime.now().strftime('%Y%m%d')
            random_num = ''.join(random.choices(string.digits, k=4))
            self.reference = f"{prefix}-{timestamp}-{random_num}"
    
    def generer_code_barres(self):
        """Génère un code-barres EAN-13 compatible en local"""
        if not self.code_barres:
            # Générer un code-barres de 13 chiffres (EAN-13)
            timestamp = datetime.now().strftime('%Y%m%d')
            random_part = ''.join(random.choices(string.digits, k=7))
            self.code_barres = f"{timestamp}{random_part}"
    
    def generer_codes_automatiques(self):
        """Génère automatiquement la référence et le code-barres"""
        self.generer_reference()
        self.generer_code_barres()
    
    def to_dict(self):
        """Convertit le produit en dictionnaire"""
        return {
            'id': self.id,
            'reference': self.reference,
            'nom': self.nom,
            'categorie': self.categorie,
            'fournisseur': self.fournisseur,
            'code_barres': self.code_barres,
            'devise': self.devise,
            'prix_achat': self.prix_achat,
            'prix_vente': self.prix_vente,
            'quantite': self.quantite,
            'stock_min': self.stock_min,
            'image_url_1': self.image_url_1,
            'image_url_2': self.image_url_2,
            'compatibilites': self.compatibilites,
            'statut': self.statut,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f'<Produit {self.reference} - {self.nom}>'
