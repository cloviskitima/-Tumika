"""
Modèle User pour l'authentification
"""
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(db.Model):
    """Modèle d'utilisateur pour l'authentification"""
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    role = db.Column(db.String(20), default='user')  # admin, user, manager
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    permissions = db.Column(db.Text)  # Permissions stockées en JSON
    
    @property
    def perms(self):
        """Retourne les permissions déserialisées"""
        if not self.permissions:
            return []
        try:
            return json.loads(self.permissions)
        except (ValueError, TypeError):
            return []
    
    def set_permissions(self, perms):
        """Enregistre les permissions en JSON"""
        self.permissions = json.dumps(list(perms)) if perms else None
    
    def set_password(self, password):
        """Hash le mot de passe"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Vérifie le mot de passe"""
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self):
        """Met à jour la date de dernière connexion"""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    @property
    def nom_complet(self):
        """Retourne le nom complet ou le nom d'utilisateur"""
        parts = [p for p in [self.first_name, self.last_name] if p]
        if parts:
            return " ".join(parts)
        return self.username

    def to_dict(self):
        """Convertit l'utilisateur en dictionnaire"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'nom_complet': self.nom_complet,
            'role': self.role,
            'is_active': self.is_active,
            'permissions': self.perms,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    def __repr__(self):
        return f'<User {self.username}>'
