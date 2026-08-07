"""
Modèle EnvoiEmail : file d'attente des rapports quotidiens par email.

Chaque ligne = un rapport programmé (ou déjà envoyé) pour une date précise.
Lorsque l'application est hors ligne, les rapports restent « en_attente »
et sont envoyés dès que la connexion internet est rétablie.
"""
from datetime import datetime
from app import db


class EnvoiEmail(db.Model):
    __tablename__ = 'envoi_email'

    id = db.Column(db.Integer, primary_key=True)
    destinataire = db.Column(db.String(255), nullable=False)
    sujet = db.Column(db.String(255), nullable=False)
    date_prevue = db.Column(db.DateTime, nullable=False, index=True)
    date_debut = db.Column(db.DateTime, nullable=False)
    date_fin = db.Column(db.DateTime, nullable=False)
    statut = db.Column(db.String(20), default='en_attente', index=True)
    # statuts : en_attente, envoye, erreur
    date_envoi = db.Column(db.DateTime, nullable=True)
    erreur = db.Column(db.Text, nullable=True)
    nb_tentatives = db.Column(db.Integer, default=0)
    derniere_tentative = db.Column(db.DateTime, nullable=True)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('destinataire', 'date_prevue', name='uq_envoi_dest_prevue'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'destinataire': self.destinataire,
            'sujet': self.sujet,
            'date_prevue': self.date_prevue.isoformat() if self.date_prevue else None,
            'date_debut': self.date_debut.isoformat() if self.date_debut else None,
            'date_fin': self.date_fin.isoformat() if self.date_fin else None,
            'statut': self.statut,
            'date_envoi': self.date_envoi.isoformat() if self.date_envoi else None,
            'erreur': self.erreur,
            'nb_tentatives': self.nb_tentatives,
            'date_creation': self.date_creation.isoformat() if self.date_creation else None
        }

    def __repr__(self):
        return f'<EnvoiEmail #{self.id} {self.statut} {self.destinataire} prévu={self.date_prevue}>'
