"""
Modèle Parametre : stockage clé/valeur des paramètres de l'application
"""
from datetime import datetime
from app import db


class Parametre(db.Model):
    """Paramètre de l'application (stockage clé/valeur)"""
    __tablename__ = 'parametre'

    id = db.Column(db.Integer, primary_key=True)
    cle = db.Column(db.String(80), unique=True, nullable=False)
    valeur = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {'cle': self.cle, 'valeur': self.valeur, 'updated_at': self.updated_at.isoformat() if self.updated_at else None}

    def __repr__(self):
        return f'<Parametre {self.cle}={self.valeur}>'


DEFAUTS = {
    'nom_entreprise': '#TUMIKA',
    'slogan': 'Gestion intelligente de stock & ventes',
    'adresse': '',
    'telephone': '',
    'email': '',
    'rccm': '',
    'devise_principale': 'USD',
    'theme': 'light',
    'couleur_principale': '#1e3a8a',
    'notif_email': 'true',
    'notif_stock_faible': 'true',
    'notif_nouvelles_ventes': 'true',
    'notif_son': 'false',
    'alert_sound_type': 'sine',
    'alert_sound_frequency': '800',
    'rapport_email_active': 'false',
    'rapport_email_destinataires': '',
    'rapport_email_heure': '07:00',
    'rapport_email_jours': '',
    'smtp_serveur': '',
    'smtp_port': '587',
    'smtp_utilisateur': '',
    'smtp_mot_de_passe': '',
    'smtp_securite': 'starttls',
    'smtp_expediteur_nom': '',
    # ===== Paramètres de la facture =====
    'facture_design': 'moderne',
    'facture_titre': 'FACTURE',
    'facture_afficher_entreprise': 'true',
    'facture_afficher_slogan': 'true',
    'facture_afficher_adresse': 'true',
    'facture_afficher_telephone': 'true',
    'facture_afficher_email': 'true',
    'facture_afficher_rccm': 'true',
    'facture_afficher_numero': 'true',
    'facture_afficher_date': 'true',
    'facture_afficher_mention': 'false',
    'facture_mention': 'TVA 16% incluse dans le prix de vente — déjà acquittée lors du dédouanement des marchandises.',
    'facture_afficher_signatures': 'true',
    'facture_signature_image': '',
    'facture_cachet_image': '',
}


def get_param(cle, defaut=None):
    """Retourne la valeur d'un paramètre (avec défaut)."""
    p = Parametre.query.filter_by(cle=cle).first()
    if p is not None:
        return p.valeur
    return defaut if defaut is not None else DEFAUTS.get(cle)


def set_param(cle, valeur):
    """Enregistre un paramètre (créé ou mis à jour)."""
    p = Parametre.query.filter_by(cle=cle).first()
    if p:
        p.valeur = str(valeur)
    else:
        p = Parametre(cle=cle, valeur=str(valeur))
        db.session.add(p)
    return p


def all_params():
    """Retourne tous les paramètres sous forme de dictionnaire."""
    resultats = dict(DEFAUTS)
    for p in Parametre.query.all():
        resultats[p.cle] = p.valeur
    return resultats
