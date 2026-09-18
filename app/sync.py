"""
Synchronisation des données #TUMIKA : GitHub devient le pont entre le travail
local et le site hébergé (Render).

Flux attendu :
    1. Sur l'ordinateur, « Pousser la base de données vers GitHub » envoie une
       copie de motostock.db sur le dépôt de sauvegarde (backups/motostock.db).
    2. Sur le site en ligne, l'application vérifie GitHub à intervalle régulier
       (à chaque requête, mais limitée à un appel GitHub toutes les N secondes)
       et télécharge la base la plus récente.
    3. Si le fichier a changé, il est validé puis fusionné dans la base SQLite
       du site (insérer / mettre à jour ligne par ligne, sans rien écraser) :
       les nouvelles données locales sont ainsi affichées sur le site.
    4. Alternative sans jeton GitHub : l'ordinateur envoie lui-même sa base au
       site en ligne via /api/backup/upload (même fusion, aucune configuration
       à faire sur Render).

Activation : uniquement sur le site en ligne. Sur Render (RENDER_EXTERNAL_URL
présent), la synchro s'active automatiquement dès que le dépôt de sauvegarde est
identifié (utilisateur + dépôt, valeurs par défaut intégrées au code). Aucun
jeton n'est requis lorsque le dépôt est public ; GITHUB_SYNC_TOKEN n'est
nécessaire que pour un dépôt privé. La variable GITHUB_SYNC_ENABLED=1 reste
disponible pour forcer l'activation. En local (jamais de RENDER_EXTERNAL_URL),
la synchro ne peut pas s'activer : la base locale ne peut pas être écrasée par
le contenu de GitHub.
"""
import base64
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime

import requests
from flask import current_app

BASE_URL = 'https://api.github.com'
DEFAULT_PATH = 'backups/motostock.db'
# Récupération sans jeton quand le dépôt de sauvegarde est public.
DEFAULT_OWNER = 'cloviskitima'
DEFAULT_REPO = '-Tumika-backup'

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

    # Valeurs par défaut : fonctionne sans AUCUNE configuration (dépôt public).
    cfg.setdefault('owner', DEFAULT_OWNER)
    cfg.setdefault('repo', DEFAULT_REPO)
    cfg.setdefault('branch', 'main')
    cfg.setdefault('path', DEFAULT_PATH)
    return cfg


