"""
Application principale MotoStockIA
"""
import os
from app import create_app

app = create_app()

# Route racine
@app.route('/')
def index():
    from flask import session, redirect, url_for
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

# Tâche de fond : rapports quotidiens par email (file d'attente hors ligne)
from app.utils.rapports_email import demarrer_tache_rapports_email, flush_rapports

with app.app_context():
    try:
        flush_rapports(limite=10)
    except Exception:
        pass
demarrer_tache_rapports_email(app)

if __name__ == '__main__':
    # debug uniquement si FLASK_DEBUG=1 est défini explicitement (sécurité)
    debug = os.environ.get('FLASK_DEBUG') == '1'
    app.run(debug=debug, host='0.0.0.0', port=5000, use_reloader=debug)
