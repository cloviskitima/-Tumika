"""
Routes d'authentification
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from app.models.user import User
from app.models.login_log import LoginLog
from app import db

auth_bp = Blueprint('auth', __name__)


def record_login_log(user, success=True):
    """Enregistre une tentative de connexion dans le journal."""
    try:
        log = LoginLog(
            user_id=user.id if user else None,
            username=user.username if user else (request.form.get('username') or request.get_json(silent=True) or {}).get('username'),
            success=success,
            ip_address=_ip_client(),
            user_agent=(request.user_agent.string or '')[:255]
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


# ---- Protection brute-force (par IP) ----
from datetime import datetime, timedelta

MAX_ECHECS = 5
FENETRE_MINUTES = 10


def _ip_client():
    """Adresse IP du client (gère le proxy en prenant la 1ère valeur de X-Forwarded-For)."""
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or 'inconnu'


def _trop_d_echecs(ip):
    """Vrai si plus de MAX_ECHECS échecs récents depuis cette IP."""
    try:
        seuil = datetime.utcnow() - timedelta(minutes=FENETRE_MINUTES)
        nb = LoginLog.query.filter(
            LoginLog.ip_address == ip,
            LoginLog.success == False,  # noqa: E712
            LoginLog.created_at >= seuil
        ).count()
        return nb >= MAX_ECHECS
    except Exception:
        return False


def login_required(f):
    """Décorateur pour protéger les routes nécessitant une connexion"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter pour accéder à cette page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion"""
    if request.method == 'GET':
        return render_template('login.html')
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember')
        
        if not username or not password:
            flash('Veuillez remplir tous les champs.', 'error')
            return render_template('login.html')
        
        ip = _ip_client()
        if _trop_d_echecs(ip):
            flash(f'Trop de tentatives échouées. Réessayez dans {FENETRE_MINUTES} minutes.', 'error')
            return render_template('login.html')
        
        # Rechercher l'utilisateur par username ou email
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                record_login_log(user, success=False)
                flash('Votre compte est désactivé. Contactez l\'administrateur.', 'error')
                return render_template('login.html')
            
            # Créer la session
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            # Mettre à jour la dernière connexion
            user.update_last_login()
            record_login_log(user, success=True)
            
            flash('Connexion réussie!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            record_login_log(user, success=False)
            flash('Identifiants incorrects.', 'error')
            return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Déconnexion"""
    session.clear()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register')
def register():
    """Inscription publique désactivée (comptes créés par l'administrateur uniquement)."""
    return redirect(url_for('auth.login'))


@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    """API de connexion pour les requêtes AJAX"""
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs'}), 400
    
    ip = _ip_client()
    if _trop_d_echecs(ip):
        return jsonify({'success': False, 'message': f'Trop de tentatives échouées. Réessayez dans {FENETRE_MINUTES} minutes.'}), 429
    
    username = data.get('email')
    password = data.get('password')
    
    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()
    
    if user and user.check_password(password):
        if not user.is_active:
            record_login_log(user, success=False)
            return jsonify({'success': False, 'message': 'Votre compte est désactivé'}), 403
        
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        
        user.update_last_login()
        record_login_log(user, success=True)
        
        return jsonify({
            'success': True,
            'message': 'Connexion réussie',
            'user': user.to_dict()
        })
    else:
        record_login_log(user, success=False)
        return jsonify({'success': False, 'message': 'Identifiants incorrects'}), 401


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    """API de déconnexion"""
    session.clear()
    return jsonify({'success': True, 'message': 'Déconnexion réussie'})


@auth_bp.route('/api/user/current')
def get_current_user():
    """API pour obtenir l'utilisateur connecté"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Non connecté'}), 401
    
    user = User.query.get(session['user_id'])
    if user:
        return jsonify({'success': True, 'user': user.to_dict()})
    else:
        session.clear()
        return jsonify({'success': False, 'message': 'Utilisateur introuvable'}), 404
