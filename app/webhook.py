"""
Webhook GitHub -> Render : lorsqu'une sauvegarde est poussée sur GitHub,
Render s'actualise immédiatement (sans attendre la prochaine vérification).

Réglage côté GitHub (dépôt -Tumika-backup) :
    Settings -> Webhooks -> Add webhook
    - Payload URL : https://<votre-url>/webhook/github-sync
    - Content type : application/json
    - Secret : la valeur de GITHUB_SYNC_WEBHOOK_SECRET
    - Events : « Just the push event » (optionnellement aussi « Issues »)

La requête est vérifiée par signature HMAC-SHA256 (X-Hub-Signature-256),
comme effectué par GitHub, pour empêcher toute activation malveillante.
"""
import hashlib
import hmac
import os

from flask import Blueprint, request, jsonify

webhook_bp = Blueprint('webhook', __name__)


@webhook_bp.route('/webhook/github-sync', methods=['POST'])
def github_sync_hook():
    secret = os.environ.get('GITHUB_SYNC_WEBHOOK_SECRET')
    if not secret:
        return jsonify({'success': False, 'message': 'Webhook non configuré.'}), 404

    event = request.headers.get('X-GitHub-Event', '')
    if event == 'ping':
        # GitHub sonde le webhook à sa création
        return jsonify({'success': True, 'event': 'ping'})

    if event != 'push':
        # Événement non pertinent : répondre OK pour ne pas bloquer GitHub
        return jsonify({'success': False, 'message': 'Événement non géré.'}), 200

    payload = request.get_data(cache=False)
    provided = request.headers.get('X-Hub-Signature-256', '')
    mac = 'sha256=' + hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    if not provided or not hmac.compare_digest(mac, provided):
        return jsonify({'success': False, 'message': 'Signature invalide.'}), 401

    from app.sync import force_sync, sync_status
    try:
        result = force_sync()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'sync_status': sync_status()}), 500

    message = ('Base de données mise à jour depuis GitHub (webhook).' if result.get('applied')
               else 'Rien à mettre à jour (base déjà à jour).')
    return jsonify({'success': True, 'message': message, 'sync': result, 'sync_status': sync_status()})