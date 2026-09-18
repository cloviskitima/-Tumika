"""
Synchronisation AUTOMATIQUE entre l'ordinateur (local) et le site en ligne.

Fonctionnement (côté ORDINATEUR uniquement, jamais sur le site hébergé) :
    - après chaque opération de modification (vente, stock, caisse, …), un envoi
      rapide de la base vers le site est déclenché (~2 s après l'action) ;
    - toutes les minutes, l'ordinateur envoie ses changements puis récupère la
      base du site et la fusionne (les données saisies en ligne reviennent sur
      l'ordinateur, les données locales partent en ligne — rien n'est écrasé).

Le trajet utilise les identifiants administrateur du site (config stockée dans
instance/github_backup.json, jamais publiée). Rien ne s'active si le mot de
passe du site n'est pas renseigné, et rien ne tourne sur le site hébergé.
"""
import logging
import os
import tempfile
import threading
import time

import requests

logger = logging.getLogger('tumika.autosync')

# Intervalle entre deux cycles complets (secondes ; 60 par défaut)
DEFAULT_INTERVAL = 60

_local = {'dirty': False, 'push_running': False, 'pull_running': False,
          'scheduled': False, 'enabled': None}
_push_lock = threading.Lock()
_pull_lock = threading.Lock()


def interval_seconds():
    try:
        return max(15, int(os.environ.get('LOCAL_SYNC_INTERVAL') or DEFAULT_INTERVAL))
    except ValueError:
        return DEFAULT_INTERVAL


def is_local():
    """La synchro locale <-> site ne tourne que sur l'ordinateur."""
    return not bool(os.environ.get('RENDER_EXTERNAL_URL'))


def _cfg(app=None):
    from app.routes.backup import _load_config
    if app is not None:
        with app.app_context():
            return _load_config()
    return _load_config()


def enabled(app=None):
    """Auto-sync activée : ordinateur + mot de passe du site renseigné + flag auto_web (défaut vrai)."""
    if not is_local():
        return False
    cfg = _cfg(app)
    if not cfg.get('site_password'):
        return False
    return bool(cfg.get('auto_web', True))


def _is_mutating():
    """Une requête API qui modifie des données ? (à la base du déclenchement auto)."""
    from flask import request
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return False
    path = request.path or ''
    if not path.startswith('/api/'):
        return False
    if path.startswith('/api/backup'):
        return False  # ne jamais se re-déclencher soi-même
    if path.startswith('/api/login') or path.startswith('/api/logout'):
        return False
    return True


def after_request_hook(response):
    """Enregistré après chaque requête : marque la base « à envoyer » et programme
    un envoi rapide dès qu'une opération modifie des données."""
    try:
        if is_local() and _is_mutating() and enabled():
            _local['dirty'] = True
            app = __import__('flask').current_app._get_current_object()
            if not _local.get('scheduled'):
                _local['scheduled'] = True
                t = threading.Timer(1.5, _run_scheduled_push, args=(app,))
                t.daemon = True
                t.start()
    except Exception as e:
        logger.debug('Hook de synchronisation ignoré : %s', e)
    return response


def _run_scheduled_push(app):
    try:
        push_now(app)
    except Exception:
        pass
    finally:
        _local['scheduled'] = False


def push_now(app=None):
    """Envoie la base de l'ordinateur vers le site (fusion en ligne, rien n'est écrasé)."""
    app = app or __import__('flask').current_app._get_current_object()
    if not enabled(app):
        return False
    with _push_lock:
        if _local.get('push_running'):
            return False
        _local['push_running'] = True
    try:
        with app.app_context():
            from app.routes.backup import _upload_to_site
            _upload_to_site(_cfg(app))
            _local['dirty'] = False
        logger.info('Synchronisation auto -> site envoyée.')
        return True
    except Exception as e:
        logger.warning('Envoi auto -> site échoué : %s', e)
        return False
    finally:
        with _push_lock:
            _local['push_running'] = False


def pull_now(app=None):
    """Télécharge la base du site et la fusionne dans la base de l'ordinateur."""
    app = app or __import__('flask').current_app._get_current_object()
    if not enabled(app):
        return False
    with _pull_lock:
        if _local.get('pull_running'):
            return False
        _local['pull_running'] = True
    fpath = None
    try:
        with app.app_context():
            from app.sync import apply_backup_file
            fpath = _download_from_site(_cfg(app))
            if fpath:
                apply_backup_file(fpath, app)
        logger.info('Synchronisation auto <- site fusionnée.')
        return True
    except Exception as e:
        logger.warning('Récupération auto <- site échouée : %s', e)
        return False
    finally:
        if fpath and os.path.exists(fpath):
            try:
                os.remove(fpath)
            except OSError:
                pass
        with _pull_lock:
            _local['pull_running'] = False


def _download_from_site(cfg):
    """Télécharge le fichier de la base actuelle du site (chemin temporaire, à supprimer)."""
    site_url = (cfg.get('site_url') or 'https://tumika.onrender.com').strip().rstrip('/')
    username = (cfg.get('site_username') or 'admin').strip()
    password = cfg.get('site_password') or ''
    if not password:
        raise RuntimeError('Mot de passe du site en ligne non renseigné (Réglages → Site en ligne).')

    session = requests.Session()
    try:
        r = session.post('{}/api/login'.format(site_url),
                         json={'email': username, 'password': password}, timeout=30)
        if r.status_code != 200 or not (r.json() or {}).get('success'):
            raise RuntimeError('Connexion au site en ligne refusée (identifiants incorrects ?).')
        r2 = session.get('{}/api/backup/download'.format(site_url), timeout=120)
    except requests.RequestException as e:
        raise RuntimeError('Site en ligne injoignable : {}'.format(e))
    if r2.status_code != 200:
        raise RuntimeError('Le site a refusé le téléchargement (code {}).'.format(r2.status_code))

    fd, path = tempfile.mkstemp(prefix='tumika_pull_', suffix='.db')
    with os.fdopen(fd, 'wb') as f:
        f.write(r2.content)
    return path


def _minute_loop(app):
    """Boucle de fond (une seule) : envoie les changements puis ramène ceux du site."""
    interval = interval_seconds()
    while True:
        time.sleep(interval)
        if not enabled(app):
            continue
        try:
            push_now(app)
        except Exception:
            pass
        try:
            pull_now(app)
        except Exception:
            pass


def start_autosync(app):
    """Démarre la boucle automatique (ordinateur uniquement). Inoffensif sinon."""
    if not enabled(app):
        logger.info('Synchronisation automatique locale <-> site inactive '
                    '(renseignez le mot de passe du site dans Réglages → Site en ligne pour l\'activer).')
        return
    if _local.get('enabled'):
        return
    _local['enabled'] = True
    t = threading.Thread(target=_minute_loop, args=(app,), daemon=True)
    t.start()
    logger.info('Synchronisation automatique locale <-> site démarrée (toutes les %s s).', interval_seconds())