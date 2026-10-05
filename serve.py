"""
MotoStockIA #TUMIKA — Serveur de production (Waitress).
Lance l'application sur http://localhost:5000 (localhost = contexte sécurisé,
ce qui permet à la caméra / getUserMedia de fonctionner).

Usage :
    python serve.py
"""
import os
import socket
import sys
import threading
import time
import webbrowser

from app import create_app
from app.utils.rapports_email import demarrer_tache_rapports_email, flush_rapports

HOST = '127.0.0.1'
PORT = int(os.environ.get('MOTOSTOCK_PORT', '5000'))
URL = 'http://localhost:%d/' % PORT

app = create_app()


@app.route('/')
def index():
    from flask import session, redirect, url_for
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


with app.app_context():
    try:
        flush_rapports(limite=10)
    except Exception:
        pass
demarrer_tache_rapports_email(app)


def _port_occupe(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, port)) == 0


def _ouvrir_navigateur():
    try:
        webbrowser.open(URL)
    except Exception:
        pass


if __name__ == '__main__':
    # Quand l'application est relancée par une mise à jour, l'ancien processus
    # peut mettre une seconde ou deux à libérer le port. On attend au lieu
    # d'abandonner : c'est ce qui faisait échouer le redémarrage automatique.
    try:
        ATTENTE_PORT = int(os.environ.get('MOTOSTOCK_WAIT_PORT', '0'))
    except (TypeError, ValueError):
        ATTENTE_PORT = 0

    if _port_occupe(PORT):
        if ATTENTE_PORT > 0:
            print('Port %d encore occupé, attente de sa libération (%d s)...' % (PORT, ATTENTE_PORT))
            limite = time.time() + ATTENTE_PORT
            while time.time() < limite and _port_occupe(PORT):
                time.sleep(0.5)
        if _port_occupe(PORT):
            print('MotoStockIA est déjà en cours d\'exécution sur %s' % URL)
            _ouvrir_navigateur()
            sys.exit(0)

    print('=' * 52)
    print('  MotoStockIA #TUMIKA  —  Serveur Waitress')
    print('  Application : %s' % URL)
    print('  (Fermez cette fenêtre pour arrêter le serveur)')
    print('=' * 52)

    threading.Timer(2.0, _ouvrir_navigateur).start()

    from waitress import serve
    serve(app, host=HOST, port=PORT, threads=8, channel_timeout=60)
