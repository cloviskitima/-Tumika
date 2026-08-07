"""
Routes principales de l'application
"""
from flask import Blueprint, render_template, session, redirect, url_for
from app.routes.auth import login_required

main_bp = Blueprint('main', __name__)


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Page du tableau de bord"""
    return render_template('dashboard.html')


@main_bp.route('/stock')
@login_required
def stock():
    """Page de gestion du stock"""
    return render_template('stock.html')


@main_bp.route('/ventes')
@login_required
def ventes():
    """Page de gestion des ventes"""
    return render_template('ventes.html')


@main_bp.route('/caisse')
@login_required
def caisse():
    """Page de gestion de caisse"""
    return render_template('caisse.html')


@main_bp.route('/rapports')
@login_required
def rapports():
    """Page des rapports (ventes, stock, crédits, connexions)"""
    return render_template('rapports.html')


@main_bp.route('/statistiques')
@login_required
def statistiques():
    """Page des statistiques globales de l'application"""
    return render_template('statistiques.html')


@main_bp.route('/comptabilite')
@login_required
def comptabilite():
    """Page de comptabilité : plan comptable congolais, journal, grand livre, balance, bilan"""
    return render_template('comptabilite.html')


@main_bp.route('/users')
@login_required
def users():
    """Page de gestion des utilisateurs"""
    return render_template('users.html', current_user_id=session.get('user_id'))


@main_bp.route('/settings')
@login_required
def settings():
    """Page des paramètres"""
    return render_template('settings.html')
