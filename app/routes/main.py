"""
Routes principales de l'application
"""
from flask import Blueprint, jsonify, render_template, request, session
from app.routes.auth import login_required, permission_required

main_bp = Blueprint('main', __name__)


@main_bp.route('/health')
def health():
    """Santé de l'application : utilisé par les hébergeurs (Render, UptimeRobot, cron…)"""
    return jsonify({'status': 'ok', 'service': 'MotoStockIA #TUMIKA'})


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Page du tableau de bord"""
    return render_template('dashboard.html')


@main_bp.route('/stock')
@login_required
@permission_required('stock', 'view')
def stock():
    """Page de gestion du stock"""
    return render_template('stock.html')


@main_bp.route('/ventes')
@login_required
@permission_required('sales', 'view')
def ventes():
    """Page de gestion des ventes"""
    return render_template('ventes.html')


@main_bp.route('/caisse')
@login_required
@permission_required('cash', 'view')
def caisse():
    """Page de gestion de caisse"""
    return render_template('caisse.html')


@main_bp.route('/rapports')
@login_required
@permission_required('reports', 'view')
def rapports():
    """Page des rapports (ventes, stock, crédits, connexions)"""
    return render_template('rapports.html')


@main_bp.route('/statistiques')
@login_required
@permission_required('reports', 'view')
def statistiques():
    """Page des statistiques globales de l'application"""
    return render_template('statistiques.html')


@main_bp.route('/comptabilite')
@login_required
@permission_required('reports', 'view')
def comptabilite():
    """Page de comptabilité : plan comptable congolais, journal, grand livre, balance, bilan"""
    return render_template('comptabilite.html')


@main_bp.route('/users')
@login_required
@permission_required('users', 'view')
def users():
    """Page de gestion des utilisateurs"""
    return render_template('users.html', current_user_id=session.get('user_id'))


@main_bp.route('/settings')
@login_required
@permission_required('settings', 'view')
def settings():
    """Page des paramètres"""
    return render_template('settings.html')


# =========================================================================
# MISE À JOUR DE L'APPLICATION (Paramètres → Mise à jour)
# =========================================================================

@main_bp.route('/settings/api/update/info')
@login_required
def update_info_api():
    """État actuel : dossier, écriture, nombre de fichiers, redémarrage auto."""
    from app.utils import self_update
    return jsonify({'status': 'success', **self_update.update_info()})


@main_bp.route('/settings/api/update/analyze', methods=['POST'])
@login_required
def update_analyze_api():
    """Analyse une liste {path, size} et renvoie nouveau/modifié/identique/ignoré."""
    from app.utils import self_update
    data = request.get_json(silent=True) or {}
    files = data.get('files') or []
    try:
        result = self_update.analyze_update(files)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    result['status'] = 'success'
    return jsonify(result)


@main_bp.route('/settings/api/update/apply', methods=['POST'])
@login_required
def update_apply_api():
    """Applique les fichiers reçus (multipart) en les remplaçant EN PLACE."""
    from app.utils import self_update
    files = []
    try:
        for key in request.files.keys():
            f = request.files[key]
            files.append((f.filename or '', f))
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    if not files:
        return jsonify({'status': 'error', 'message': 'Aucun fichier reçu.'}), 400
    result = self_update.apply_update(files)
    result['status'] = 'success'
    message = f"{len(result['applied'])} fichier(s) mis à jour en place."
    if result['ignored']:
        message += f" ({len(result['ignored'])} ignoré(s))"
    result['message'] = message
    return jsonify(result)


@main_bp.route('/settings/api/update/restart', methods=['POST'])
@login_required
def update_restart_api():
    """Demande le redémarrage de l'application pour appliquer la mise à jour."""
    from app.utils import self_update
    ok = self_update.schedule_restart()
    if ok:
        message = ("Mise à jour enregistrée. L'application redémarre "
                   "automatiquement dans quelques secondes…")
    else:
        message = ("Mise à jour enregistrée. Fermez puis relancez l'application "
                   "pour l'appliquer (redémarrage automatique indisponible ici).")
    return jsonify({'status': 'success', 'restart': ok, 'message': message})
