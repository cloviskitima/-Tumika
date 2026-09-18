"""
Sauvegarde de la base de données #TUMIKA vers GitHub.
La configuration (utilisateur, dépôt, token) est stockée dans
instance/github_backup.json (dossier instance ignoré par Git : jamais exposé).
"""
import json
import os
import base64
import shutil
import sqlite3
import tempfile
from datetime import datetime

import requests
from flask import Blueprint, request, jsonify, current_app

from app.routes.auth import permission_required

backup_bp = Blueprint('backup', __name__)

BASE_URL = 'https://api.github.com'


def _config_path():
    return os.path.join(current_app.instance_path, 'github_backup.json')


def _load_config():
    path = _config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(data):
    path = _config_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise RuntimeError('Impossible d\'écrire la configuration locale : {}'.format(e))


def _masked_status(cfg):
    token = cfg.get('token') or ''
    masked = ''
    if token:
        masked = (token[:4] + '••••' + token[-4:]) if len(token) > 8 else '••••••'
    return {
        'configured': bool(cfg.get('owner') and cfg.get('repo') and token),
        'owner': cfg.get('owner', ''),
        'repo': cfg.get('repo', ''),
        'branch': cfg.get('branch') or '',
        'path': cfg.get('path') or 'backups/motostock.db',
        'has_token': bool(token),
        'masked_token': masked,
        'last_backup_at': cfg.get('last_backup_at'),
        'last_status': cfg.get('last_status'),
        'last_error': cfg.get('last_error'),
    }


def _db_path():
    return os.path.join(current_app.instance_path, 'motostock.db')


def _build_snapshot():
    """Copie cohérente (SQLite backup) de la base dans un fichier temporaire."""
    db_path = _db_path()
    if not os.path.exists(db_path):
        raise RuntimeError('Fichier de base de données introuvable sur le disque.')
    tmpdir = tempfile.mkdtemp(prefix='tumika_bkp_')
    snapshot = os.path.join(tmpdir, 'motostock.db')
    try:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(snapshot)
        try:
            with dst:
                src.backup(dst)
        except Exception:
            # Base momentanément verrouillée : copie brute acceptable
            shutil.copyfile(db_path, snapshot)
        finally:
            dst.close()
            src.close()
    except Exception:
        shutil.copyfile(db_path, snapshot)
    return snapshot, tmpdir


def _extract_message(response):
    try:
        data = response.json()
        return str(data.get('message') or ('Erreur GitHub (code {})'.format(response.status_code)))
    except Exception:
        return (response.text or '')[:300] or 'Erreur GitHub (code {})'.format(response.status_code)


