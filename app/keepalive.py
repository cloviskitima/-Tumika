"""
Anti-veille #TUMIKA
-------------------
Empêche l'instance d'être mise en veille par les hébergeurs gratuits
(Render free met l'instance en veille après ~15 min sans trafic).

Principe : un thread de fond s'auto-interroge via l'URL publique de
l'application toutes les KEEP_ALIVE_INTERVAL secondes (9 min par défaut).
Cette requête traverse l'équilibreur de charge, ce qui réinitialise le
compteur d'inactivité et maintient l'application éveillée en continu.

Variables d'environnement :
    ENABLE_KEEPALIVE=1           -> active la tâche (définie sur Render)
    KEEP_ALIVE_URL               -> URL publique (sinon RENDER_EXTERNAL_URL ou PUBLIC_URL)
    KEEP_ALIVE_INTERVAL          -> intervalle en secondes (défaut 540)
    KEEP_ALIVE_PATH              -> chemin interrogé (défaut /health)
"""
import os
import threading
import time
from urllib.request import urlopen

DEFAULT_INTERVAL = 540  # 9 minutes < 15 minutes d'inactivité de Render free


def _url_publique():
    return (os.environ.get('KEEP_ALIVE_URL')
            or os.environ.get('RENDER_EXTERNAL_URL')
            or os.environ.get('PUBLIC_URL') or '').strip().rstrip('/')


def _ping(url):
    try:
        req = urlopen(url, timeout=45)
        try:
            req.read()
        finally:
            req.close()
        return True
    except Exception:
        return False


def _boucle(app, url, interval, path):
    ping_url = url + path
    while True:
        time.sleep(interval)
        if not _ping(ping_url):
            app.logger.warning('Keep-alive : ping échoué vers %s', ping_url)


def start_keepalive(app):
    """Démarre la tâche anti-veille dans un thread de fond (si activée)."""
    if os.environ.get('ENABLE_KEEPALIVE') != '1':
        return
    url = _url_publique()
    if not url:
        app.logger.info('Keep-alive désactivé : aucune URL publique définie '
                        '(KEEP_ALIVE_URL / RENDER_EXTERNAL_URL / PUBLIC_URL).')
        return
    try:
        interval = max(30, int(os.environ.get('KEEP_ALIVE_INTERVAL', str(DEFAULT_INTERVAL))))
    except ValueError:
        interval = DEFAULT_INTERVAL
    path = os.environ.get('KEEP_ALIVE_PATH', '/health') or '/health'

    thread = threading.Thread(target=_boucle, args=(app, url, interval, path),
                              daemon=True, name='keepalive')
    thread.start()
    app.logger.info('Keep-alive actif : ping de %s toutes les %d s', url + path, interval)