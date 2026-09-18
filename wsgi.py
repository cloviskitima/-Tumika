"""
MotoStockIA #TUMIKA — Point d'entrée WSGI pour Gunicorn (hébergeurs : Render…)

Commande :
    gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120
"""
from app import create_app
from app.utils.rapports_email import demarrer_tache_rapports_email, flush_rapports

app = create_app()


@app.route('/')
def index():
    from flask import session, redirect, url_for
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


# Tâche de fond : rapports quotidiens par email (file d'attente hors ligne)
with app.app_context():
    try:
        flush_rapports(limite=10)
    except Exception:
        pass
demarrer_tache_rapports_email(app)