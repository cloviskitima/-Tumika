"""
Synchronisation des données #TUMIKA : GitHub devient le pont entre le travail
local et le site hébergé (Render).

Flux attendu :
    1. Sur l'ordinateur, « Pousser la base de données vers GitHub » envoie une
       copie de motostock.db sur le dépôt de sauvegarde (backups/motostock.db).
    2. Sur le site en ligne, l'application vérifie GitHub à intervalle régulier
       (à chaque requête, mais limitée à un appel GitHub toutes les N secondes)
       et télécharge la base la plus récente.
    3. Si le fichier a changé, il est validé puis remplace la base SQLite locale
       du site : les données locales sont ainsi affichées sur le site à chaque
       nouvelle sauvegarde, sans manipulation manuelle.

Activation : réservée au site en ligne via la variable d'environnement
GITHUB_SYNC_ENABLED=1 (uniquement chez Render — jamais sur l'ordinateur local,
sinon la base locale serait écrasée par le contenu de GitHub).
"""
import base64
import json
import logging
import os
import sqlite3
import tempfile
import time
from datetime import datetime

import requests
from flask import current_app

BASE_URL = 'https://api.github.com'
DEFAULT_PATH = 'backups/motostock.db'

logger = logging.getLogger('tumika.sync')

# Limitation du nombre d'appels GitHub (à chaque requête mais au plus toutes les N secondes)
_THROTTLE = {'last': 0.0}


def _env(*keys):
    for k in keys:
        value = os.environ.get(k)
        if value:
            return value.strip()
    return ''


