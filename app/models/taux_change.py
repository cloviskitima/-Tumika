"""
Modèle TauxChange pour la gestion des taux de change
"""
from datetime import datetime, date
from app import db


class TauxChange(db.Model):
    """Modèle de taux de change"""
    __tablename__ = 'taux_change'
    
    id = db.Column(db.Integer, primary_key=True)
    devise_source = db.Column(db.String(10), nullable=False)  # XAF, EUR, USD, etc.
    devise_cible = db.Column(db.String(10), nullable=False)  # XAF, EUR, USD, etc.
    taux = db.Column(db.Float, nullable=False)  # Taux de change
    effective_date = db.Column(db.Date, default=date.today)
    date_mise_a_jour = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convertit le taux de change en dictionnaire"""
        return {
            'id': self.id,
            'devise_source': self.devise_source,
            'devise_cible': self.devise_cible,
            'taux': self.taux,
            'effective_date': self.effective_date.isoformat() if self.effective_date else None,
            'date_mise_a_jour': self.date_mise_a_jour.isoformat() if self.date_mise_a_jour else None
        }
    
    def __repr__(self):
        return f'<TauxChange {self.devise_source} -> {self.devise_cible}: {self.taux}>'