def is_enabled(app=None):
    """Active la synchronisation sur le site en ligne.

    Sur Render (détecté via RENDER_EXTERNAL_URL), la synchro s'active dès que
    les identifiants du dépôt sont connus (utilisateur + dépôt) ; le token n'est
    nécessaire qu'en cas de dépôt privé. En local aucune activation n'est
    possible (jamais de RENDER_EXTERNAL_URL) : la base locale reste maîtresse.
    """
    on_render_hebergeur = bool(os.environ.get('RENDER_EXTERNAL_URL'))
    flag_demandee = os.environ.get('GITHUB_SYNC_ENABLED') == '1'
    if not (flag_demandee or on_render_hebergeur):
        return False
    cfg = get_config(app)
    return bool(cfg.get('owner') and cfg.get('repo'))


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
    token = (cfg.get('token') or '').strip()
    headers = {'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    return headers


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


def _copy_sqlite(src, dst):
    """Copie cohérente d'un fichier SQLite (API de sauvegarde SQLite)."""
    s = sqlite3.connect(src)
    d = sqlite3.connect(dst)
    try:
        with d:
            s.backup(d)
    finally:
        d.close()
        s.close()


def _table_list(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _table_info(conn, table):
    """Colonnes d'une table : (cid, nom, type, notnull, defaut, pk)."""
    return [tuple(r) for r in conn.execute('PRAGMA table_info("{}")'.format(table))]


def _apply_delta(delta_path, target_path):
    """Met à jour la MÊME base (target) à partir de la sauvegarde (delta).

    Au lieu d'écraser la base du site, chaque ligne de GitHub est insérée ou
    mise à jour par clé primaire dans la base existante : les données ajoutées
    directement en ligne sont conservées, les nouvelles données locales arrivent
    de GitHub, et le schéma est complété (nouvelles tables / colonnes).
    """
    tgt = sqlite3.connect(target_path, timeout=15)
    delta = sqlite3.connect(delta_path, timeout=15)
    try:
        tgt.execute('BEGIN')
        tgt_tables = set(_table_list(tgt))
        delta_tables = set(_table_list(delta))

        for table in sorted(delta_tables):
            create_sql = delta.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if table not in tgt_tables:
                if not create_sql or not create_sql[0]:
                    continue
                tgt.execute(create_sql[0])
                tgt_tables.add(table)

            dinfo = _table_info(delta, table)
            tinfo = _table_info(tgt, table)
            tgt_cols = {c[1]: c for c in tinfo}
            # Colonnes présentes dans la sauvegarde mais absentes de la base
            for c in dinfo:
                name = c[1]
                if name not in tgt_cols and c[2].upper() != 'INTEGER PRIMARY KEY':
                    tgt.execute('ALTER TABLE "{}" ADD COLUMN "{}" {}'.format(table, name, c[2]))

            cols = [c[1] for c in dinfo]
            col_idx = {name: i for i, name in enumerate(cols)}
            pks = [c[1] for c in dinfo if c[5] > 0]

            col_list = ', '.join('"{}"'.format(c) for c in cols)
            values_clause = ', '.join('?' * len(cols))

            if pks:
                pk_where = ' AND '.join('"{}"=?'.format(c) for c in pks)
                sel = 'SELECT 1 FROM "{}" WHERE {}'.format(table, pk_where)
                upd = 'UPDATE "{}" SET {} WHERE {}'.format(
                    table,
                    ', '.join('"{}"=?'.format(c) for c in cols if c not in pks),
                    pk_where)
            else:
                # Pas de clé primaire : la ligne entière sert de clé (pas de doublons)
                key_cols = cols
                key_where = ' AND '.join('"{}"=?'.format(c) for c in key_cols)
                sel = 'SELECT 1 FROM "{}" WHERE {}'.format(table, key_where)
                upd = None
            ins = 'INSERT INTO "{}" ({}) VALUES ({})'.format(table, col_list, values_clause)

            for row in delta.execute('SELECT * FROM "{}"'.format(table)):
                if pks:
                    key = tuple(row[col_idx[c]] for c in pks)
                    exists = tgt.execute(sel, key).fetchone()
                else:
                    key = tuple(row[col_idx[c]] for c in key_cols)
                    exists = tgt.execute(sel, key).fetchone()
                if exists:
                    if upd:
                        vals = [row[col_idx[c]] for c in cols if c not in pks] + list(key)
                        tgt.execute(upd, vals)
                else:
                    tgt.execute(ins, list(row))

            # Compteurs AUTOINCREMENT : aligner pour éviter toute collision de clés
            row = tgt.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                              (table,)).fetchone()
            if row and row[0] and 'AUTOINCREMENT' in (row[0] or '').upper():
                mx = tgt.execute('SELECT COALESCE(MAX(rowid), 0) FROM "{}"'.format(table)).fetchone()[0]
                tgt.execute('UPDATE sqlite_sequence SET seq=? WHERE name=?', (mx, table))

        if tgt.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('La base fusionnée est incohérente (integrite KO).')
        tgt.execute('COMMIT')
    except Exception:
        try:
            tgt.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        tgt.close()
        delta.close()


def sync_status(app=None):
    """État de la synchronisation (affiché dans les paramètres)."""
    cfg = get_config(app)
    state = _load_state((app or current_app).instance_path)
    return {
        'sync_enabled': is_enabled(app),
        'configured': bool(cfg.get('owner') and cfg.get('repo')),
        'owner': cfg.get('owner', ''),
        'repo': cfg.get('repo', ''),
        'path': cfg.get('path') or DEFAULT_PATH,
        'commit': state.get('sha'),
        'updated_at': state.get('updated_at'),
        'last_check_at': state.get('last_check_at'),
        'last_error': state.get('last_error'),
        'interval': interval_seconds(),
        'webhook': bool(os.environ.get('GITHUB_SYNC_WEBHOOK_SECRET')),
        'mode': 'fusion',
    }


def apply_backup_file(file_path, app=None):
    """Fusionne un fichier SQLite dans la base live du site.

    Rien n'est écrasé : les lignes du fichier sont insérées ou mises à jour par
    clé primaire dans la base existante (données du site conservées). Le résultat
    est vérifié puis écrit EN PLACE dans le fichier de la base (API de sauvegarde
    SQLite, sans renommage : fiable sous Windows, aucun verrou d'antivirus).
    Lève RuntimeError('base_non_sqlite'|'fichier_invalide'|'fichier_vide') en cas
    de problème. Idempotent : réappliquer le même fichier ne crée pas de doublons.
    """
    app = app or current_app
    live = _live_db_path(app)
    if not live:
        raise RuntimeError('base_non_sqlite')
    if not os.path.exists(file_path) or not os.path.getsize(file_path):
        raise RuntimeError('fichier_vide')
    if not _validate(file_path):
        raise RuntimeError('fichier_invalide')

    # Fichier fusionné temporaire, dans le même dossier que la base (VM Windows).
    base_dir = os.path.dirname(live) or tempfile.gettempdir()
    fd, merged_path = tempfile.mkstemp(prefix='tumika_merge_', suffix='.db', dir=base_dir)
    os.close(fd)
    try:
        # 1) Fusion : copie de la base actuelle + application des lignes du fichier
        if os.path.exists(live):
            _copy_sqlite(live, merged_path)
            _apply_delta(file_path, merged_path)
        else:
            shutil.copyfile(file_path, merged_path)

        # 2) Validation avant toute écriture
        if not _validate(merged_path):
            raise RuntimeError('fichier_invalide')

        # 3) Libérer les connexions SQLAlchemy (fichier non verrouillé)
        from app import db
        try:
            with app.app_context():
                db.engine.dispose()
        except Exception:
            pass

        # 4) Réserve de sécurité : copie de la base actuelle telle quelle
        if os.path.exists(live):
            try:
                shutil.copyfile(live, live + '.pre-sync')
            except OSError:
                pass

        # 5) Écriture en place du contenu fusionné (sans renommer le fichier)
        src = sqlite3.connect(merged_path)
        dst = sqlite3.connect(live)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    finally:
        if os.path.exists(merged_path):
            try:
                os.remove(merged_path)
            except OSError:
                pass


def force_sync(app=None):
    """Télécharge la base de GitHub et la fusionne dans la base du site (retourne un statut)."""
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

        try:
            apply_backup_file(tmp_path, app)
        except RuntimeError as e:
            reason = str(e) or 'fichier_invalide'
            state['last_error'] = reason
            _save_state(instance, state)
            return {'applied': False, 'reason': reason}

        state['sha'] = sha
        state['updated_at'] = now
        state.pop('last_error', None)
        _save_state(instance, state)
        logger.info('Synchronisation GitHub -> base locale : mise à jour fusionnée (commit %s…)', sha[:12])
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