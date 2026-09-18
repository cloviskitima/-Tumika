"""
Package principal de l'application
"""
from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
import secrets

db = SQLAlchemy()
migrate = Migrate()


def _get_secret_key(basedir):
    """Retourne une clé secrète persistante (générée une seule fois puis stockée)."""
    key_file = os.path.join(os.path.dirname(basedir), 'instance', 'secret_key')
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    try:
        os.makedirs(os.path.dirname(key_file), exist_ok=True)
        if os.path.exists(key_file):
            with open(key_file, 'r', encoding='utf-8') as f:
                key = f.read().strip()
                if key:
                    return key
        key = secrets.token_hex(32)
        with open(key_file, 'w', encoding='utf-8') as f:
            f.write(key)
        return key
    except Exception:
        return secrets.token_hex(32)


def create_app():
    """Création de l'application Flask"""
    # Définir le chemin absolu du dossier templates et static
    basedir = os.path.abspath(os.path.dirname(__file__))
    template_dir = os.path.join(os.path.dirname(basedir), 'templates')
    static_dir = os.path.join(os.path.dirname(basedir), 'static')
    
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    
    # Configuration
    app.config['SECRET_KEY'] = _get_secret_key(basedir)
    # Base de données : DATABASE_URL (ex. PostgreSQL sur Render) sinon SQLite locale
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///motostock.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Durcissement des cookies de session
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = False  # HTTP (pas de TLS local)
    app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 8  # 8h
    
    # Configuration pour l'upload d'images
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads')
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
    
    # Initialisation des extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Import des modèles
    from app.models.user import User
    from app.models.produit import Produit
    from app.models.caisse import CaisseMovement
    from app.models.login_log import LoginLog
    from app.models.comptabilite import CompteComptable, EcritureComptable
    from app.models.parametre import Parametre
    from app.models.identification import ProduitSignature, CorrectionIdentification
    from app.models.reapprovisionnement import Reapprovisionnement
    from app.models.activite_stock import ActiviteStock
    from app.models.envoi_email import EnvoiEmail
    
    # Import des routes
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    from app.routes.backup import backup_bp
    from app.webhook import webhook_bp
    
    # Enregistrement des blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(backup_bp)
    app.register_blueprint(webhook_bp)

    # Injection de l'utilisateur courant dans tous les templates
    @app.context_processor
    def inject_user():
        from app.models.user import User, ROLE_LABELS
        user_id = session.get('user_id')
        user = User.query.get(user_id) if user_id else None
        return {'current_user': user, 'ROLE_LABELS': ROLE_LABELS}
    
    # Création des tables
    with app.app_context():
        db.create_all()
        # Migration légère : ajouter la colonne permissions si absente (base existante)
        try:
            from sqlalchemy import inspect as sa_inspect, text as sa_text
            cols = [c['name'] for c in sa_inspect(db.engine).get_columns('user')]
            if 'permissions' not in cols:
                db.session.execute(sa_text('ALTER TABLE "user" ADD COLUMN permissions TEXT'))
                db.session.commit()
        except Exception:
            pass
        # Utilisateur admin par défaut (hébergement : base neuve au 1er démarrage)
        try:
            from app.models.user import User
            if not User.query.filter_by(username='admin').first():
                admin = User(
                    username='admin',
                    email='admin@motostock.local',
                    first_name='Administrateur',
                    last_name='Principal',
                    role='admin',
                    is_active=True
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
        except Exception:
            pass
        from app.utils.comptabilite import seed_plan_comptable
        try:
            seed_plan_comptable()
        except Exception:
            pass
        # Reconstitution de l'historique des activités de stock (une seule fois)
        from app.utils.backfill_activites import backfill_activites_stock
        try:
            backfill_activites_stock()
        except Exception:
            pass
    
    # Anti-veille (hébergeurs gratuits : Render…) : maintient l'instance éveillée
    from app.keepalive import start_keepalive
    start_keepalive(app)

    # Synchronisation des données (site en ligne uniquement) : GitHub -> base locale.
    # GitLab/Render télécharge et affiche la base poussée depuis l'ordinateur ;
    # jamais activé en local (GITHUB_SYNC_ENABLED=1 chez l'hébergeur uniquement).
    if os.environ.get('GITHUB_SYNC_ENABLED') == '1':
        from app.sync import force_sync
        try:
            force_sync(app)
        except Exception:
            pass

    # À chaque requête (rafraîchissement de page, /health…), vérifie GitHub de
    # façon limitée et récupère la base si une nouvelle sauvegarde existe.
    @app.before_request
    def _synchroniser_donnees():
        from app.sync import sync_if_needed
        sync_if_needed()

    return app
