"""
Package principal de l'application
"""
from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
import secrets
import sqlite3
import logging
import sqlalchemy

_log = logging.getLogger('tumika')

db = SQLAlchemy()
migrate = Migrate()

# Version de l'application, affichée en bas de la barre latérale.
# À incrémenter à chaque livraison pour que l'utilisateur puisse vérifier
# d'un coup d'œil que l'interface est bien à jour.
APP_VERSION = '2.1'


def _chemin_base_sqlite(app):
    """Emplacement du fichier SQLite utilisé par l'application, ou None."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not uri.startswith('sqlite:'):
        return None
    nom = uri.split('sqlite:///')[-1].split('?')[0]
    if not nom or nom == ':memory:':
        return None
    if not os.path.isabs(nom):
        nom = os.path.join(app.instance_path, nom)
    return nom


def _sauvegarder_avant_migration(app):
    """Copie de sécurité de la base AVANT toute modification de schéma.

    Une migration quiturned mal ne doit jamais pouvoirdestroyre les données
    du client : on conserve toujours une copie datée de l'état d'avant.
    """
    base = _chemin_base_sqlite(app)
    if not base or not os.path.exists(base):
        return None
    dossier = os.path.join(app.instance_path, 'sauvegardes')
    try:
        os.makedirs(dossier, exist_ok=True)
        from datetime import datetime
        from app.utils.sauvegarde_sqlite import copie_sqlite_consistante
        cible = os.path.join(dossier, 'avant-migration-%s.db'
                             % datetime.now().strftime('%Y%m%d-%H%M%S'))
        methode, message = copie_sqlite_consistante(base, cible)
        if methode == 'echec':
            _log.error('Sauvegarde avant migration IMPOSSIBLE : %s', message)
            return None
        # On ne garde que les 5 dernières : la place est comptée sur l'hébergement.
        anciennes = sorted(f for f in os.listdir(dossier) if f.startswith('avant-migration-'))
        for vieille in anciennes[:-5]:
            try:
                os.remove(os.path.join(dossier, vieille))
            except OSError:
                pass
        _log.info('Base sauvegardée avant migration (%s) : %s',
                  os.path.basename(cible), message)
        return cible
    except Exception:
        return None


def _base_saine(app):
    """Contrôle d'intégrité de la base. None si tout va bien, sinon le problème."""
    base = _chemin_base_sqlite(app)
    if not base or not os.path.exists(base):
        return None
    try:
        import sqlite3 as _sq
        c = _sq.connect('file:%s?mode=ro' % base.replace('\\', '/'), uri=True, timeout=10)
        r = c.execute('PRAGMA integrity_check').fetchone()
        c.close()
        if r and str(r[0]).lower() == 'ok':
            return None
        return str(r[0]) if r else 'integrité inconnue'
    except Exception as e:
        return str(e)


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

    # --- SQLite : éviter « database is locked » -------------------------------
    # Le serveur fait tourner plusieurs threads (4 requêtes simultanées) et des
    # tâches de fond (rapports email, synchronisation) qui écrivent en même
    # temps que les visiteurs. Sans réglage, SQLite bloque tout le monde dès
    # qu'une écriture est en cours : une simple lecture échoue alors et la page
    # renvoie une erreur 500.
    #   * journal_mode=WAL : les lectures ne bloquent plus les écritures.
    #   * busy_timeout     : une écriture attend au lieu d'échouer aussitôt.
    #   * synchronous      : équilibre sûr/durabilité avec le mode WAL.
    _uri = app.config['SQLALCHEMY_DATABASE_URI']
    if _uri.startswith('sqlite:'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {'timeout': 30, 'check_same_thread': False},
            'pool_pre_ping': True,
        }

        @sqlalchemy.event.listens_for(sqlalchemy.engine.Engine, 'connect')
        def _reglages_sqlite(dbapi_connection, connection_record):
            try:
                if not isinstance(dbapi_connection, sqlite3.Connection):
                    return
                curseur = dbapi_connection.cursor()
                curseur.execute('PRAGMA journal_mode=WAL')
                curseur.execute('PRAGMA busy_timeout=30000')
                curseur.execute('PRAGMA synchronous=NORMAL')
                curseur.close()
            except Exception:
                pass

    # Durcissement des cookies de session
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = False  # HTTP (pas de TLS local)
    app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 8  # 8h

    # Rechargement automatique des gabarits.
    # Sans ceci, Jinja garde en memoire les templates compiles : une mise a jour
    # qui remplace un .html n'est visible qu'apres un redemarrage du serveur.
    # Active, le simple rechargement de la page (F5) suffit pour les
    # changements d'interface, ce qui rend les mises a jour fiables.
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['DEBUG'] = False
    try:
        app.jinja_env.auto_reload = True
    except Exception:
        pass

    # Aucune mise en cache des pages : apres une mise a jour, le navigateur
    # ne doit jamais resservir l'ancien HTML.
    @app.after_request
    def _no_cache_pages(response):
        try:
            ct = (response.headers.get('Content-Type') or '')
            if 'text/html' in ct or 'application/json' in ct:
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
        except Exception:
            pass
        return response
    
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
    # Tableau de bord : ajoute ses routes /api/dashboard/... sur le meme blueprint
    from app.routes import dashboard as _dashboard_routes
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
        return {'current_user': user, 'ROLE_LABELS': ROLE_LABELS,
                'version_app': APP_VERSION, 'version_maj': _version_maj()}

    # Affichage de la version : permet de vérifier d'un coup d'œil que
    # l'interface affichée correspond bien à la dernière mise à jour installée.
    def _version_maj():
        try:
            p = os.path.join(basedir, 'instance', 'version_maj.txt')
            if os.path.isfile(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return f.read().strip() or '—'
        except Exception:
            pass
        return '—'
    
    # Protection des données du client : contrôle d'intégrité + copie de
    # sécurité AVANT toute migration. Si une migration tourne mal, la base
    # d'origine est toujours récupérable dans instance/sauvegardes.
    _probleme = _base_saine(app)
    _sauvegarder_avant_migration(app)
    if _probleme:
        _log.error("Base de donnees corrompue ou illisible (%s). Les migrations "
                   "ne parviendront probablement pas a s'appliquer. Une copie "
                   "de la base d'origine est conservee dans "
                   "instance/sauvegardes : restaurez-la apres avoir sauvegarde "
                   "la base actuelle.", _probleme)
    else:
        _log.info('Base vérifiée : intègre.')

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
        # Migration légère : colonnes de réduction sur les ventes (ajout-only, aucune donnée touchée)
        try:
            from sqlalchemy import inspect as sa_inspect2, text as sa_text2
            _insp = sa_inspect2(db.engine)
            _ventes = {c['name'] for c in _insp.get_columns('ventes')}
            for _col, _ddl in (
                ('remise_globale', 'REAL DEFAULT 0'),
                ('remise_type', "TEXT DEFAULT 'montant'"),
                ('remise_articles', 'REAL DEFAULT 0'),
                ('motif_remise', 'TEXT'),
            ):
                if _col not in _ventes:
                    db.session.execute(sa_text2(f'ALTER TABLE ventes ADD COLUMN {_col} {_ddl}'))
            if 'remise' not in {c['name'] for c in _insp.get_columns('produits_vendus')}:
                db.session.execute(sa_text2('ALTER TABLE produits_vendus ADD COLUMN remise REAL DEFAULT 0'))
            db.session.commit()
        except Exception:
            pass
        # Migration légère : date d'ajout en stock (colonne + remplissage depuis la
        # date de création existante, aucune donnée n'est effacée)
        try:
            from sqlalchemy import inspect as sa_inspect3, text as sa_text3
            _insp3 = sa_inspect3(db.engine)
            _tables3 = set(_insp3.get_table_names())
            if 'produit' in _tables3:
                _cols3 = {c['name'] for c in _insp3.get_columns('produit')}
                if 'date_ajout' not in _cols3:
                    db.session.execute(sa_text3('ALTER TABLE produit ADD COLUMN date_ajout DATE'))
                    # Remplissage : on déduit la date d'ajout de la date de création
                    _has_created = 'created_at' in _cols3
                    if _has_created:
                        db.session.execute(sa_text3(
                            'UPDATE produit SET date_ajout = date(created_at) '
                            'WHERE date_ajout IS NULL AND created_at IS NOT NULL'
                        ))
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

    # Synchronisation AUTOMATIQUE locale <-> site en ligne (ordinateur uniquement) :
    # envoie la base au site après chaque opération de modification, récupère celle
    # du site toutes les minutes, et fusionne dans les deux sens (rien n'est écrasé).
    from app.autosync import after_request_hook, start_autosync
    if not os.environ.get('RENDER_EXTERNAL_URL'):
        app.after_request(after_request_hook)
    start_autosync(app)

    return app
