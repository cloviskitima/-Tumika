"""
Modèle User pour l'authentification
"""
import json
from copy import deepcopy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

# ─── Rôles & permissions ─────────────────────────────────────────────

# Actions possibles pour chaque module
MODULES = ['stock', 'sales', 'cash', 'users', 'reports', 'settings']
ACTIONS = ['view', 'create', 'update', 'delete']

MODULE_LABELS = {
    'stock': 'Stock',
    'sales': 'Ventes',
    'cash': 'Caisse',
    'users': 'Utilisateurs',
    'reports': 'Rapports',
    'settings': 'Paramètres',
}

ACTION_LABELS = {
    'view': 'Voir',
    'create': 'Créer',
    'update': 'Modifier',
    'delete': 'Supprimer',
}

ROLE_LABELS = {
    'admin': 'Administrateur',
    'manager': 'Manager',
    'user': 'Utilisateur',
}


def _perms_totales(valeur):
    """Renvoie un dict {module: {action: bool}} entièrement à la même valeur."""
    return {m: {a: bool(valeur) for a in ACTIONS} for m in MODULES}


# Permissions par défaut de chaque rôle
ROLE_PERMISSIONS = {
    'admin': _perms_totales(True),
    'manager': {
        'stock': {'view': True, 'create': True, 'update': True, 'delete': False},
        'sales': {'view': True, 'create': True, 'update': True, 'delete': False},
        'cash': {'view': True, 'create': True, 'update': True, 'delete': False},
        'users': {'view': True, 'create': False, 'update': False, 'delete': False},
        'reports': {'view': True, 'create': True, 'update': True, 'delete': False},
        'settings': {'view': False, 'create': False, 'update': False, 'delete': False},
    },
    'user': {
        'stock': {'view': True, 'create': False, 'update': False, 'delete': False},
        'sales': {'view': True, 'create': True, 'update': False, 'delete': False},
        'cash': {'view': True, 'create': False, 'update': False, 'delete': False},
        'users': {'view': False, 'create': False, 'update': False, 'delete': False},
        'reports': {'view': False, 'create': False, 'update': False, 'delete': False},
        'settings': {'view': False, 'create': False, 'update': False, 'delete': False},
    },
}


def role_permissions(role):
    """Permissions par défaut d'un rôle (copie indépendante)."""
    return deepcopy(ROLE_PERMISSIONS.get(role or 'user', ROLE_PERMISSIONS['user']))


def normalize_permissions(raw):
    """Normalise n'importe quel format de permissions stockées en
    dict {module: {action: bool}}. Formats acceptés :
    - None → dict vide
    - ['stock', 'sales'] (liste) → toutes les actions sur ces modules
    - {'stock': True} (dict de booléens) → toutes les actions sur ces modules
    - {'stock': {'view': True, ...}} (dict imbriqué) → actions précises
    """
    result = {}
    if not raw:
        return result
    if isinstance(raw, list):
        for module in raw:
            if module in MODULES:
                result[module] = {a: True for a in ACTIONS}
        return result
    if isinstance(raw, dict):
        for module, valeur in raw.items():
            if module not in MODULES:
                continue
            if isinstance(valeur, dict):
                actions = {a: bool(valeur.get(a, False)) for a in ACTIONS}
            else:
                actions = {a: bool(valeur) for a in ACTIONS}
            result[module] = actions
    return result


class User(db.Model):
    """Modèle d'utilisateur pour l'authentification"""
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    role = db.Column(db.String(20), default='user')  # admin, manager, user
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    permissions = db.Column(db.Text)  # Permissions stockées en JSON
    
    @property
    def perms(self):
        """Retourne les permissions déserialisées (format brut stocké)."""
        if not self.permissions:
            return None
        try:
            return json.loads(self.permissions)
        except (ValueError, TypeError):
            return None
    
    @property
    def permissions_obj(self):
        """Permissions normalisées en dict {module: {action: bool}}."""
        return normalize_permissions(self.perms)
    
    @property
    def effective_permissions(self):
        """Permissions effectives : défauts du rôle + overrides stockés.
        Un administrateur dispose de toutes les permissions."""
        result = role_permissions(self.role)
        if self.role == 'admin':
            return result
        for module, actions in self.permissions_obj.items():
            if module in result:
                result[module].update(actions)
            else:
                result[module] = actions
        return result
    
    def set_permissions(self, perms):
        """Enregistre les permissions en JSON (dict imbriqué ou liste)."""
        if perms is None or (isinstance(perms, dict) and not perms) or perms == []:
            self.permissions = None
        else:
            self.permissions = json.dumps(perms, ensure_ascii=False)
    
    def has_perm(self, module, action='view'):
        """Vrai si l'utilisateur a l'action demandée sur le module."""
        if self.role == 'admin':
            return True
        if module not in MODULES:
            return False
        return bool(self.effective_permissions.get(module, {}).get(action, False))
    
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
        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'nom_complet': self.nom_complet,
            'role': self.role,
            'role_label': ROLE_LABELS.get(self.role or 'user', self.role),
            'is_active': self.is_active,
            'permissions': self.effective_permissions,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
        return data
    
    def __repr__(self):
        return f'<User {self.username}>'
