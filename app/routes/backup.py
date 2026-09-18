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
        'site_url': cfg.get('site_url') or 'https://tumika.onrender.com',
        'site_username': cfg.get('site_username') or 'admin',
        'has_site_password': bool(cfg.get('site_password')),
        'auto_site': bool(cfg.get('auto_site')),
        'auto_web': bool(cfg.get('auto_web', True)),
        'last_site_upload_at': cfg.get('last_site_upload_at'),
        'last_site_status': cfg.get('last_site_status'),
        'last_site_error': cfg.get('last_site_error'),
        'last_site_pull_at': cfg.get('last_site_pull_at'),
        'last_site_pull_status': cfg.get('last_site_pull_status'),
        'last_site_pull_error': cfg.get('last_site_pull_error'),
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


def _upload_to_site(cfg):
    """Envoie directement un instantané de la base vers le site en ligne.

    Contrairement au trajet GitHub -> Render, cette méthode ne requiert AUCUN
    jeton sur le site : l'ordinateur se connecte au site (compte administrateur)
    puis téléverse la base, que le site fusionne dans sa base (rien n'est écrasé).
    """
    site_url = (cfg.get('site_url') or 'https://tumika.onrender.com').strip().rstrip('/')
    username = (cfg.get('site_username') or 'admin').strip()
    password = cfg.get('site_password') or ''
    if not password:
        raise RuntimeError('Mot de passe du site en ligne non renseigné (Réglages → Site en ligne).')

    session = requests.Session()
    try:
        r = session.post('{}/api/login'.format(site_url),
                         json={'email': username, 'password': password}, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError('Impossible de joindre le site en ligne ({}). Vérifiez l\'adresse : {}'.format(site_url, e))
    try:
        data = r.json()
        if r.status_code != 200 or not data.get('success'):
            raise RuntimeError('Connexion au site en ligne refusée (identifiants incorrects ?).')
    except (ValueError, KeyError):
        raise RuntimeError('Réponse inattendue du site en ligne (code {}).'.format(r.status_code))

    snapshot, tmpdir = _build_snapshot()
    try:
        try:
            with open(snapshot, 'rb') as f:
                r2 = session.post('{}/api/backup/upload'.format(site_url),
                                  files={'db': ('motostock.db', f, 'application/octet-stream')}, timeout=120)
        except requests.RequestException as e:
            raise RuntimeError('Erreur réseau lors de l\'envoi au site en ligne : {}'.format(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    try:
        d2 = r2.json()
    except Exception:
        d2 = {}
    if r2.status_code != 200 or not d2.get('success'):
        raise RuntimeError(str(d2.get('message') or 'Le site a refusé le fichier (code {}).'.format(r2.status_code)))
    return {'sync': d2.get('sync')}


@backup_bp.route('/api/backup/status', methods=['GET'])
@permission_required('settings', 'update')
def backup_status():
    """État de la sauvegarde (sans jamais renvoyer le token) et de la synchronisation."""
    from app.sync import sync_status
    return jsonify({
        'success': True,
        **_masked_status(_load_config()),
        'sync': sync_status(),
    })


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

    if 'site_url' in data and data.get('site_url') is not None:
        cfg['site_url'] = str(data['site_url']).strip().rstrip('/') or 'https://tumika.onrender.com'
    if 'site_username' in data and data.get('site_username') is not None:
        cfg['site_username'] = str(data['site_username']).strip() or 'admin'
    if 'site_password' in data and data.get('site_password') is not None:
        cfg['site_password'] = str(data['site_password'])
    if 'auto_site' in data and data.get('auto_site') is not None:
        cfg['auto_site'] = bool(data['auto_site'])
    if 'auto_web' in data and data.get('auto_web') is not None:
        cfg['auto_web'] = bool(data['auto_web'])

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

    # Envoi automatique au site en ligne (si activé) — ne bloque pas la sauvegarde
    site_result = None
    if cfg.get('auto_site'):
        try:
            site_result = _upload_to_site(cfg)
            cfg['last_site_upload_at'] = now
            cfg['last_site_status'] = 'ok'
            cfg.pop('last_site_error', None)
        except Exception as e:
            cfg['last_site_status'] = 'error'
            cfg['last_site_error'] = str(e)

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
        'site_upload': site_result,
        'last_site_upload_at': cfg.get('last_site_upload_at'),
        'last_site_status': cfg.get('last_site_status'),
        'last_site_error': cfg.get('last_site_error'),
    })


@backup_bp.route('/api/backup/push-site', methods=['POST'])
@permission_required('settings', 'update')
def backup_push_site():
    """Côté ordinateur : envoie la base directement au site en ligne (aucun jeton requis)."""
    cfg = _load_config()
    now = datetime.now().isoformat(timespec='seconds')
    try:
        result = _upload_to_site(cfg)
    except Exception as e:
        cfg['last_site_upload_at'] = now
        cfg['last_site_status'] = 'error'
        cfg['last_site_error'] = str(e)
        try:
            _save_config(cfg)
        except RuntimeError:
            pass
        return jsonify({
            'success': False,
            'message': 'L\'envoi au site en ligne a échoué. Vous pouvez réessayer.',
            'error': str(e),
            'last_site_upload_at': now,
            'last_site_status': 'error',
        }), 500

    cfg['last_site_upload_at'] = now
    cfg['last_site_status'] = 'ok'
    cfg.pop('last_site_error', None)
    try:
        _save_config(cfg)
    except RuntimeError:
        pass

    return jsonify({
        'success': True,
        'message': 'Base de données envoyée au site en ligne et fusionnée avec succès',
        '@': 'site',
        'last_site_upload_at': now,
        'last_site_status': 'ok',
        'sync': result.get('sync'),
    })


@backup_bp.route('/api/backup/upload', methods=['POST'])
@permission_required('settings', 'update')
def backup_upload():
    """Côté site en ligne : reçoit la base envoyée par l'ordinateur et la fusionne.

    Le fichier reçu est fusionné dans la base existante du site (insérer / mettre
    à jour ligne par ligne) : les données saisies directement en ligne sont
    conservées, les données de l'ordinateur arrivent sans rien écraser.
    """
    from app.sync import apply_backup_file, sync_status
    f = request.files.get('db')
    if not f or not f.filename:
        return jsonify({'success': False, 'message': 'Aucun fichier reçu.'}), 400

    tmpdir = tempfile.mkdtemp(prefix='tumika_upload_')
    try:
        fpath = os.path.join(tmpdir, 'upload.db')
        f.save(fpath)
        apply_backup_file(fpath)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'sync': sync_status()}), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return jsonify({'success': True, 'message': 'Base fusionnée sur le site en ligne avec succès.', 'sync': sync_status()})