def get_config(app=None):
    """Configuration de synchronisation : variables d'environnement, sinon config locale tapée."""
    instance = (app or current_app).instance_path
    cfg = {}
    path = os.path.join(instance, 'github_backup.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f) or {}
        except Exception:
            cfg = {}

    env = {
        'token': _env('GITHUB_SYNC_TOKEN', 'GITHUB_BACKUP_TOKEN'),
        'owner': _env('GITHUB_SYNC_OWNER', 'GITHUB_BACKUP_OWNER'),
        'repo': _env('GITHUB_SYNC_REPO', 'GITHUB_BACKUP_REPO'),
        'branch': _env('GITHUB_SYNC_BRANCH', 'GITHUB_BACKUP_BRANCH'),
        'path': _env('GITHUB_SYNC_PATH', 'GITHUB_BACKUP_PATH'),
    }
    for key, value in env.items():
        if value:
            cfg[key] = value
    return cfg


def is_enabled(app=None):
    if os.environ.get('GITHUB_SYNC_ENABLED') != '1':
        return False
    cfg = get_config(app)
    return bool(cfg.get('token') and cfg.get('owner') and cfg.get('repo'))


def interval_seconds():
    try:
        return max(10, int(_env('GITHUB_SYNC_INTERVAL') or 30))
    except ValueError:
        return 30


def _load_state(instance):
    try:
        with open(os.path.join(instance, 'sync_state.json'), 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_state(instance, data):
    try:
        with open(os.path.join(instance, 'sync_state.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _headers(cfg):
    return {
        'Authorization': 'Bearer ' + (cfg.get('token') or ''),
        'Accept': 'application/vnd.github+json',
    }


def _latest_sha(cfg):
    """Dernier commit ayant modifié le fichier de sauvegarde (vérification légère)."""
    path = (cfg.get('path') or DEFAULT_PATH).strip().strip('/')
    url = '{}/repos/{}/{}/commits'.format(BASE_URL, cfg.get('owner'), cfg.get('repo'))
    try:
        r = requests.get(url, params={'path': path, 'per_page': '1'}, headers=_headers(cfg), timeout=20)
        if r.status_code == 200:
            items = r.json()
            if items:
                return items[0].get('sha')
    except (requests.RequestException, ValueError):
        pass
    return None


def _download(cfg, target):
    """Télécharge le fichier via l'API Contents ; retourne le sha du fichier (ou None)."""
    path = (cfg.get('path') or DEFAULT_PATH).strip().strip('/')
    branch = cfg.get('branch') or 'main'
    url = '{}/repos/{}/{}/contents/{}'.format(BASE_URL, cfg.get('owner'), cfg.get('repo'), path)
    try:
        r = requests.get(url, params={'ref': branch}, headers=_headers(cfg), timeout=60)
        if r.status_code != 200:
            logger.warning('Téléchargement GitHub refusé (code %s) pour %s', r.status_code, path)
            return None
        data = r.json()
        content = base64.b64decode(data.get('content') or '')
        with open(target, 'wb') as f:
            f.write(content)
        return data.get('sha')
    except (requests.RequestException, ValueError, KeyError, OSError) as e:
        logger.warning('Téléchargement GitHub impossible : %s', e)
        return None


def _validate(filepath):
    """Valide qu'il s'agit bien d'une base SQLite #TUMIKA exploitable."""
    try:
        uri = 'file:{}?mode=ro'.format(filepath.replace('\\', '/'))
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            integ = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if integ != 'ok':
                return False
            has_user = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user'"
            ).fetchone()
            return bool(has_user)
        finally:
            conn.close()
    except Exception:
        return False


def _live_db_path(app):
    """Chemin du fichier SQLite réellement utilisé par l'application (None si non-SQLite)."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    prefix = 'sqlite:///'
    if not uri.startswith(prefix):
        logger.warning('Synchronisation ignorée : base de données non-SQLite (%s)', uri.split(':', 1)[0])
        return None
    rel = uri[len(prefix):]
    if rel.startswith('/'):
        return rel
    return os.path.join(app.instance_path, rel)


def sync_status(app=None):
    """État de la synchronisation (affiché dans les paramètres)."""
    cfg = get_config(app)
    state = _load_state((app or current_app).instance_path)
    return {
        'sync_enabled': is_enabled(app),
        'configured': bool(cfg.get('token') and cfg.get('owner') and cfg.get('repo')),
        'owner': cfg.get('owner', ''),
        'repo': cfg.get('repo', ''),
        'path': cfg.get('path') or DEFAULT_PATH,
        'commit': state.get('sha'),
        'updated_at': state.get('updated_at'),
        'last_check_at': state.get('last_check_at'),
        'last_error': state.get('last_error'),
        'interval': interval_seconds(),
    }


def force_sync(app=None):
    """Télécharge la base de GitHub et remplace la base SQLite du site (retourne un statut)."""
    app = app or current_app
    if not is_enabled(app):
        return {'applied': False, 'reason': 'sync_desactive'}

    cfg = get_config(app)
    instance = app.instance_path
    state = _load_state(instance)
    now = datetime.now().isoformat(timespec='seconds')
    state['last_check_at'] = now

    sha = _latest_sha(cfg)
    if not sha:
        state['last_error'] = 'github_injoignable'
        _save_state(instance, state)
        return {'applied': False, 'reason': 'github_injoignable'}

    if sha == state.get('sha'):
        state.pop('last_error', None)
        _save_state(instance, state)
        return {'applied': False, 'reason': 'a_jour', 'commit': sha}

    tmp_fd, tmp_path = tempfile.mkstemp(prefix='tumika_sync_', suffix='.db')
    os.close(tmp_fd)
    try:
        file_sha = _download(cfg, tmp_path)
        if not file_sha or not os.path.getsize(tmp_path):
            state['last_error'] = 'telechargement_impossible'
            _save_state(instance, state)
            return {'applied': False, 'reason': 'telechargement_impossible'}

        if not _validate(tmp_path):
            state['last_error'] = 'fichier_invalide'
            _save_state(instance, state)
            return {'applied': False, 'reason': 'fichier_invalide'}

        live = _live_db_path(app)
        if not live:
            state['last_error'] = 'base_non_sqlite'
            _save_state(instance, state)
            return {'applied': False, 'reason': 'base_non_sqlite'}

        # Fermer les connexions SQLAlchemy (libère le fichier, requis notamment
        # sur Windows), puis remplacement atomique : au prochain accès, le
        # moteur rouvrira le nouveau fichier.
        from app import db
        try:
            with app.app_context():
                db.engine.dispose()
        except Exception:
            pass
        if os.path.exists(live):
            try:
                os.replace(live, live + '.pre-sync')
            except OSError:
                pass
        os.replace(tmp_path, live)

        state['sha'] = sha
        state['updated_at'] = now
        state.pop('last_error', None)
        _save_state(instance, state)
        logger.info('Synchronisation GitHub -> base locale effectuée (commit %s…)', sha[:12])
        return {'applied': True, 'commit': sha, 'updated_at': now}
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def sync_if_needed(force=False):
    """Point d'entrée appelé avant chaque requête : vérifie GitHub de façon limitée."""
    if not is_enabled():
        return
    try:
        now = time.time()
        if not force and (now - _THROTTLE['last']) < interval_seconds():
            return
        _THROTTLE['last'] = now
        force_sync()
    except Exception as e:  # ne doit jamais bloquer les requêtes du site
        logger.warning('Synchronisation ignorée (échec silencieux) : %s', e)