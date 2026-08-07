"""
Modèles Comptabilité : Plan Comptable Général Congolais (PCGC) et livre journal
"""
from datetime import datetime
from app import db


class CompteComptable(db.Model):
    """Compte du plan comptable congolais (PCGC)"""
    __tablename__ = 'compte_comptable'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(10), unique=True, nullable=False)
    libelle = db.Column(db.String(255), nullable=False)
    classe = db.Column(db.Integer, nullable=False)
    nature = db.Column(db.String(10), default='debit')  # debit | credit (solde normal)
    est_actif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'numero': self.numero,
            'libelle': self.libelle,
            'classe': self.classe,
            'nature': self.nature,
            'est_actif': self.est_actif
        }

    def __repr__(self):
        return f'<CompteComptable {self.numero} {self.libelle}>'


class EcritureComptable(db.Model):
    """Écriture du livre journal (une ligne = un débit / un crédit)"""
    __tablename__ = 'ecriture_comptable'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    numero_piece = db.Column(db.String(50))
    libelle = db.Column(db.String(255), nullable=False)
    compte_debit_id = db.Column(db.Integer, db.ForeignKey('compte_comptable.id'), nullable=False)
    compte_credit_id = db.Column(db.Integer, db.ForeignKey('compte_comptable.id'), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    devise = db.Column(db.String(10), default='USD')
    taux_change = db.Column(db.Float, nullable=True)
    source = db.Column(db.String(50), default='manuel')  # vente | caisse | credit | manuel
    source_id = db.Column(db.Integer, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    compte_debit = db.relationship('CompteComptable', foreign_keys=[compte_debit_id])
    compte_credit = db.relationship('CompteComptable', foreign_keys=[compte_credit_id])

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'numero_piece': self.numero_piece,
            'libelle': self.libelle,
            'compte_debit_id': self.compte_debit_id,
            'compte_credit_id': self.compte_credit_id,
            'compte_debit_numero': self.compte_debit.numero if self.compte_debit else '',
            'compte_debit_libelle': self.compte_debit.libelle if self.compte_debit else '',
            'compte_credit_numero': self.compte_credit.numero if self.compte_credit else '',
            'compte_credit_libelle': self.compte_credit.libelle if self.compte_credit else '',
            'montant': self.montant,
            'devise': self.devise,
            'taux_change': self.taux_change,
            'source': self.source,
            'source_id': self.source_id,
            'user_id': self.user_id
        }

    def __repr__(self):
        return f'<EcritureComptable {self.id} {self.compte_debit_id}→{self.compte_credit_id}>'