@backup_bp.route('/api/backup/pull-site', methods=['POST'])
@permission_required('settings', 'update')
def backup_pull_site():
    """Côté ordinateur : récupère la base du site en ligne et la fusionne dans la base locale."""
    from app.autosync import _download_from_site
    from app.sync import apply_backup_file, sync_status
    cfg = _load_config()
    now = datetime.now().isoformat(timespec='seconds')
    fpath = None
    try:
        fpath = _download_from_site(cfg)
        apply_backup_file(fpath)
    except Exception as e:
        cfg['last_site_pull_at'] = now
        cfg['last_site_pull_status'] = 'error'
        cfg['last_site_pull_error'] = str(e)
        try:
            _save_config(cfg)
        except RuntimeError:
            pass
        return jsonify({
            'success': False,
            'message': 'La récupération depuis le site a échoué. Vous pouvez réessayer.',
            'error': str(e),
            'last_site_pull_at': now,
            'last_site_pull_status': 'error',
            'sync': sync_status(),
        }), 500
    finally:
        if fpath and os.path.exists(fpath):
            try:
                os.remove(fpath)
            except OSError:
                pass

    cfg['last_site_pull_at'] = now
    cfg['last_site_pull_status'] = 'ok'
    cfg.pop('last_site_pull_error', None)
    try:
        _save_config(cfg)
    except RuntimeError:
        pass

    return jsonify({
        'success': True,
        'message': 'Base récupérée depuis le site et fusionnée sur l\'ordinateur avec succès',
        'last_site_pull_at': now,
        'last_site_pull_status': 'ok',
        'sync': sync_status(),
    })


@backup_bp.route('/api/backup/download', methods=['GET'])
@permission_required('settings', 'update')
def backup_download():
    """Côté site en ligne : télécharge la base actuelle (pour la fusion côté ordinateur)."""
    from flask import after_this_request, send_file
    snapshot, tmpdir = _build_snapshot()

    @after_this_request
    def _cleanup(response):
        shutil.rmtree(tmpdir, ignore_errors=True)
        return response

    return send_file(snapshot, as_attachment=True, download_name='motostock.db',
                     mimetype='application/octet-stream')


@backup_bp.route('/api/backup/sync', methods=['POST'])
@permission_required('settings', 'update')
def backup_sync_now():
    """Déclenche immédiatement la synchronisation depuis GitHub (site en ligne).

    Récupère la base poussée depuis l'ordinateur et remplace la base locale
    du site afin d'afficher les données à jour.
    """
    from app.sync import force_sync, sync_status
    try:
        result = force_sync()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'sync': sync_status()}), 500

    applied = bool(result.get('applied'))
    message = ('Base de données synchronisée depuis GitHub avec succès.' if applied
               else {'a_jour': 'Base déjà à jour (aucun changement depuis la dernière synchronisation).',
                     'sync_desactive': 'Synchronisation désactivée sur cette installation.',
                     'github_injoignable': 'GitHub injoignable pour le moment. Réessayez plus tard.',
                     'telechargement_impossible': 'Impossible de télécharger la base depuis GitHub.',
                     'fichier_invalide': 'Le fichier téléchargé depuis GitHub est invalide.',
                     'base_non_sqlite': 'Synchronisation non supportée avec cette base de données.'}.get(
                         result.get('reason'), 'Rien à synchroniser.'))
    return jsonify({'success': applied, 'message': message, **result, 'sync': sync_status()})