def _push_to_github(cfg):
    """Téléverse un instantané de la base via l'API Contents de GitHub."""
    token = (cfg.get('token') or '').strip()
    owner = (cfg.get('owner') or '').strip()
    repo = (cfg.get('repo') or '').strip()
    if not token or not owner or not repo:
        raise RuntimeError('Configuration GitHub incomplète : le nom d\'utilisateur, le dépôt et le token sont obligatoires.')

    repo_path = (cfg.get('path') or 'backups/motostock.db').strip().strip('/')
    headers = {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
    }

    # 1) Vérifier l'accès au dépôt et son token
    try:
        r = requests.get('{}/repos/{}/{}'.format(BASE_URL, owner, repo), headers=headers, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError('Impossible de joindre GitHub : {}'.format(e))
    if r.status_code == 401:
        raise RuntimeError('Token GitHub invalide ou expiré. Créez un nouveau token avec le scope « repo ».')
    if r.status_code == 404:
        raise RuntimeError('Dépôt introuvable. Vérifiez le nom d\'utilisateur et le nom du dépôt, et que le token a accès à ce dépôt.')
    if r.status_code != 200:
        raise RuntimeError('Erreur GitHub (code {}) : {}'.format(r.status_code, r.text[:200]))
    if r.status_code == 200:
        branch = cfg.get('branch') or r.json().get('default_branch') or 'main'
    else:
        branch = cfg.get('branch') or 'main'

    # 2) Instantané SQLite cohérent
    snapshot, tmpdir = _build_snapshot()
    try:
        with open(snapshot, 'rb') as f:
            content_b64 = base64.b64encode(f.read()).decode('ascii')
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    message = 'Sauvegarde base de données #TUMIKA {}'.format(datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
    url = '{}/repos/{}/{}/contents/{}'.format(BASE_URL, owner, repo, repo_path)

    # 3) Sha du fichier s'il existe déjà (nécessaire pour la mise à jour)
    sha = None
    try:
        r = requests.get(url, params={'ref': branch}, headers=headers, timeout=30)
        if r.status_code == 200:
            sha = r.json().get('sha')
    except requests.RequestException:
        pass

    payload = {'message': message, 'content': content_b64, 'branch': branch}
    if sha:
        payload['sha'] = sha

    try:
        r = requests.put(url, headers=headers, json=payload, timeout=120)
    except requests.RequestException as e:
        raise RuntimeError('Erreur réseau lors de l\'envoi vers GitHub : {}'.format(e))

    # 4) Conflit de concurrence : réessayer une fois avec le sha le plus récent
    if r.status_code == 422 and ('sha' in r.text.lower()):
        try:
            r2 = requests.get(url, params={'ref': branch}, headers=headers, timeout=30)
            if r2.status_code == 200:
                payload['sha'] = r2.json().get('sha')
                r = requests.put(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException:
            pass

    if r.status_code in (200, 201):
        data = r.json()
        return {
            'commit': (data.get('commit') or {}).get('sha'),
            'html_url': (data.get('content') or {}).get('html_url') or (data.get('commit') or {}).get('html_url'),
        }

    raise RuntimeError(_extract_message(r))


@backup_bp.route('/api/backup/status', methods=['GET'])
@permission_required('settings', 'update')
def backup_status():
    """État de la sauvegarde (sans jamais renvoyer le token)."""
    return jsonify({'success': True, **_masked_status(_load_config())})


@backup_bp.route('/api/backup/config', methods=['POST'])
@permission_required('settings', 'update')
def backup_config():
    """Enregistre la configuration de sauvegarde GitHub."""
    data = request.get_json(silent=True) or {}
    cfg = _load_config()

    if 'owner' in data and data.get('owner') is not None:
        cfg['owner'] = str(data['owner']).strip()
    if 'repo' in data and data.get('repo') is not None:
        cfg['repo'] = str(data['repo']).strip()
    if 'branch' in data and data.get('branch') is not None:
        cfg['branch'] = str(data['branch']).strip() or 'main'
    if 'path' in data and data.get('path') is not None:
        cfg['path'] = str(data['path']).strip() or 'backups/motostock.db'
    token = str(data.get('token') or '').strip()
    if token:
        cfg['token'] = token

    if not cfg.get('owner') or not cfg.get('repo'):
        return jsonify({'success': False, 'message': 'Le nom d\'utilisateur GitHub et le dépôt sont obligatoires.'}), 400

    try:
        _save_config(cfg)
    except RuntimeError as e:
        return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': True, 'message': 'Configuration sauvegardée avec succès', **_masked_status(cfg)})


@backup_bp.route('/api/backup/push', methods=['POST'])
@permission_required('settings', 'update')
def backup_push():
    """Pousse la base de données vers GitHub."""
    cfg = _load_config()
    now = datetime.now().isoformat(timespec='seconds')

    if not cfg.get('token') or not cfg.get('owner') or not cfg.get('repo'):
        return jsonify({'success': False, 'message': 'Veuillez d\'abord enregistrer la configuration GitHub (utilisateur, dépôt, token).'}), 400

    try:
        result = _push_to_github(cfg)
    except Exception as e:
        cfg['last_backup_at'] = now
        cfg['last_status'] = 'error'
        cfg['last_error'] = str(e)
        try:
            _save_config(cfg)
        except RuntimeError:
            pass
        return jsonify({
            'success': False,
            'message': 'La sauvegarde vers GitHub a échoué. Vous pouvez réessayer.',
            'error': str(e),
            'last_backup_at': now,
            'last_status': 'error',
        }), 500

    cfg['last_backup_at'] = now
    cfg['last_status'] = 'ok'
    cfg.pop('last_error', None)
    try:
        _save_config(cfg)
    except RuntimeError:
        pass

    return jsonify({
        'success': True,
        'message': 'Base de données poussée sur GitHub avec succès',
        'commit': result.get('commit'),
        'html_url': result.get('html_url'),
        'last_backup_at': now,
        'last_status': 'ok',
    })