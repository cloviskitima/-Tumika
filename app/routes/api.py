"""
Routes API pour l'application
"""
from flask import Blueprint, request, jsonify, current_app, session, Response
import json
from app.models.user import User
from app.models.produit import Produit
from app.models.notification import Notification
from app.models.taux_change import TauxChange
from app.models.vente import Vente, ProduitVendu
from app.models.caisse import CaisseMovement
from app.models.login_log import LoginLog
from app.models.comptabilite import CompteComptable, EcritureComptable
from app.models.parametre import Parametre, get_param, set_param, all_params
from app.models.identification import ProduitSignature, CorrectionIdentification
from app.models.reapprovisionnement import Reapprovisionnement
from app.models.activite_stock import ActiviteStock
from app.vision.identification import analyser_image, identifier_par_texte, identifier_par_code
from app.utils.qr_generator import generate_qr_png_bytes, generate_barcode_png_bytes
from app.utils.comptabilite import (
    seed_plan_comptable,
    synchroniser_compta,
    generation_vente,
    generation_paiement_credit,
    generation_caisse,
    maj_ecriture_vente,
    soldes_par_compte,
)
from app import db
import os
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime, timedelta, date
from sqlalchemy import func, or_

api_bp = Blueprint('api', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


@api_bp.before_request
def proteger_api():
    """Exige une session authentifiée sur tous les endpoints /api/*."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Non connecté'}), 401

def allowed_file(filename):
    """Vérifie si l'extension du fichier est autorisée"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _valider_contenu_image(data):
    """Vérifie que le contenu est bien une image décodable (PIL)."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        img.verify()
        return True
    except Exception:
        return False


@api_bp.route('/qrcode')
def api_qrcode():
    """Génère un QR code PNG réel contenant les données fournies (ex : référence)."""
    data = request.args.get('data', '')
    if not data:
        return jsonify({'success': False, 'message': 'Donnée manquante'}), 400
    try:
        size = min(max(int(request.args.get('size', 300)), 100), 800)
    except (TypeError, ValueError):
        size = 300
    return Response(generate_qr_png_bytes(data, size), mimetype='image/png')


@api_bp.route('/barcode')
def api_barcode():
    """Génère un code-barres PNG réel contenant le code fourni (ex : code-barres produit)."""
    data = request.args.get('data', '')
    if not data:
        return jsonify({'success': False, 'message': 'Donnée manquante'}), 400
    return Response(generate_barcode_png_bytes(data), mimetype='image/png')


def enregistrer_image(file, upload_folder):
    """Valide (extension + contenu) et enregistre une image uploadée.
    Retourne l'URL relative ou None si le fichier est invalide."""
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        return None
    data = file.read()
    if not data or len(data) > current_app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024):
        return None
    if not _valider_contenu_image(data):
        return None
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join(upload_folder, unique_filename)
    with open(file_path, 'wb') as f:
        f.write(data)
    return f"/static/uploads/{unique_filename}"


def get_exchange_rate(source, target, operation_date=None):
    """Retourne le taux de change le plus récent valide pour une date d'opération."""
    src = normalize_devise(source)
    tgt = normalize_devise(target)
    if src == tgt:
        return 1.0

    query = TauxChange.query.filter_by(devise_source=source, devise_cible=target)
    if operation_date:
        query = query.filter(TauxChange.effective_date <= operation_date)
    taux = query.order_by(TauxChange.effective_date.desc()).first()
    if taux and taux.taux:
        return float(taux.taux)

    inverse_query = TauxChange.query.filter_by(devise_source=target, devise_cible=source)
    if operation_date:
        inverse_query = inverse_query.filter(TauxChange.effective_date <= operation_date)
    inverse = inverse_query.order_by(TauxChange.effective_date.desc()).first()
    if inverse and inverse.taux:
        return 1.0 / float(inverse.taux)

    if src == 'USD' and tgt in ['CDF', 'FC', 'XAF']:
        return 2800.0
    if src in ['CDF', 'FC', 'XAF'] and tgt == 'USD':
        return 1.0 / 2800.0

    return 1.0



def normalize_devise(devise):
    """Normalise la devise (USD ou CDF/FC)."""
    if not devise:
        return 'USD'
    d = str(devise).upper().strip()
    if d in ['FC', 'CDF', 'XAF']:
        return 'CDF'
    if d in ['USD', '$']:
        return 'USD'
    return d


def get_caisse_balance(devise='USD'):
    """Retourne le solde courant de caisse pour une devise donnée."""
    norm_devise = normalize_devise(devise)
    devise_list = ['CDF', 'FC', 'XAF'] if norm_devise == 'CDF' else ['USD']

    total_in = db.session.query(func.coalesce(func.sum(CaisseMovement.montant), 0)).filter(
        CaisseMovement.type == 'in',
        CaisseMovement.devise.in_(devise_list)
    ).scalar() or 0
    total_out = db.session.query(func.coalesce(func.sum(CaisseMovement.montant), 0)).filter(
        CaisseMovement.type == 'out',
        CaisseMovement.devise.in_(devise_list)
    ).scalar() or 0
    return total_in - total_out


def enregistrer_activite_stock(produit_id, type_activite, quantite_avant, quantite_apres,
                               description='', user_id=None):
    """Ajoute une ligne au journal des activités de stock (historique produit)."""
    variation = (quantite_apres or 0) - (quantite_avant or 0)
    db.session.add(ActiviteStock(
        produit_id=produit_id,
        type=type_activite,
        quantite_avant=quantite_avant or 0,
        quantite_apres=quantite_apres or 0,
        variation=variation,
        description=description[:255],
        user_id=user_id or session.get('user_id')
    ))



@api_bp.route('/produits', methods=['GET'])
def get_produits():
    """Récupère la liste des produits avec filtres"""
    search = request.args.get('search', '')
    categorie = request.args.get('categorie', '')
    stock_status = request.args.get('stock_status', '')
    
    query = Produit.query
    
    if search:
        query = query.filter(
            (Produit.nom.ilike(f'%{search}%')) |
            (Produit.reference.ilike(f'%{search}%')) |
            (Produit.code_barres.ilike(f'%{search}%'))
        )
    
    if categorie:
        query = query.filter(Produit.categorie == categorie)
    
    if stock_status:
        if stock_status == 'low':
            query = query.filter(Produit.quantite <= Produit.stock_min)
        elif stock_status == 'out':
            query = query.filter(Produit.quantite == 0)
        elif stock_status == 'available':
            query = query.filter(Produit.quantite > Produit.stock_min)
    
    produits = query.all()
    
    return jsonify({
        'success': True,
        'produits': [p.to_dict() for p in produits]
    })

@api_bp.route('/produits/<int:id>', methods=['GET'])
def get_produit(id):
    """Récupère un produit par son ID"""
    produit = Produit.query.get_or_404(id)
    return jsonify({
        'success': True,
        'produit': produit.to_dict()
    })

@api_bp.route('/produits', methods=['POST'])
def create_produit():
    """Crée un nouveau produit ou met à jour un produit existant"""
    try:
        data = request.form
        
        # Vérifier si un produit avec les mêmes détails existe déjà
        nom = data.get('nom')
        categorie = data.get('categorie')
        fournisseur = data.get('fournisseur')
        prix_achat = float(data.get('prix_achat', 0))
        prix_vente = float(data.get('prix_vente', 0))
        
        produit_existant = Produit.query.filter(
            Produit.nom == nom,
            Produit.categorie == categorie,
            Produit.fournisseur == fournisseur,
            Produit.prix_achat == prix_achat,
            Produit.prix_vente == prix_vente
        ).first()
        
        if produit_existant:
            # Mettre à jour le produit existant
            quantite_additionnelle = int(data.get('quantite', 0))
            qty_avant = produit_existant.quantite
            produit_existant.quantite += quantite_additionnelle
            if quantite_additionnelle:
                enregistrer_activite_stock(
                    produit_existant.id, 'reapprovisionnement', qty_avant, produit_existant.quantite,
                    f"Produit existant : ajout de +{quantite_additionnelle} unités en stock"
                )
            
            # Mettre à jour les images si de nouvelles sont fournies
            upload_folder = current_app.config['UPLOAD_FOLDER']
            url_1 = enregistrer_image(request.files.get('image_1'), upload_folder)
            if url_1:
                produit_existant.image_url_1 = url_1
            url_2 = enregistrer_image(request.files.get('image_2'), upload_folder)
            if url_2:
                produit_existant.image_url_2 = url_2
            
        db.session.commit()
        
        # Journaliser la modification (focalisée sur le changement de stock)
        desc = f"Modification du produit"
        if produit.quantite != qty_avant:
            desc += f" — stock {qty_avant} → {produit.quantite}"
        enregistrer_activite_stock(
            produit.id, 'modification', qty_avant, produit.quantite, desc
        )
        db.session.commit()
        
        from app.vision import dataset as dataset_vision
        try:
            dataset_vision.mettre_a_jour_signatures_produit(produit, current_app.config['UPLOAD_FOLDER'])
        except Exception:
            pass
            
            return jsonify({
                'success': True,
                'message': 'Produit existant mis à jour avec succès',
                'produit': produit_existant.to_dict(),
                'existant': True
            }), 200
        
        # Créer un nouveau produit
        reference = data.get('reference')
        code_barres = data.get('code_barres')
        
        produit = Produit(
            nom=nom,
            categorie=categorie,
            fournisseur=fournisseur,
            prix_achat=prix_achat,
            prix_vente=prix_vente,
            devise=data.get('devise', 'XAF'),
            quantite=int(data.get('quantite', 0)),
            stock_min=int(data.get('stock_min', 5)),
            compatibilites=data.get('compatibilites')
        )
        
        # Génération automatique des codes si non fournis
        if not reference or not code_barres:
            produit.generer_codes_automatiques()
        else:
            produit.reference = reference
            produit.code_barres = code_barres
        
        # Gestion des images en local
        upload_folder = current_app.config['UPLOAD_FOLDER']
        url_1 = enregistrer_image(request.files.get('image_1'), upload_folder)
        if url_1:
            produit.image_url_1 = url_1
        url_2 = enregistrer_image(request.files.get('image_2'), upload_folder)
        if url_2:
            produit.image_url_2 = url_2
        
        db.session.add(produit)
        db.session.commit()
        enregistrer_activite_stock(
            produit.id, 'creation', 0, produit.quantite,
            f"Création du produit avec {produit.quantite} unité(s) en stock"
        )
        db.session.commit()
        
        from app.vision import dataset as dataset_vision
        try:
            dataset_vision.mettre_a_jour_signatures_produit(produit, current_app.config['UPLOAD_FOLDER'])
        except Exception:
            pass
        
        return jsonify({
            'success': True,
            'message': 'Produit créé avec succès',
            'produit': produit.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }), 400

@api_bp.route('/produits/<int:id>', methods=['PUT'])
def update_produit(id):
    """Met à jour un produit"""
    try:
        produit = Produit.query.get_or_404(id)
        data = request.form
        
        qty_avant = produit.quantite
        produit.nom = data.get('nom', produit.nom)
        produit.categorie = data.get('categorie', produit.categorie)
        produit.fournisseur = data.get('fournisseur', produit.fournisseur)
        produit.prix_achat = float(data.get('prix_achat', produit.prix_achat))
        produit.prix_vente = float(data.get('prix_vente', produit.prix_vente))
        produit.devise = data.get('devise', produit.devise)
        produit.quantite = int(data.get('quantite', produit.quantite))
        produit.stock_min = int(data.get('stock_min', produit.stock_min))
        produit.compatibilites = data.get('compatibilites', produit.compatibilites)
        
        # Gestion des images
        upload_folder = current_app.config['UPLOAD_FOLDER']
        url_1 = enregistrer_image(request.files.get('image_1'), upload_folder)
        if url_1:
            produit.image_url_1 = url_1
        url_2 = enregistrer_image(request.files.get('image_2'), upload_folder)
        if url_2:
            produit.image_url_2 = url_2
        
        db.session.commit()
        
        from app.vision import dataset as dataset_vision
        try:
            dataset_vision.mettre_a_jour_signatures_produit(produit, current_app.config['UPLOAD_FOLDER'])
        except Exception:
            pass
        
        return jsonify({
            'success': True,
            'message': 'Produit mis à jour avec succès',
            'produit': produit.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors de la mise à jour: {str(e)}'
        }), 400

@api_bp.route('/produits/<int:id>', methods=['DELETE'])
def delete_produit(id):
    """Supprime un produit"""
    try:
        produit = Produit.query.get_or_404(id)
        
        # Supprimer les fichiers images
        if produit.image_url_1:
            try:
                file_path = os.path.join(current_app.root_path, produit.image_url_1.lstrip('/'))
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
        
        if produit.image_url_2:
            try:
                file_path = os.path.join(current_app.root_path, produit.image_url_2.lstrip('/'))
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
        
        # Nettoyage du dataset et des corrections liés
        try:
            ProduitSignature.query.filter_by(produit_id=produit.id).delete()
            CorrectionIdentification.query.filter_by(produit_id=produit.id).delete()
        except Exception:
            pass
        
        # Journaliser la suppression avant de supprimer le produit
        enregistrer_activite_stock(
            produit.id, 'suppression', produit.quantite, 0,
            f"Suppression du produit (il restait {produit.quantite} unité(s))"
        )
        db.session.delete(produit)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Produit supprimé avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }), 400

@api_bp.route('/ventes', methods=['GET'])
def get_sales():
    """Récupère la liste des ventes"""
    try:
        search = request.args.get('search', '').strip()
        date_filter = request.args.get('date_filter', '')
        status_filter = request.args.get('status_filter', '')

        query = Vente.query

        if search:
            query = query.filter(
                or_(
                    Vente.client.ilike(f'%{search}%'),
                    Vente.telephone.ilike(f'%{search}%')
                )
            )

        if status_filter:
            query = query.filter(Vente.statut == status_filter)

        if date_filter == 'today':
            today = datetime.utcnow().date()
            query = query.filter(func.date(Vente.date) == today)
        elif date_filter == 'week':
            today = datetime.utcnow().date()
            week_start = today - timedelta(days=today.weekday())
            query = query.filter(func.date(Vente.date) >= week_start)
        elif date_filter == 'month':
            today = datetime.utcnow().date()
            query = query.filter(func.strftime('%Y-%m', Vente.date) == today.strftime('%Y-%m'))

        ventes = query.order_by(Vente.date.desc()).all()
        return jsonify({
            'success': True,
            'ventes': [v.to_dict() for v in ventes]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/ventes/<int:id>', methods=['GET'])
def get_sale(id):
    """Récupère une vente par son ID"""
    try:
        vente = Vente.query.get_or_404(id)
        return jsonify({
            'success': True,
            'vente': vente.to_dict()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 404

@api_bp.route('/ventes/<int:id>', methods=['PUT'])
def update_sale(id):
    """Modifie une vente et ajuste le stock et les mouvements de caisse en conséquence"""
    try:
        vente = Vente.query.get_or_404(id)

        if vente.statut == 'cancelled':
            return jsonify({'success': False, 'message': 'Impossible de modifier une vente annulée'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Données manquantes'}), 400

        new_produits_data = data.get('produits', [])
        if not new_produits_data:
            return jsonify({'success': False, 'message': 'Aucun produit fourni'}), 400

        new_montant = float(data.get('montant', vente.montant))
        if new_montant <= 0:
            return jsonify({'success': False, 'message': 'Montant invalide'}), 400

        # ─── 1. Construire un dict des anciennes quantités ───
        old_quantities = {}  # {produit_id: (ProduitVendu_obj, quantite_ancienne)}
        for pv in vente.produits_vendus:
            old_quantities[pv.produit_id] = pv

        # ─── 2. Construire un dict des nouvelles quantités demandées ───
        new_quantities = {}  # {produit_id: quantite_nouvelle}
        for item in new_produits_data:
            pid = int(item.get('id'))
            qty = int(item.get('quantite', 0))
            if qty > 0:
                new_quantities[pid] = qty

        # ─── 3. Calculer les deltas et vérifier les stocks ───
        # Produits qui augmentent ou sont nouveaux → besoin de stock supplémentaire
        for pid, new_qty in new_quantities.items():
            old_pv = old_quantities.get(pid)
            old_qty = old_pv.quantite if old_pv else 0
            delta = new_qty - old_qty  # positif = on retire plus du stock
            if delta > 0:
                produit = Produit.query.get_or_404(pid)
                if produit.quantite < delta:
                    return jsonify({
                        'success': False,
                        'message': f'Stock insuffisant pour {produit.nom} (besoin: {delta}, disponible: {produit.quantite})'
                    }), 400

        # ─── 4. Appliquer les deltas de stock ───
        # a) Produits supprimés de la vente → remettre tout en stock
        for pid, old_pv in old_quantities.items():
            if pid not in new_quantities:
                if old_pv.produit:
                    old_pv.produit.quantite += old_pv.quantite
                db.session.delete(old_pv)

        # b) Produits existants et nouveaux → ajuster delta
        for pid, new_qty in new_quantities.items():
            old_pv = old_quantities.get(pid)
            produit = Produit.query.get_or_404(pid)
            if old_pv:
                delta = new_qty - old_pv.quantite
                produit.quantite -= delta  # négatif = retour en stock, positif = sortie stock
                old_pv.quantite = new_qty
                old_pv.prix_vente = produit.prix_vente
                old_pv.prix_achat = produit.prix_achat
            else:
                # Nouveau produit ajouté à la vente
                produit.quantite -= new_qty
                new_pv = ProduitVendu(
                    vente=vente,
                    produit=produit,
                    quantite=new_qty,
                    prix_vente=produit.prix_vente,
                    prix_achat=produit.prix_achat
                )
                db.session.add(new_pv)

        # ─── 5. Mettre à jour les infos de la vente ───
        old_montant = vente.montant
        vente.client = data.get('client', vente.client)
        vente.telephone = data.get('telephone', vente.telephone)
        vente.montant = new_montant

        # ─── 6. Mettre à jour le mouvement de caisse lié (si paiement cash/completed) ───
        if vente.statut == 'completed' and vente.mode_paiement != 'credit':
            caisse_mvt = CaisseMovement.query.filter_by(vente_id=vente.id).first()
            if caisse_mvt:
                diff_montant = new_montant - old_montant
                caisse_mvt.montant = new_montant
                caisse_mvt.solde_apres = caisse_mvt.solde_apres + diff_montant
                caisse_mvt.libelle = f'Vente #{vente.id} (modifiée)'

        maj_ecriture_vente(vente)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Vente modifiée avec succès, stock et caisse mis à jour'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400


# ==================== API Rapports ====================

def get_report_date_range(periode):
    """Retourne la date de début selon la période demandée."""
    today = datetime.utcnow().date()
    if periode == 'today':
        return today, today
    elif periode == 'week':
        week_start = today - timedelta(days=today.weekday())
        return week_start, today
    elif periode == 'month':
        month_start = today.replace(day=1)
        return month_start, today
    elif periode == 'year':
        year_start = today.replace(month=1, day=1)
        return year_start, today
    return None, None


@api_bp.route('/rapports/ventes', methods=['GET'])
def get_sales_report():
    """Rapport détaillé des ventes avec synthèse et filtre par période"""
    try:
        periode = request.args.get('periode', 'all')
        date_start, date_end = get_report_date_range(periode)

        query = Vente.query
        if date_start:
            query = query.filter(func.date(Vente.date) >= date_start, func.date(Vente.date) <= date_end)

        ventes = query.order_by(Vente.date.desc()).all()
        taux_cdf = get_exchange_rate('USD', 'CDF') or 2800.0

        total_ventes = len(ventes)
        total_ventes_completed = sum(1 for v in ventes if v.statut == 'completed')
        total_credits = sum(1 for v in ventes if v.statut == 'pending' or v.mode_paiement == 'credit')

        chiffre_cdf = 0.0
        chiffre_usd = 0.0
        for v in ventes:
            dev = normalize_devise(v.devise)
            m = v.montant or 0.0
            if dev == 'USD':
                chiffre_usd += m
                chiffre_cdf += m * (v.taux_change or taux_cdf)
            else:
                chiffre_cdf += m
                chiffre_usd += m / taux_cdf if taux_cdf else 0.0

        ventes_list = []
        for v in ventes:
            item = v.to_dict()
            item['devise_norm'] = normalize_devise(v.devise)
            item['nom_vendeur'] = None
            if v.user_id:
                u = User.query.get(v.user_id)
                if u:
                    item['nom_vendeur'] = u.nom_complet or u.username
            ventes_list.append(item)

        return jsonify({
            'success': True,
            'periode': periode,
            'total_ventes': total_ventes,
            'total_ventes_completed': total_ventes_completed,
            'total_credits': total_credits,
            'chiffre_affaires_cdf': round(chiffre_cdf, 2),
            'chiffre_affaires_usd': round(chiffre_usd, 2),
            'taux_change': taux_cdf,
            'ventes': ventes_list
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/rapports/stock', methods=['GET'])
def get_stock_report():
    """Rapport détaillé du stock par produit"""
    try:
        produits = Produit.query.order_by(Produit.categorie, Produit.nom).all()
        taux_cdf = get_exchange_rate('USD', 'CDF') or 2800.0

        total_produits = len(produits)
        stock_faible = 0
        stock_epuise = 0
        stock_disponible = 0
        quantite_totale = 0
        valeur_stock_cdf = 0.0
        valeur_stock_usd = 0.0
        valeur_vente_cdf = 0.0
        valeur_vente_usd = 0.0

        produits_list = []
        for p in produits:
            dev = normalize_devise(p.devise)
            qty = p.quantite or 0
            quantite_totale += qty

            if p.quantite == 0:
                statut = 'epuise'
                stock_epuise += 1
            elif p.quantite <= p.stock_min:
                statut = 'faible'
                stock_faible += 1
            else:
                statut = 'disponible'
                stock_disponible += 1

            val_cost_native = (p.prix_achat or 0.0) * qty
            val_sale_native = (p.prix_vente or 0.0) * qty
            if dev == 'USD':
                val_cost_cdf = val_cost_native * taux_cdf
                val_cost_usd = val_cost_native
                val_sale_cdf = val_sale_native * taux_cdf
                val_sale_usd = val_sale_native
            else:
                val_cost_cdf = val_cost_native
                val_cost_usd = val_cost_native / taux_cdf if taux_cdf else 0.0
                val_sale_cdf = val_sale_native
                val_sale_usd = val_sale_native / taux_cdf if taux_cdf else 0.0

            valeur_stock_cdf += val_cost_cdf
            valeur_stock_usd += val_cost_usd
            valeur_vente_cdf += val_sale_cdf
            valeur_vente_usd += val_sale_usd

            produits_list.append({
                'id': p.id,
                'nom': p.nom,
                'reference': p.reference,
                'categorie': p.categorie or 'Non classé',
                'fournisseur': p.fournisseur,
                'devise': dev,
                'prix_achat': p.prix_achat,
                'prix_vente': p.prix_vente,
                'quantite': p.quantite,
                'stock_min': p.stock_min,
                'statut': statut,
                'valeur_stock_cdf': round(val_cost_cdf, 2),
                'valeur_stock_usd': round(val_cost_usd, 2)
            })

        return jsonify({
            'success': True,
            'total_produits': total_produits,
            'quantite_totale': quantite_totale,
            'stock_disponible': stock_disponible,
            'stock_faible': stock_faible,
            'stock_epuise': stock_epuise,
            'valeur_stock_cdf': round(valeur_stock_cdf, 2),
            'valeur_stock_usd': round(valeur_stock_usd, 2),
            'valeur_vente_cdf': round(valeur_vente_cdf, 2),
            'valeur_vente_usd': round(valeur_vente_usd, 2),
            'taux_change': taux_cdf,
            'produits': produits_list
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/rapports/credits', methods=['GET'])
def get_credits_report():
    """Rapport des ventes à crédit (en attente de paiement)"""
    try:
        periode = request.args.get('periode', 'all')
        date_start, date_end = get_report_date_range(periode)

        query = Vente.query.filter(
            (Vente.statut == 'pending') | (Vente.mode_paiement == 'credit')
        )
        if date_start:
            query = query.filter(func.date(Vente.date) >= date_start, func.date(Vente.date) <= date_end)

        credits = query.order_by(Vente.date.desc()).all()
        taux_cdf = get_exchange_rate('USD', 'CDF') or 2800.0

        total_credits = len(credits)
        montant_total_cdf = 0.0
        montant_total_usd = 0.0

        credits_list = []
        for v in credits:
            dev = normalize_devise(v.devise)
            m = v.montant or 0.0
            if dev == 'USD':
                montant_total_usd += m
                montant_total_cdf += m * (v.taux_change or taux_cdf)
            else:
                montant_total_cdf += m
                montant_total_usd += m / taux_cdf if taux_cdf else 0.0

            item = v.to_dict()
            item['devise_norm'] = dev
            item['jours_retard'] = (datetime.utcnow().date() - (v.date_echeance.date() if v.date_echeance else v.date.date())).days if (v.date_echeance or v.date) else 0
            credits_list.append(item)

        credits_list.sort(key=lambda x: x['jours_retard'], reverse=True)

        return jsonify({
            'success': True,
            'periode': periode,
            'total_credits': total_credits,
            'montant_total_cdf': round(montant_total_cdf, 2),
            'montant_total_usd': round(montant_total_usd, 2),
            'taux_change': taux_cdf,
            'credits': credits_list
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/rapports/connexions', methods=['GET'])
def get_connexions_report():
    """Rapport des connexions au système"""
    try:
        periode = request.args.get('periode', 'all')
        date_start, date_end = get_report_date_range(periode)

        query = LoginLog.query
        if date_start:
            query = query.filter(func.date(LoginLog.created_at) >= date_start, func.date(LoginLog.created_at) <= date_end)

        logs = query.order_by(LoginLog.created_at.desc()).limit(500).all()

        total_connexions = len(logs)
        reussies = sum(1 for l in logs if l.success)
        echouees = total_connexions - reussies
        utilisateurs_uniques = len({l.username for l in logs if l.username})

        return jsonify({
            'success': True,
            'periode': periode,
            'total_connexions': total_connexions,
            'reussies': reussies,
            'echouees': echouees,
            'utilisateurs_uniques': utilisateurs_uniques,
            'logs': [l.to_dict() for l in logs]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


def _plage_periode_etendue(periode):
    """Retourne (date_start, date_end, nb_jours) pour toute période y compris 2 semaines et semestre."""
    today = datetime.utcnow().date()
    if periode == 'today':
        return today, today, 1
    elif periode == 'week':
        return today - timedelta(days=today.weekday()), today, 7
    elif periode == '2weeks':
        return today - timedelta(days=13), today, 14
    elif periode == 'month':
        return today.replace(day=1), today, 30
    elif periode == 'semester':
        return today - timedelta(days=182), today, 182
    elif periode == 'year':
        return today.replace(month=1, day=1), today, 365
    return None, None, 0


def _cumul_devises(montant, devise, taux_cdf, taux_vente=None):
    """Convertit un montant en équivalents CDF et USD."""
    dev = normalize_devise(devise)
    if dev == 'USD':
        taux = taux_vente or taux_cdf
        return montant * taux, montant
    else:
        return montant, (montant / taux_cdf if taux_cdf else 0.0)


@api_bp.route('/rapports/complet', methods=['GET'])
def get_full_report():
    """Rapport complet d'activité (propriétaire) :
    CA, bénéfices, évolution, top produits, rotation stock, dettes et clients.
    Filtres : today, week, 2weeks, month, semester, year, all.
    """
    try:
        periode = request.args.get('periode', 'month')
        date_start, date_end, nb_jours = _plage_periode_etendue(periode)
        taux_cdf = get_exchange_rate('USD', 'CDF') or 2800.0

        # Ventes de la période
        query = Vente.query
        if date_start:
            query = query.filter(func.date(Vente.date) >= date_start, func.date(Vente.date) <= date_end)
        ventes = query.order_by(Vente.date.asc()).all()
        ventes_ids = [v.id for v in ventes]

        # ── Chiffre d'affaires & bénéfices ──
        ca_cdf = 0.0
        ca_usd = 0.0
        benefice_cdf = 0.0
        benefice_usd = 0.0
        cout_cdf = 0.0
        cout_usd = 0.0
        nb_ventes = len(ventes)
        nb_payees = sum(1 for v in ventes if v.statut == 'completed' and v.mode_paiement != 'credit')
        nb_credits = sum(1 for v in ventes if v.statut == 'pending' or v.mode_paiement == 'credit')

        # Détail des produits vendus sur la période (bénéfice par ligne)
        detail_produits = {}   # produit_id -> {qte, revenu_cdf, revenu_usd, cout_cdf, cout_usd, nom, ...}
        ventes_par_mode = {}
        montants_journaliers = {}  # date -> {'cdf':, 'usd':, 'count':}

        for v in ventes:
            dev = normalize_devise(v.devise)
            m = v.montant or 0.0
            cdf_part, usd_part = _cumul_devises(m, dev, taux_cdf, v.taux_change)
            ca_cdf += cdf_part
            ca_usd += usd_part

            mode = v.mode_paiement or 'cash'
            ventes_par_mode[mode] = ventes_par_mode.get(mode, 0) + 1

            jour = v.date.strftime('%Y-%m-%d') if v.date else None
            if jour:
                j = montants_journaliers.setdefault(jour, {'cdf': 0.0, 'usd': 0.0, 'count': 0})
                j['cdf'] += cdf_part
                j['usd'] += usd_part
                j['count'] += 1

            for pv in v.produits_vendus:
                qte = pv.quantite or 0
                prix_vente = pv.prix_vente or 0.0
                prix_achat = pv.prix_achat
                if prix_achat is None and pv.produit:
                    prix_achat = pv.produit.prix_achat
                prix_achat = prix_achat or 0.0

                # prix_vente / prix_achat d'une ligne sont exprimés dans la devise du produit.
                # On convertit revenu et coût depuis la devise du produit pour une marge cohérente.
                dev_prod = normalize_devise(pv.produit.devise) if pv.produit else 'USD'
                rev_cdf, rev_usd = _cumul_devises(prix_vente * qte, dev_prod, taux_cdf, v.taux_change)
                cst_cdf, cst_usd = _cumul_devises(prix_achat * qte, dev_prod, taux_cdf, v.taux_change)

                pid = pv.produit_id
                d = detail_produits.setdefault(pid, {
                    'qte': 0, 'revenu_cdf': 0.0, 'revenu_usd': 0.0,
                    'cout_cdf': 0.0, 'cout_usd': 0.0, 'nb_ventes': 0
                })
                d['qte'] += qte
                d['revenu_cdf'] += rev_cdf
                d['revenu_usd'] += rev_usd
                d['cout_cdf'] += cst_cdf
                d['cout_usd'] += cst_usd
                d['nb_ventes'] += 1
                cout_cdf += cst_cdf
                cout_usd += cst_usd

        benefice_cdf = ca_cdf - cout_cdf
        benefice_usd = ca_usd - cout_usd

        # ── Évolution (par jour, ou par mois si longue période) ──
        evolution = []
        if nb_jours and nb_jours <= 31:
            cur = date_start
            jours_fr = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
            mois_fr = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
            while cur <= date_end:
                key = cur.strftime('%Y-%m-%d')
                j = montants_journaliers.get(key, {'cdf': 0.0, 'usd': 0.0, 'count': 0})
                evolution.append({
                    'label': f"{jours_fr[cur.weekday()]} {cur.day} {mois_fr[cur.month-1]}",
                    'cdf': round(j['cdf'], 2),
                    'usd': round(j['usd'], 2),
                    'count': j['count']
                })
                cur += timedelta(days=1)
        else:
            # Regroupement par mois
            mois_grp = {}
            for jour, j in montants_journaliers.items():
                cle = jour[:7]
                g = mois_grp.setdefault(cle, {'cdf': 0.0, 'usd': 0.0, 'count': 0})
                g['cdf'] += j['cdf']
                g['usd'] += j['usd']
                g['count'] += j['count']
            mois_fr = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
            for cle in sorted(mois_grp.keys()):
                g = mois_grp[cle]
                y, mm = int(cle[:4]), int(cle[5:7])
                evolution.append({
                    'label': f"{mois_fr[mm-1]} {y}",
                    'cdf': round(g['cdf'], 2),
                    'usd': round(g['usd'], 2),
                    'count': g['count']
                })

        # ── Top produits vendus / peu demandés / rotation ──
        produits = Produit.query.all()
        produits_by_id = {p.id: p for p in produits}

        liste_top = []
        for pid, d in detail_produits.items():
            p = produits_by_id.get(pid)
            liste_top.append({
                'id': pid,
                'nom': p.nom if p else 'Produit supprimé',
                'reference': p.reference if p else '',
                'categorie': p.categorie if p else '',
                'qte': d['qte'],
                'revenu_cdf': round(d['revenu_cdf'], 2),
                'revenu_usd': round(d['revenu_usd'], 2),
                'cout_cdf': round(d['cout_cdf'], 2),
                'cout_usd': round(d['cout_usd'], 2),
                'benefice_cdf': round(d['revenu_cdf'] - d['cout_cdf'], 2),
                'benefice_usd': round(d['revenu_usd'] - d['cout_usd'], 2),
                'nb_ventes': d['nb_ventes']
            })
        liste_top.sort(key=lambda x: x['qte'], reverse=True)
        top_produits = liste_top[:10]

        # Produits peu demandés : vendus mais en bas du classement, OU en stock avec zéro vente
        produits_peu = [x for x in liste_top if x['qte'] > 0][-10:]
        produits_peu.reverse()
        if not produits_peu:
            produits_peu = [{
                'id': p.id, 'nom': p.nom, 'reference': p.reference, 'categorie': p.categorie,
                'qte': 0, 'revenu_cdf': 0.0, 'revenu_usd': 0.0,
                'cout_cdf': 0.0, 'cout_usd': 0.0, 'benefice_cdf': 0.0, 'benefice_usd': 0.0,
                'nb_ventes': 0
            } for p in produits if (p.quantite or 0) > 0][:10]

        # Rotation stock : quantités vendues vs stock actuel
        rotation = []
        for p in produits:
            d = detail_produits.get(p.id)
            qte_vendue = d['qte'] if d else 0
            stock_actuel = p.quantite or 0
            rotation.append({
                'id': p.id,
                'nom': p.nom,
                'reference': p.reference,
                'categorie': p.categorie or 'Non classé',
                'stock': stock_actuel,
                'vendu_periode': qte_vendue,
                'rotation': round(qte_vendue / stock_actuel, 2) if stock_actuel > 0 else (0.0 if qte_vendue == 0 else 99.99),
                'statut': p.statut
            })
        rotation.sort(key=lambda x: x['vendu_periode'], reverse=True)

        # ── Dettes / crédits ──
        credits = [v for v in ventes if v.statut == 'pending' or v.mode_paiement == 'credit']
        dettes_cdf = 0.0
        dettes_usd = 0.0
        dettes_par_client = {}
        dettes_en_retard = 0
        aujourdhui = datetime.utcnow().date()
        for v in credits:
            dev = normalize_devise(v.devise)
            cdf_part, usd_part = _cumul_devises(v.montant or 0.0, dev, taux_cdf, v.taux_change)
            dettes_cdf += cdf_part
            dettes_usd += usd_part
            client = (v.client or '').strip() or 'Client comptant'
            dc = dettes_par_client.setdefault(client, {
                'client': client, 'telephone': v.telephone, 'montant_cdf': 0.0,
                'montant_usd': 0.0, 'nb_credits': 0, 'jours_retard_max': 0, 'echeance': None
            })
            if v.telephone:
                dc['telephone'] = v.telephone
            dc['montant_cdf'] += cdf_part
            dc['montant_usd'] += usd_part
            dc['nb_credits'] += 1
            eche = v.date_echeance.date() if v.date_echeance else (v.date.date() if v.date else None)
            if eche:
                retard = (aujourdhui - eche).days
                if retard > dc['jours_retard_max']:
                    dc['jours_retard_max'] = retard
                if eche < aujourdhui:
                    dettes_en_retard += 1
                if dc['echeance'] is None or eche > dc['echeance']:
                    dc['echeance'] = eche
        dettes_clients = sorted(
            dettes_par_client.values(),
            key=lambda x: x['montant_usd'],
            reverse=True
        )

        # ── Clients : nouveaux, réguliers, top ──
        ventes_par_client = {}
        for v in ventes:
            client = (v.client or '').strip() or 'Client comptant'
            dev = normalize_devise(v.devise)
            cdf_part, usd_part = _cumul_devises(v.montant or 0.0, dev, taux_cdf, v.taux_change)
            c = ventes_par_client.setdefault(client, {
                'client': client, 'telephone': v.telephone, 'nb_ventes': 0,
                'ca_cdf': 0.0, 'ca_usd': 0.0, 'premiere_vente': v.date
            })
            if v.telephone:
                c['telephone'] = v.telephone
            c['nb_ventes'] += 1
            c['ca_cdf'] += cdf_part
            c['ca_usd'] += usd_part
            if c['premiere_vente'] is None or (v.date and v.date < c['premiere_vente']):
                c['premiere_vente'] = v.date

        clients_list = list(ventes_par_client.values())

        # Nouveaux clients : première vente de TOUJOURS dans la période
        nouveaux = 0
        for c in clients_list:
            avant = Vente.query.filter(
                Vente.client == c['client'],
                func.date(Vente.date) < (date_start or aujourdhui.replace(year=2000))
            ).count()
            if avant == 0:
                nouveaux += 1

        clients_reguliers = [c for c in clients_list if c['nb_ventes'] >= 2]
        top_clients = sorted(clients_list, key=lambda x: x['ca_usd'], reverse=True)[:10]
        top_clients = [{
            'client': c['client'],
            'telephone': c['telephone'],
            'nb_ventes': c['nb_ventes'],
            'ca_cdf': round(c['ca_cdf'], 2),
            'ca_usd': round(c['ca_usd'], 2),
            'premiere_vente': c['premiere_vente'].isoformat() if c['premiere_vente'] else None
        } for c in top_clients]

        # Dettes par client : enrichir avec jours retard max
        dettes_clients = [{
            'client': d['client'],
            'telephone': d['telephone'],
            'montant_cdf': round(d['montant_cdf'], 2),
            'montant_usd': round(d['montant_usd'], 2),
            'nb_credits': d['nb_credits'],
            'jours_retard_max': d['jours_retard_max'],
            'echeance': d['echeance'].isoformat() if d['echeance'] else None,
            'statut': 'Retard' if d['jours_retard_max'] > 0 else 'En cours'
        } for d in dettes_clients]

        # ── CAPITAL / ACTIFS (valeur cumulée de l'entreprise) ──
        # Stock actuel au prix d'achat et au prix de vente
        capital_stock_achat_cdf = 0.0
        capital_stock_achat_usd = 0.0
        capital_stock_vente_cdf = 0.0
        capital_stock_vente_usd = 0.0
        for p in produits:
            devp = normalize_devise(p.devise)
            qty = p.quantite or 0
            val_a = (p.prix_achat or 0.0) * qty
            val_v = (p.prix_vente or 0.0) * qty
            ca_achat, usd_achat = _cumul_devises(val_a, devp, taux_cdf)
            ca_vente, usd_vente = _cumul_devises(val_v, devp, taux_cdf)
            capital_stock_achat_cdf += ca_achat
            capital_stock_achat_usd += usd_achat
            capital_stock_vente_cdf += ca_vente
            capital_stock_vente_usd += usd_vente

        # Toutes les ventes depuis le début (capital généré)
        ventes_toutes = Vente.query.all()
        ventes_total_cdf = 0.0
        ventes_total_usd = 0.0
        benefice_total_cdf = 0.0
        benefice_total_usd = 0.0
        cout_total_cdf = 0.0
        cout_total_usd = 0.0
        ca_par_annee = {}
        for v in ventes_toutes:
            dev = normalize_devise(v.devise)
            cdf_p, usd_p = _cumul_devises(v.montant or 0.0, dev, taux_cdf, v.taux_change)
            ventes_total_cdf += cdf_p
            ventes_total_usd += usd_p
            annee = v.date.year if v.date else None
            if annee:
                a = ca_par_annee.setdefault(annee, {'ca_cdf': 0.0, 'ca_usd': 0.0, 'cout_cdf': 0.0, 'cout_usd': 0.0, 'ventes': 0})
                a['ca_cdf'] += cdf_p
                a['ca_usd'] += usd_p
                a['ventes'] += 1
            for pv in v.produits_vendus:
                qte = pv.quantite or 0
                pv_achat = pv.prix_achat
                if pv_achat is None and pv.produit:
                    pv_achat = pv.produit.prix_achat
                pv_achat = pv_achat or 0.0
                devp2 = normalize_devise(pv.produit.devise) if pv.produit else 'USD'
                cst_cdf, cst_usd = _cumul_devises(pv_achat * qte, devp2, taux_cdf, v.taux_change)
                cout_total_cdf += cst_cdf
                cout_total_usd += cst_usd
                if annee:
                    ca_par_annee[annee]['cout_cdf'] += cst_cdf
                    ca_par_annee[annee]['cout_usd'] += cst_usd
        benefice_total_cdf = ventes_total_cdf - cout_total_cdf
        benefice_total_usd = ventes_total_usd - cout_total_usd
        for a in ca_par_annee.values():
            a['ca_cdf'] = round(a['ca_cdf'], 2)
            a['ca_usd'] = round(a['ca_usd'], 2)
            a['benefice_cdf'] = round(a['ca_cdf'] - a['cout_cdf'], 2)
            a['benefice_usd'] = round(a['ca_usd'] - a['cout_usd'], 2)
            a['marge'] = round((a['benefice_cdf'] / a['ca_cdf'] * 100) if a['ca_cdf'] else 0, 1)

        # Créances totales (toutes dettes en cours, toutes périodes)
        creances_cdf = 0.0
        creances_usd = 0.0
        for v in Vente.query.filter((Vente.statut == 'pending') | (Vente.mode_paiement == 'credit')).all():
            dev = normalize_devise(v.devise)
            cdf_p, usd_p = _cumul_devises(v.montant or 0.0, dev, taux_cdf, v.taux_change)
            creances_cdf += cdf_p
            creances_usd += usd_p

        # Caisse (argent disponible)
        caisse_usd = get_caisse_balance('USD')
        caisse_cdf = get_caisse_balance('CDF')

        capital = {
            'stock_achat_cdf': round(capital_stock_achat_cdf, 2),
            'stock_achat_usd': round(capital_stock_achat_usd, 2),
            'stock_vente_cdf': round(capital_stock_vente_cdf, 2),
            'stock_vente_usd': round(capital_stock_vente_usd, 2),
            'ventes_total_cdf': round(ventes_total_cdf, 2),
            'ventes_total_usd': round(ventes_total_usd, 2),
            'benefice_total_cdf': round(benefice_total_cdf, 2),
            'benefice_total_usd': round(benefice_total_usd, 2),
            'creances_cdf': round(creances_cdf, 2),
            'creances_usd': round(creances_usd, 2),
            'caisse_cdf': round(caisse_cdf, 2),
            'caisse_usd': round(caisse_usd, 2),
            # Actif total = stock (valeur de vente) + argent en caisse + créances
            'actif_total_cdf': round(capital_stock_vente_cdf + caisse_cdf + creances_cdf, 2),
            'actif_total_usd': round(capital_stock_vente_usd + caisse_usd + creances_usd, 2),
            'ca_par_annee': sorted(ca_par_annee.items(), reverse=True)
        }

        # ── RÉSUMÉ DES BÉNÉFICES PAR TYPE DE PÉRIODE (indépendant du filtre) ──
        # Répond à : "je veux voir mes bénéfices par jour, semaine, mois, trimestre, semestre, année"
        au = date.today()
        trim_courant = ((au.month - 1) // 3) * 3 + 1
        fenetres = [
            ('today', "Aujourd'hui", au, au),
            ('7jours', '7 derniers jours', au - timedelta(days=6), au),
            ('30jours', '30 derniers jours', au - timedelta(days=29), au),
            ('trimestre', 'Ce trimestre', date(au.year, trim_courant, 1), au),
            ('semestre', 'Ce semestre (6 mois)', au - timedelta(days=182), au),
            ('annee', 'Cette année', date(au.year, 1, 1), au),
            ('tout', 'Toute la période', date(1900, 1, 1), date(9999, 12, 31)),
        ]
        resume_periodes = []
        for key, label, d0, d1 in fenetres:
            rp = {'key': key, 'label': label, 'ca_cdf': 0.0, 'ca_usd': 0.0,
                  'cout_cdf': 0.0, 'cout_usd': 0.0, 'benefice_cdf': 0.0, 'benefice_usd': 0.0,
                  'ventes': 0}
            for v in ventes_toutes:
                dvente = v.date.date() if v.date else None
                if not dvente or not (d0 <= dvente <= d1):
                    continue
                rp['ventes'] += 1
                dev = normalize_devise(v.devise)
                cdf_p, usd_p = _cumul_devises(v.montant or 0.0, dev, taux_cdf, v.taux_change)
                rp['ca_cdf'] += cdf_p
                rp['ca_usd'] += usd_p
                for pv in v.produits_vendus:
                    qte = pv.quantite or 0
                    pv_achat = pv.prix_achat
                    if pv_achat is None and pv.produit:
                        pv_achat = pv.produit.prix_achat
                    pv_achat = pv_achat or 0.0
                    devp4 = normalize_devise(pv.produit.devise) if pv.produit else 'USD'
                    cst_cdf, cst_usd = _cumul_devises(pv_achat * qte, devp4, taux_cdf, v.taux_change)
                    rp['cout_cdf'] += cst_cdf
                    rp['cout_usd'] += cst_usd
            rp['benefice_cdf'] = round(rp['ca_cdf'] - rp['cout_cdf'], 2)
            rp['benefice_usd'] = round(rp['ca_usd'] - rp['cout_usd'], 2)
            rp['ca_cdf'] = round(rp['ca_cdf'], 2)
            rp['ca_usd'] = round(rp['ca_usd'], 2)
            rp['cout_cdf'] = round(rp['cout_cdf'], 2)
            rp['cout_usd'] = round(rp['cout_usd'], 2)
            rp['marge'] = round((rp['benefice_cdf'] / rp['ca_cdf'] * 100) if rp['ca_cdf'] else 0, 1)
            resume_periodes.append(rp)

        # ── TOP PRODUITS PAR ANNÉE et PAR TRIMESTRE ──
        # Pour chaque année : le top 3 des produits les plus vendus (en quantité)
        ventes_par_annee_prod = {}
        ventes_par_trimestre_prod = {}
        for v in ventes_toutes:
            if not v.date:
                continue
            annee = v.date.year
            q = ((v.date.month - 1) // 3) + 1
            cle_t = (annee, q)
            for pv in v.produits_vendus:
                pid = pv.produit_id
                qte = pv.quantite or 0
                pa = ventes_par_annee_prod.setdefault(annee, {})
                pt = ventes_par_trimestre_prod.setdefault(cle_t, {})
                for d, key in [(pa, 'annee'), (pt, 'trimestre')]:
                    e = d.setdefault(pid, {'produit_id': pid, 'qte': 0, 'revenu_cdf': 0.0, 'revenu_usd': 0.0})
                    e['qte'] += qte
                    devp5 = normalize_devise(pv.produit.devise) if pv.produit else 'USD'
                    rcdf, rusd = _cumul_devises((pv.prix_vente or 0.0) * qte, devp5, taux_cdf, v.taux_change)
                    e['revenu_cdf'] += rcdf
                    e['revenu_usd'] += rusd
        top_par_annee = []
        for annee in sorted(ventes_par_annee_prod.keys(), reverse=True):
            liste = []
            for pid, e in ventes_par_annee_prod[annee].items():
                p = produits_by_id.get(pid)
                liste.append({
                    'produit_id': pid,
                    'nom': p.nom if p else 'Produit supprimé',
                    'categorie': p.categorie if p else '',
                    'qte': e['qte'],
                    'revenu_cdf': round(e['revenu_cdf'], 2),
                    'revenu_usd': round(e['revenu_usd'], 2)
                })
            liste.sort(key=lambda x: x['qte'], reverse=True)
            top_par_annee.append({'annee': annee, 'top': liste[:3], 'nb_produits': len(liste)})
        mois_fr = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
        top_par_trimestre = []
        for (annee, q), prods in sorted(ventes_par_trimestre_prod.items(), reverse=True)[:4]:
            liste = []
            for pid, e in prods.items():
                p = produits_by_id.get(pid)
                liste.append({
                    'produit_id': pid,
                    'nom': p.nom if p else 'Produit supprimé',
                    'categorie': p.categorie if p else '',
                    'qte': e['qte'],
                    'revenu_cdf': round(e['revenu_cdf'], 2),
                    'revenu_usd': round(e['revenu_usd'], 2)
                })
            liste.sort(key=lambda x: x['qte'], reverse=True)
            label_q = f"T{q} {annee}"
            top_par_trimestre.append({'trimestre': label_q, 'top': liste[:3], 'nb_produits': len(liste)})
        top_par_trimestre.reverse()

        # ── RÉAPPROVISIONNEMENTS (sur la période) ──
        q_reap = Reapprovisionnement.query
        if date_start:
            q_reap = q_reap.filter(func.date(Reapprovisionnement.date) >= date_start,
                                   func.date(Reapprovisionnement.date) <= date_end)
        reaps = q_reap.all()
        reappro_by_produit = {}
        for r in reaps:
            pid = r.produit_id
            p = produits_by_id.get(pid)
            e = reappro_by_produit.setdefault(pid, {
                'produit_id': pid,
                'nom': p.nom if p else 'Produit supprimé',
                'categorie': p.categorie if p else 'Non classé',
                'nb_fois': 0,
                'quantite_totale': 0,
                'date_dernier': None
            })
            e['nb_fois'] += 1
            e['quantite_totale'] += r.quantite or 0
            if e['date_dernier'] is None or (r.date and r.date > e['date_dernier']):
                e['date_dernier'] = r.date
        reappro_by_produit = sorted(
            reappro_by_produit.values(),
            key=lambda x: x['quantite_totale'], reverse=True
        )
        for e in reappro_by_produit:
            e['date_dernier'] = e['date_dernier'].isoformat() if e['date_dernier'] else None
            e['stock_actuel'] = produits_by_id.get(e['produit_id']).quantite if produits_by_id.get(e['produit_id']) else 0
        reappro_par_categorie = {}
        for e in reappro_by_produit:
            c = reappro_par_categorie.setdefault(e['categorie'], {'categorie': e['categorie'], 'nb_fois': 0, 'quantite_totale': 0})
            c['nb_fois'] += e['nb_fois']
            c['quantite_totale'] += e['quantite_totale']
        reappro_par_categorie = sorted(
            reappro_par_categorie.values(),
            key=lambda x: x['quantite_totale'], reverse=True
        )

        # ── DÉTAIL ARTICLE → CLIENTS ──
        # Pour chaque produit vendu dans la période : qui l'a acheté, combien, montant, reste en stock
        detail_article_clients = {}
        for v in ventes:
            client = (v.client or '').strip() or 'Client comptant'
            for pv in v.produits_vendus:
                pid = pv.produit_id
                dac = detail_article_clients.setdefault(pid, {'produit_id': pid, 'clients': {}})
                cc = dac['clients'].setdefault(client, {'client': client, 'telephone': v.telephone, 'qte': 0, 'montant_cdf': 0.0, 'montant_usd': 0.0})
                qte = pv.quantite or 0
                cc['qte'] += qte
                devp3 = normalize_devise(pv.produit.devise) if pv.produit else 'USD'
                mcdf, musd = _cumul_devises((pv.prix_vente or 0.0) * qte, devp3, taux_cdf, v.taux_change)
                cc['montant_cdf'] += mcdf
                cc['montant_usd'] += musd
                if v.telephone:
                    cc['telephone'] = v.telephone
        articles_detail = []
        for pid, dac in detail_article_clients.items():
            p = produits_by_id.get(pid)
            clients_liste = sorted(dac['clients'].values(), key=lambda x: x['qte'], reverse=True)[:5]
            articles_detail.append({
                'produit_id': pid,
                'nom': p.nom if p else 'Produit supprimé',
                'categorie': p.categorie if p else '',
                'stock_restant': p.quantite if p else 0,
                'total_vendu': sum(c['qte'] for c in dac['clients'].values()),
                'nb_clients': len(dac['clients']),
                'clients': [{
                    'client': c['client'], 'telephone': c['telephone'],
                    'qte': c['qte'],
                    'montant_cdf': round(c['montant_cdf'], 2),
                    'montant_usd': round(c['montant_usd'], 2)
                } for c in clients_liste]
            })
        articles_detail.sort(key=lambda x: x['total_vendu'], reverse=True)

        # ── CLIENTS : payeurs comptant vs crédit, crédits qui traînent ──
        clients_payeurs = []   # clients qui paient comptant
        clients_crediteurs = []  # clients qui achètent à crédit
        for v in ventes:
            client = (v.client or '').strip() or 'Client comptant'
            if v.mode_paiement == 'credit' or v.statut == 'pending':
                cc2 = next((x for x in clients_crediteurs if x['client'] == client), None)
                if cc2 is None:
                    cc2 = {'client': client, 'telephone': v.telephone, 'nb_ventes': 0, 'montant_cdf': 0.0, 'montant_usd': 0.0}
                    clients_crediteurs.append(cc2)
                cc2['nb_ventes'] += 1
                dev = normalize_devise(v.devise)
                mcdf, musd = _cumul_devises(v.montant or 0.0, dev, taux_cdf, v.taux_change)
                cc2['montant_cdf'] += mcdf
                cc2['montant_usd'] += musd
            else:
                cp = next((x for x in clients_payeurs if x['client'] == client), None)
                if cp is None:
                    cp = {'client': client, 'telephone': v.telephone, 'nb_ventes': 0, 'montant_cdf': 0.0, 'montant_usd': 0.0}
                    clients_payeurs.append(cp)
                cp['nb_ventes'] += 1
                dev = normalize_devise(v.devise)
                mcdf, musd = _cumul_devises(v.montant or 0.0, dev, taux_cdf, v.taux_change)
                cp['montant_cdf'] += mcdf
                cp['montant_usd'] += musd
        clients_payeurs.sort(key=lambda x: x['montant_usd'], reverse=True)
        clients_crediteurs.sort(key=lambda x: x['montant_usd'], reverse=True)

        # Crédits qui traînent (retard > 30 jours, non remboursés)
        credits_traines = []
        for v in credits:
            if v.date_echeance and (aujourdhui - v.date_echeance.date()).days > 30:
                client = (v.client or '').strip() or 'Client comptant'
                dev = normalize_devise(v.devise)
                mcdf, musd = _cumul_devises(v.montant or 0.0, dev, taux_cdf, v.taux_change)
                credits_traines.append({
                    'id': v.id,
                    'client': client,
                    'telephone': v.telephone,
                    'montant_cdf': round(mcdf, 2),
                    'montant_usd': round(musd, 2),
                    'jours_retard': (aujourdhui - v.date_echeance.date()).days,
                    'echeance': v.date_echeance.isoformat(),
                    'date_vente': v.date.isoformat() if v.date else None
                })
        credits_traines.sort(key=lambda x: x['jours_retard'], reverse=True)

        labels_periode = {
            'today': "Aujourd'hui",
            'week': 'Cette semaine',
            '2weeks': 'Les 2 dernières semaines',
            'month': 'Ce mois',
            'semester': 'Ce semestre (6 mois)',
            'year': 'Cette année',
            'all': 'Toute la période'
        }

        panier_moyen_cdf = round(ca_cdf / nb_ventes, 2) if nb_ventes else 0
        panier_moyen_usd = round(ca_usd / nb_ventes, 2) if nb_ventes else 0

        return jsonify({
            'success': True,
            'periode': periode,
            'label_periode': labels_periode.get(periode, periode),
            'date_debut': date_start.isoformat() if date_start else None,
            'date_fin': date_end.isoformat() if date_end else None,
            'taux_change': taux_cdf,
            'synthese': {
                'nb_ventes': nb_ventes,
                'nb_payees': nb_payees,
                'nb_credits': nb_credits,
                'ca_cdf': round(ca_cdf, 2),
                'ca_usd': round(ca_usd, 2),
                'cout_cdf': round(cout_cdf, 2),
                'cout_usd': round(cout_usd, 2),
                'benefice_cdf': round(benefice_cdf, 2),
                'benefice_usd': round(benefice_usd, 2),
                'marge_cdf': round((benefice_cdf / ca_cdf * 100) if ca_cdf else 0, 1),
                'marge_usd': round((benefice_usd / ca_usd * 100) if ca_usd else 0, 1),
                'panier_moyen_cdf': panier_moyen_cdf,
                'panier_moyen_usd': panier_moyen_usd,
                'dettes_cdf': round(dettes_cdf, 2),
                'dettes_usd': round(dettes_usd, 2),
                'dettes_en_retard': dettes_en_retard,
                'clients_actifs': len(clients_list),
                'nouveaux_clients': nouveaux,
                'clients_reguliers': len(clients_reguliers)
            },
            'evolution': evolution,
            'par_mode': {k: ventes_par_mode.get(k, 0) for k in ['cash', 'credit', 'mobile', 'bank']},
            'top_produits': top_produits,
            'produits_peu_demandes': produits_peu,
            'rotation_stock': rotation,
            'dettes_clients': dettes_clients,
            'top_clients': top_clients,
            'capital': capital,
            'resume_periodes': resume_periodes,
            'top_par_annee': top_par_annee,
            'top_par_trimestre': top_par_trimestre,
            'reapprovisionnements': reappro_by_produit,
            'reappro_par_categorie': reappro_par_categorie,
            'detail_articles': articles_detail,
            'clients_payeurs': clients_payeurs,
            'clients_crediteurs': clients_crediteurs,
            'credits_traines': credits_traines
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/activites/stock', methods=['GET'])
def get_activites_stock():
    """Journal des activités de stock : détail chronologique + résumé par produit.
    Filtres : periode, produit_id, limite. Le résumé couvre TOUT l'historique.
    """
    try:
        periode = request.args.get('periode', 'all')
        produit_id = request.args.get('produit_id', type=int)
        limite = min(int(request.args.get('limite', 300)), 1000)
        date_start, date_end, _ = _plage_periode_etendue(periode)

        # ── Résumé global par produit (toutes les activités) ──
        toutes = ActiviteStock.query.order_by(ActiviteStock.id.asc()).all()
        produits_map = {p.id: p for p in Produit.query.all()}
        compteur_type = {
            'creation': 'nb_creation', 'modification': 'nb_modification',
            'vente': 'nb_ventes', 'reapprovisionnement': 'nb_reappro',
            'epuisement': 'nb_epuisement', 'retour': 'nb_retour',
            'suppression': 'nb_suppression',
        }
        resume = {}
        for a in toutes:
            r = resume.setdefault(a.produit_id, {
                'produit_id': a.produit_id,
                'produit_nom': a.produit.nom if a.produit else 'Produit supprimé',
                'categorie': a.produit.categorie if a.produit else '',
                'nb_creation': 0, 'nb_modification': 0, 'nb_ventes': 0, 'nb_reappro': 0,
                'nb_epuisement': 0, 'nb_retour': 0, 'nb_suppression': 0,
                'qte_vendue': 0, 'qte_ajoutee': 0, 'nb_activites': 0,
                'premiere_activite': None, 'derniere_activite': None
            })
            compteur = compteur_type.get(a.type, 'nb_' + a.type)
            r[compteur] = r.get(compteur, 0) + 1
            r['nb_activites'] += 1
            if a.type == 'vente':
                r['qte_vendue'] += a.variation  # négatif
            elif a.type in ('reapprovisionnement', 'retour', 'creation'):
                r['qte_ajoutee'] += max(a.variation, 0)
            if a.date:
                if r['premiere_activite'] is None or a.date < r['premiere_activite']:
                    r['premiere_activite'] = a.date
                if r['derniere_activite'] is None or a.date > r['derniere_activite']:
                    r['derniere_activite'] = a.date
        # enrichir stock_actuel
        for pid, r in resume.items():
            p = produits_map.get(pid)
            r['stock_actuel'] = p.quantite if p else 0
            r['statut_actuel'] = 'Épuisé' if p and p.quantite == 0 else ('En stock' if p else 'Supprimé')
            r['premiere_activite'] = r['premiere_activite'].isoformat() if r['premiere_activite'] else None
            r['derniere_activite'] = r['derniere_activite'].isoformat() if r['derniere_activite'] else None
        resume_list = sorted(resume.values(), key=lambda x: x['nb_activites'], reverse=True)

        # ── Détail chronologique (filtré) ──
        query = ActiviteStock.query
        if date_start:
            query = query.filter(func.date(ActiviteStock.date) >= date_start,
                                 func.date(ActiviteStock.date) <= date_end)
        if produit_id:
            query = query.filter(ActiviteStock.produit_id == produit_id)
        detail = query.order_by(ActiviteStock.date.desc(), ActiviteStock.id.desc()).limit(limite).all()

        return jsonify({
            'success': True,
            'label_periode': ({
                'today': "Aujourd'hui", 'week': 'Cette semaine', '2weeks': 'Les 2 dernières semaines',
                'month': 'Ce mois', 'semester': 'Ce semestre', 'year': 'Cette année', 'all': 'Toute la période'
            }).get(periode, periode),
            'total_activites': len(toutes),
            'total_epuisements': sum(r['nb_epuisement'] for r in resume_list),
            'total_produits_actifs': len(resume_list),
            'resume_par_produit': [{
                **r,
                'qte_vendue': abs(r['qte_vendue']),
                'nb_ventes': r['nb_ventes'],
                'nb_epuisement': r['nb_epuisement']
            } for r in resume_list],
            'activites': [a.to_dict() for a in detail]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/activites/caisse', methods=['GET'])
def get_activites_caisse():
    """Journal des activités de caisse : mouvements récents + résumé."""
    try:
        limite = min(int(request.args.get('limite', 100)), 500)
        mouvements = CaisseMovement.query.order_by(CaisseMovement.date.desc()).all()

        entrees_cdf = 0.0
        entrees_usd = 0.0
        sorties_cdf = 0.0
        sorties_usd = 0.0
        for m in mouvements:
            if m.devise == 'USD':
                if m.type == 'in':
                    entrees_usd += m.montant
                else:
                    sorties_usd += m.montant
            else:
                if m.type == 'in':
                    entrees_cdf += m.montant
                else:
                    sorties_cdf += m.montant

        # Répartir le solde par devise
        solde_cdf = get_caisse_balance('CDF')
        solde_usd = get_caisse_balance('USD')

        detail = mouvements[:limite]
        return jsonify({
            'success': True,
            'resume': {
                'nb_mouvements': len(mouvements),
                'entrees_cdf': round(entrees_cdf, 2),
                'entrees_usd': round(entrees_usd, 2),
                'sorties_cdf': round(sorties_cdf, 2),
                'sorties_usd': round(sorties_usd, 2),
                'solde_cdf': round(solde_cdf, 2),
                'solde_usd': round(solde_usd, 2)
            },
            'mouvements': [{
                'id': m.id,
                'type': m.type,
                'libelle': m.libelle,
                'montant': m.montant,
                'devise': m.devise,
                'date': m.date.isoformat() if m.date else None,
                'solde_apres': m.solde_apres,
                'notes': m.notes
            } for m in detail]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400
def delete_sale(id):
    """Supprime une vente, réincrémente le stock et supprime le mouvement de caisse lié"""
    try:
        vente = Vente.query.get_or_404(id)

        # 1. Réincrémenter les stocks des produits
        for pv in vente.produits_vendus:
            if pv.produit:
                qty_avant = pv.produit.quantite
                pv.produit.quantite += pv.quantite
                enregistrer_activite_stock(
                    pv.produit.id, 'retour', qty_avant, pv.produit.quantite,
                    f"Annulation de la vente #{vente.id} : restitution de {pv.quantite} unité(s) en stock"
                )

        # 2. Supprimer les mouvements de caisse liés
        mouvements_caisse = CaisseMovement.query.filter_by(vente_id=vente.id).all()
        for m in mouvements_caisse:
            db.session.delete(m)

        # 2bis. Supprimer les écritures comptables liées
        EcritureComptable.query.filter(EcritureComptable.source_id == vente.id,
                                       EcritureComptable.source.in_(['vente', 'vente_credit', 'vente_paiement'])).delete()

        # 3. Supprimer la vente
        db.session.delete(vente)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Vente supprimée avec succès et mouvements de caisse annulés'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors de la suppression de la vente: {str(e)}'
        }), 400

@api_bp.route('/ventes', methods=['POST'])
def create_sale():
    """Crée une nouvelle vente"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Données manquantes'}), 400

        produits_data = data.get('produits', [])
        if not produits_data:
            return jsonify({'success': False, 'message': 'Aucun produit sélectionné'}), 400

        montant = float(data.get('montant', 0))
        if montant <= 0:
            return jsonify({'success': False, 'message': 'Montant de vente invalide'}), 400

        mode_paiement = data.get('mode_paiement', 'cash')
        statut = 'pending' if mode_paiement == 'credit' else 'completed'
        devise = data.get('devise', 'XAF')
        taux_change = float(data.get('taux_change')) if data.get('taux_change') else None

        vente = Vente(
            client=data.get('client'),
            telephone=data.get('telephone'),
            montant=montant,
            mode_paiement=mode_paiement,
            statut=statut,
            devise=devise,
            taux_change=taux_change,
            date_echeance=datetime.fromisoformat(data.get('date_echeance')) if data.get('date_echeance') else None,
            user_id=session.get('user_id')
        )
        db.session.add(vente)

        for produit_item in produits_data:
            produit_id = int(produit_item.get('id'))
            quantite = int(produit_item.get('quantite', 0))
            if quantite <= 0:
                continue

            produit = Produit.query.get_or_404(produit_id)
            if produit.quantite < quantite:
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'message': f'Stock insuffisant pour le produit {produit.nom}'
                }), 400

            qty_avant = produit.quantite
            produit.quantite -= quantite
            client_nom = (data.get('client') or '').strip() or 'Client comptant'
            enregistrer_activite_stock(
                produit.id, 'vente', qty_avant, produit.quantite,
                f"Vente de {quantite} unité(s) à {client_nom} — stock {qty_avant} → {produit.quantite}"
            )
            if produit.quantite == 0 and qty_avant > 0:
                enregistrer_activite_stock(
                    produit.id, 'epuisement', qty_avant, 0,
                    f"Stock épuisé après la vente à {client_nom}"
                )
            produit_vendu = ProduitVendu(
                vente=vente,
                produit=produit,
                quantite=quantite,
                prix_vente=produit.prix_vente,
                prix_achat=produit.prix_achat
            )
            db.session.add(produit_vendu)

        if mode_paiement == 'cash':
            db.session.flush()
            dernier_solde = get_caisse_balance(devise)
            if devise == 'USD' and taux_change is None:
                taux_change = get_exchange_rate('USD', 'XAF')
            solde_apres = dernier_solde + montant
            caisse_mouvement = CaisseMovement(
                type='in',
                libelle=f'Vente #{vente.id} enregistré',
                montant=montant,
                devise=devise,
                taux_change=taux_change,
                solde_apres=solde_apres,
                vente_id=vente.id
            )
            db.session.add(caisse_mouvement)

        generation_vente(vente, user_id=session.get('user_id'))
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Vente enregistrée avec succès',
            'vente_id': vente.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors de l\'enregistrement: {str(e)}'
        }), 400


@api_bp.route('/ventes/<int:id>/payer-credit', methods=['POST'])
def pay_credit_sale(id):
    """Enregistre le paiement d'une vente à crédit"""
    try:
        vente = Vente.query.get_or_404(id)
        if vente.statut != 'pending':
            return jsonify({'success': False, 'message': 'Cette vente n\'est pas en attente de paiement'}), 400

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'success': False, 'message': 'Données manquantes'}), 400

        montant = float(data.get('montant', vente.montant))
        if montant <= 0:
            return jsonify({'success': False, 'message': 'Montant invalide'}), 400

        devise = vente.devise or 'XAF'
        taux_change = vente.taux_change
        if devise == 'USD' and taux_change is None:
            taux_change = get_exchange_rate('USD', 'XAF')

        dernier_solde = get_caisse_balance(devise)
        solde_apres = dernier_solde + montant

        caisse_mouvement = CaisseMovement(
            type='in',
            libelle=f'Paiement crédit Vente #{vente.id}',
            montant=montant,
            devise=devise,
            taux_change=taux_change,
            solde_apres=solde_apres,
            vente_id=vente.id
        )
        vente.statut = 'completed'
        db.session.add(caisse_mouvement)
        generation_paiement_credit(vente, montant, caisse_mouvement=caisse_mouvement, user_id=session.get('user_id'))
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Paiement du crédit enregistré avec succès'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/ventes/statistiques', methods=['GET'])
def get_sales_statistics():
    """Récupère les statistiques des ventes"""
    try:
        total_ventes = Vente.query.count()
        chiffre_affaires_xaf = db.session.query(func.coalesce(func.sum(Vente.montant), 0)).filter(Vente.devise == 'XAF').scalar() or 0
        chiffre_affaires_usd = db.session.query(func.coalesce(func.sum(Vente.montant), 0)).filter(Vente.devise == 'USD').scalar() or 0

        montant_total_xaf = 0
        for vente in Vente.query.all():
            if vente.devise == 'USD':
                taux = vente.taux_change if vente.taux_change else get_exchange_rate('USD', 'XAF')
                montant_total_xaf += vente.montant * taux if taux else 0
            else:
                montant_total_xaf += vente.montant

        panier_moyen = round(montant_total_xaf / total_ventes, 0) if total_ventes else 0

        today = datetime.utcnow().date()
        ventes_aujourdhui = Vente.query.filter(func.date(Vente.date) == today).count()

        return jsonify({
            'success': True,
            'total_ventes': total_ventes,
            'chiffre_affaires_xaf': chiffre_affaires_xaf,
            'chiffre_affaires_usd': chiffre_affaires_usd,
            'ventes_aujourdhui': ventes_aujourdhui,
            'panier_moyen': panier_moyen
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/caisse/statistiques', methods=['GET'])
def get_caisse_statistics():
    """Récupère les statistiques de caisse séparées par devise (USD et CDF)"""
    try:
        mouvements = CaisseMovement.query.all()
        
        total_entrees_usd = 0
        total_sorties_usd = 0
        total_entrees_cdf = 0
        total_sorties_cdf = 0

        today = datetime.utcnow().date()
        today_entrees_usd = 0
        today_sorties_usd = 0
        today_entrees_cdf = 0
        today_sorties_cdf = 0

        for mouvement in mouvements:
            montant = mouvement.montant or 0
            devise_norm = normalize_devise(mouvement.devise)
            is_today = (mouvement.date and mouvement.date.date() == today)

            if devise_norm == 'USD':
                if mouvement.type == 'in':
                    total_entrees_usd += montant
                    if is_today:
                        today_entrees_usd += montant
                else:
                    total_sorties_usd += montant
                    if is_today:
                        today_sorties_usd += montant
            else:  # CDF / FC / XAF
                if mouvement.type == 'in':
                    total_entrees_cdf += montant
                    if is_today:
                        today_entrees_cdf += montant
                else:
                    total_sorties_cdf += montant
                    if is_today:
                        today_sorties_cdf += montant

        solde_usd = total_entrees_usd - total_sorties_usd
        solde_cdf = total_entrees_cdf - total_sorties_cdf

        today_balance_usd = today_entrees_usd - today_sorties_usd
        today_balance_cdf = today_entrees_cdf - today_sorties_cdf

        return jsonify({
            'success': True,
            'solde_usd': solde_usd,
            'solde_cdf': solde_cdf,
            'total_entrees_usd': total_entrees_usd,
            'total_sorties_usd': total_sorties_usd,
            'total_entrees_cdf': total_entrees_cdf,
            'total_sorties_cdf': total_sorties_cdf,
            'today_balance_usd': today_balance_usd,
            'today_balance_cdf': today_balance_cdf
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/caisse/mouvements', methods=['GET'])
def get_caisse_movements():
    """Récupère la liste des mouvements de caisse avec filtres de recherche et devises"""
    try:
        search = request.args.get('search', '').strip()
        date_filter = request.args.get('date', '').strip()
        type_filter = request.args.get('type', '').strip()
        devise_filter = request.args.get('devise', '').strip()

        query = CaisseMovement.query

        if type_filter in ['in', 'out']:
            query = query.filter(CaisseMovement.type == type_filter)

        if devise_filter:
            norm = normalize_devise(devise_filter)
            if norm == 'CDF':
                query = query.filter(CaisseMovement.devise.in_(['CDF', 'FC', 'XAF']))
            elif norm == 'USD':
                query = query.filter(CaisseMovement.devise == 'USD')

        if date_filter == 'today':
            today_str = datetime.utcnow().strftime('%Y-%m-%d')
            query = query.filter(func.date(CaisseMovement.date) == today_str)
        elif date_filter == 'week':
            one_week_ago = datetime.utcnow() - timedelta(days=7)
            query = query.filter(CaisseMovement.date >= one_week_ago)
        elif date_filter == 'month':
            one_month_ago = datetime.utcnow() - timedelta(days=30)
            query = query.filter(CaisseMovement.date >= one_month_ago)

        if search:
            query = query.filter(
                (CaisseMovement.libelle.ilike(f'%{search}%')) |
                (CaisseMovement.notes.ilike(f'%{search}%'))
            )

        mouvements = query.order_by(CaisseMovement.date.desc()).all()

        mouvements_list = []
        user_id = session.get('user_id')
        user_name = "Caissier Principal"
        if user_id:
            u = User.query.get(user_id)
            if u:
                user_name = u.nom_complet or u.username

        for m in mouvements:
            item = m.to_dict()
            item['devise'] = normalize_devise(m.devise)
            item['bon_ref'] = f"BC-{m.date.year if m.date else 2026}-{m.id:04d}"
            item['operator_name'] = user_name
            if m.vente_id:
                v = Vente.query.get(m.vente_id)
                if v:
                    item['vente_info'] = {
                        'client': v.client or 'Client comptant',
                        'telephone': v.telephone or 'N/A',
                        'mode_paiement': v.mode_paiement,
                        'statut': v.statut,
                        'montant': v.montant,
                        'devise': normalize_devise(v.devise),
                        'produits': [pv.to_dict() for pv in v.produits_vendus]
                    }
            mouvements_list.append(item)

        return jsonify({
            'success': True,
            'mouvements': mouvements_list
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/caisse/mouvements/<int:id>', methods=['GET'])
def get_single_caisse_movement(id):
    """Récupère les détails d'un mouvement de caisse pour fiche d'impression"""
    try:
        m = CaisseMovement.query.get_or_404(id)
        item = m.to_dict()
        item['devise'] = normalize_devise(m.devise)
        item['bon_ref'] = f"BC-{m.date.year if m.date else 2026}-{m.id:04d}"
        
        user_id = session.get('user_id')
        user_name = "Caissier Principal"
        if user_id:
            u = User.query.get(user_id)
            if u:
                user_name = u.nom_complet or u.username
        item['operator_name'] = user_name

        if m.vente_id:
            v = Vente.query.get(m.vente_id)
            if v:
                item['vente_info'] = {
                    'client': v.client or 'Client comptant',
                    'telephone': v.telephone or 'N/A',
                    'mode_paiement': v.mode_paiement,
                    'statut': v.statut,
                    'montant': v.montant,
                    'devise': normalize_devise(v.devise),
                    'produits': [pv.to_dict() for pv in v.produits_vendus]
                }
        return jsonify({'success': True, 'mouvement': item})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400

@api_bp.route('/caisse/mouvements', methods=['POST'])
def create_caisse_movement():
    """Enregistre un mouvement de caisse manuel dans la devise spécifiée (USD ou CDF)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Données manquantes'}), 400

        mouvement_type = data.get('type')
        if mouvement_type not in ['in', 'out']:
            return jsonify({'success': False, 'message': 'Type de mouvement invalide'}), 400

        montant = float(data.get('montant', 0))
        if montant <= 0:
            return jsonify({'success': False, 'message': 'Montant invalide'}), 400

        devise = normalize_devise(data.get('devise', 'USD'))
        taux_change = float(data.get('taux_change')) if data.get('taux_change') else None

        dernier_solde = get_caisse_balance(devise)
        solde_apres = dernier_solde + montant if mouvement_type == 'in' else dernier_solde - montant

        mouvement = CaisseMovement(
            type=mouvement_type,
            libelle=data.get('libelle', 'Mouvement manuel'),
            montant=montant,
            devise=devise,
            taux_change=taux_change,
            date=datetime.fromisoformat(data.get('date')) if data.get('date') else datetime.utcnow(),
            solde_apres=solde_apres,
            notes=data.get('notes')
        )
        db.session.add(mouvement)
        generation_caisse(mouvement, user_id=session.get('user_id'))
        db.session.commit()

        return jsonify({'success': True, 'message': 'Mouvement enregistré', 'mouvement': mouvement.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400

@api_bp.route('/caisse/mouvements/<int:id>', methods=['DELETE'])
def delete_caisse_mouvement(id):
    """Supprime un mouvement de caisse manuel uniquement"""
    try:
        mouvement = CaisseMovement.query.get_or_404(id)
        if mouvement.vente_id:
            return jsonify({
                'success': False,
                'message': 'Ce mouvement provient d\'une vente. Veuillez le supprimer depuis la gestion des ventes.'
            }), 400

        db.session.delete(mouvement)
        EcritureComptable.query.filter_by(source='caisse', source_id=mouvement.id).delete()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Mouvement de caisse supprimé'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400

@api_bp.route('/produits/<int:id>/reapprovisionner', methods=['POST'])
def reapprovisionner_produit(id):
    """Réapprovisionne un produit en augmentant sa quantité en stock"""
    try:
        produit = Produit.query.get_or_404(id)
        data = request.get_json(silent=True) or {}
        
        quantite_ajoutee = int(data.get('quantite', 0))
        if quantite_ajoutee <= 0:
            return jsonify({
                'success': False,
                'message': 'Veuillez saisir une quantité supérieure à 0'
            }), 400
            
        ancienne_quantite = produit.quantite
        produit.quantite += quantite_ajoutee
        
        user_id = session.get('user_id')
        # Historique des réapprovisionnements (pour les rapports)
        db.session.add(Reapprovisionnement(
            produit_id=produit.id,
            quantite=quantite_ajoutee,
            user_id=user_id
        ))
        enregistrer_activite_stock(
            produit.id, 'reapprovisionnement', ancienne_quantite, produit.quantite,
            f"Réapprovisionnement : ajout de +{quantite_ajoutee} unités — stock {ancienne_quantite} → {produit.quantite}"
        )
        
        if user_id:
            Notification.create_notification(
                user_id=user_id,
                title=f'Réapprovisionnement: {produit.nom}',
                message=f'Le stock de {produit.nom} a été augmenté de +{quantite_ajoutee} unités (nouveau stock: {produit.quantite}).',
                type='success'
            )
            
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Stock de "{produit.nom}" augmenté de +{quantite_ajoutee} unités avec succès !',
            'produit': produit.to_dict(),
            'ancienne_quantite': ancienne_quantite,
            'nouvelle_quantite': produit.quantite
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors du réapprovisionnement: {str(e)}'
        }), 400


@api_bp.route('/ventes/graphique', methods=['GET'])
def get_sales_chart_data():
    """Données d'évolution des ventes pour les graphiques du tableau de bord"""
    try:
        periode = request.args.get('periode', 'week')
        now = datetime.utcnow()
        rate = get_exchange_rate('USD', 'CDF') or 2800.0

        labels = []
        data_cdf = []
        data_usd = []
        data_count = []

        if periode == 'week':
            days_fr = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
            for i in range(6, -1, -1):
                day_date = (now - timedelta(days=i)).date()
                day_name = days_fr[day_date.weekday()]
                date_str = day_date.strftime('%d/%m')
                labels.append(f"{day_name} {date_str}")
                
                ventes_jour = Vente.query.filter(func.date(Vente.date) == day_date).all()
                data_count.append(len(ventes_jour))
                
                tot_cdf = 0.0
                tot_usd = 0.0
                for v in ventes_jour:
                    dev = normalize_devise(v.devise)
                    m = v.montant or 0.0
                    if dev == 'USD':
                        tot_usd += m
                        tot_cdf += m * (v.taux_change or rate)
                    else:
                        tot_cdf += m
                        tot_usd += m / rate if rate else 0.0
                data_cdf.append(round(tot_cdf, 2))
                data_usd.append(round(tot_usd, 2))

        elif periode == 'month':
            for i in range(29, -1, -1):
                day_date = (now - timedelta(days=i)).date()
                labels.append(day_date.strftime('%d/%m'))
                
                ventes_jour = Vente.query.filter(func.date(Vente.date) == day_date).all()
                data_count.append(len(ventes_jour))
                
                tot_cdf = 0.0
                tot_usd = 0.0
                for v in ventes_jour:
                    dev = normalize_devise(v.devise)
                    m = v.montant or 0.0
                    if dev == 'USD':
                        tot_usd += m
                        tot_cdf += m * (v.taux_change or rate)
                    else:
                        tot_cdf += m
                        tot_usd += m / rate if rate else 0.0
                data_cdf.append(round(tot_cdf, 2))
                data_usd.append(round(tot_usd, 2))

        elif periode == 'year':
            months_fr = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
            for i in range(11, -1, -1):
                year = now.year
                month = now.month - i
                while month <= 0:
                    month += 12
                    year -= 1
                
                labels.append(f"{months_fr[month-1]} {year}")
                month_str = f"{year}-{month:02d}"
                ventes_mois = Vente.query.filter(func.strftime('%Y-%m', Vente.date) == month_str).all()
                data_count.append(len(ventes_mois))
                
                tot_cdf = 0.0
                tot_usd = 0.0
                for v in ventes_mois:
                    dev = normalize_devise(v.devise)
                    m = v.montant or 0.0
                    if dev == 'USD':
                        tot_usd += m
                        tot_cdf += m * (v.taux_change or rate)
                    else:
                        tot_cdf += m
                        tot_usd += m / rate if rate else 0.0
                data_cdf.append(round(tot_cdf, 2))
                data_usd.append(round(tot_usd, 2))

        return jsonify({
            'success': True,
            'periode': periode,
            'labels': labels,
            'data_cdf': data_cdf,
            'data_usd': data_usd,
            'data_count': data_count,
            'taux_change': rate
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400


@api_bp.route('/stock/repartition', methods=['GET'])
def get_stock_repartition_chart():
    """Répartition du stock par catégorie et par statut"""
    try:
        produits = Produit.query.all()
        rate = get_exchange_rate('USD', 'CDF') or 2800.0

        categories_map = {}
        status_counts = {'disponible': 0, 'faible': 0, 'epuise': 0}

        for p in produits:
            cat = p.categorie or 'Non classé'
            if cat not in categories_map:
                categories_map[cat] = {'quantite': 0, 'valeur_cdf': 0.0, 'valeur_usd': 0.0, 'nb_produits': 0}
            
            dev = normalize_devise(p.devise)
            qty = p.quantite or 0
            prix = p.prix_achat or 0.0
            val_native = prix * qty
            
            if dev == 'USD':
                val_usd = val_native
                val_cdf = val_native * rate
            else:
                val_cdf = val_native
                val_usd = val_native / rate if rate else 0.0

            categories_map[cat]['quantite'] += qty
            categories_map[cat]['valeur_cdf'] += val_cdf
            categories_map[cat]['valeur_usd'] += val_usd
            categories_map[cat]['nb_produits'] += 1

            if qty == 0:
                status_counts['epuise'] += 1
            elif qty <= (p.stock_min or 5):
                status_counts['faible'] += 1
            else:
                status_counts['disponible'] += 1

        cat_labels = list(categories_map.keys())
        cat_quantities = [categories_map[c]['quantite'] for c in cat_labels]
        cat_valeurs_cdf = [round(categories_map[c]['valeur_cdf'], 2) for c in cat_labels]
        cat_valeurs_usd = [round(categories_map[c]['valeur_usd'], 2) for c in cat_labels]
        cat_nb_produits = [categories_map[c]['nb_produits'] for c in cat_labels]

        return jsonify({
            'success': True,
            'categories': {
                'labels': cat_labels,
                'quantities': cat_quantities,
                'valeurs_cdf': cat_valeurs_cdf,
                'valeurs_usd': cat_valeurs_usd,
                'nb_produits': cat_nb_produits
            },
            'statuts': status_counts,
            'total_produits': len(produits)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400


@api_bp.route('/stock/statistiques', methods=['GET'])
def get_stock_statistics():
    """Récupère les statistiques du stock en devises CDF et USD"""
    try:
        produits = Produit.query.all()
        rate = get_exchange_rate('USD', 'CDF') or 2800.0
        
        total_produits = len(produits)
        stock_faible = sum(1 for p in produits if p.quantite <= p.stock_min and p.quantite > 0)
        stock_epuise = sum(1 for p in produits if p.quantite == 0)
        
        valeur_stock_cdf = 0.0
        valeur_stock_usd = 0.0
        valeur_vente_cdf = 0.0
        valeur_vente_usd = 0.0
        
        valeur_par_categorie = {}
        produits_par_categorie = {}
        valeur_par_devise = {'CDF': 0.0, 'USD': 0.0}
        
        for p in produits:
            devise = normalize_devise(p.devise)
            qty = p.quantite or 0
            cost_native = (p.prix_achat or 0.0) * qty
            sale_native = (p.prix_vente or 0.0) * qty
            
            if devise not in valeur_par_devise:
                valeur_par_devise[devise] = 0.0
            valeur_par_devise[devise] += cost_native
            
            if devise == 'USD':
                val_cost_usd = cost_native
                val_cost_cdf = cost_native * rate
                val_sale_usd = sale_native
                val_sale_cdf = sale_native * rate
            else:
                val_cost_cdf = cost_native
                val_cost_usd = cost_native / rate if rate else 0.0
                val_sale_cdf = sale_native
                val_sale_usd = sale_native / rate if rate else 0.0

            valeur_stock_cdf += val_cost_cdf
            valeur_stock_usd += val_cost_usd
            valeur_vente_cdf += val_sale_cdf
            valeur_vente_usd += val_sale_usd

            cat = p.categorie or 'Non classé'
            if cat not in valeur_par_categorie:
                valeur_par_categorie[cat] = 0.0
                produits_par_categorie[cat] = 0
            valeur_par_categorie[cat] += val_cost_cdf
            produits_par_categorie[cat] += 1

        alertes_stock = [
            {
                'id': p.id,
                'nom': p.nom,
                'reference': p.reference,
                'quantite': p.quantite,
                'stock_min': p.stock_min,
                'devise': normalize_devise(p.devise),
                'prix_achat': p.prix_achat,
                'prix_vente': p.prix_vente,
                'categorie': p.categorie
            }
            for p in produits if p.quantite <= p.stock_min
        ]

        user_id = session.get('user_id')
        if user_id:
            for p in produits:
                if p.quantite <= p.stock_min and p.quantite > 0:
                    notification_existante = Notification.query.filter_by(
                        user_id=user_id,
                        type='stock_faible',
                        read=False
                    ).filter(Notification.message.like(f'%{p.nom}%')).first()
                    
                    if not notification_existante:
                        Notification.create_notification(
                            user_id=user_id,
                            title=f'Stock faible: {p.nom}',
                            message=f'Le produit {p.nom} (Réf: {p.reference}) a un stock de {p.quantite} unités (minimum: {p.stock_min}). Veuillez réapprovisionner.',
                            type='warning'
                        )

        return jsonify({
            'success': True,
            'total_produits': total_produits,
            'valeur_stock_cdf': round(valeur_stock_cdf, 2),
            'valeur_stock_usd': round(valeur_stock_usd, 2),
            'valeur_vente_cdf': round(valeur_vente_cdf, 2),
            'valeur_vente_usd': round(valeur_vente_usd, 2),
            'valeur_stock': round(valeur_stock_cdf, 2),
            'valeur_par_devise': valeur_par_devise,
            'stock_faible': stock_faible,
            'stock_epuise': stock_epuise,
            'valeur_par_categorie': valeur_par_categorie,
            'produits_par_categorie': produits_par_categorie,
            'alertes_stock': alertes_stock,
            'taux_change': rate
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

# ==================== API Utilisateurs ====================

@api_bp.route('/users', methods=['GET'])
def get_users():
    """Récupère la liste des utilisateurs"""
    try:
        search = request.args.get('search', '')
        role = request.args.get('role', '')
        status = request.args.get('status', '')
        
        query = User.query
        
        if search:
            query = query.filter(
                (User.username.ilike(f'%{search}%')) |
                (User.email.ilike(f'%{search}%')) |
                (User.first_name.ilike(f'%{search}%')) |
                (User.last_name.ilike(f'%{search}%'))
            )
        
        if role:
            query = query.filter(User.role == role)
        
        if status == 'active':
            query = query.filter(User.is_active == True)
        elif status == 'inactive':
            query = query.filter(User.is_active == False)
        
        users = query.all()
        
        return jsonify({
            'success': True,
            'users': [u.to_dict() for u in users]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/users/statistiques', methods=['GET'])
def get_users_statistics():
    """Récupère les statistiques des utilisateurs"""
    try:
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        admin_count = User.query.filter_by(role='admin').count()
        inactive_users = User.query.filter_by(is_active=False).count()
        
        return jsonify({
            'success': True,
            'total_users': total_users,
            'active_users': active_users,
            'admin_count': admin_count,
            'inactive_users': inactive_users
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/users/<int:id>', methods=['GET'])
def get_user(id):
    """Récupère un utilisateur par son ID"""
    try:
        user = User.query.get_or_404(id)
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 404

@api_bp.route('/users', methods=['POST'])
def create_user():
    """Crée un nouvel utilisateur"""
    try:
        data = request.get_json()
        
        # Validation
        if not data.get('username') or not data.get('email') or not data.get('password'):
            return jsonify({
                'success': False,
                'message': 'Veuillez remplir tous les champs obligatoires'
            }), 400
        
        # Vérifier si l'utilisateur existe déjà
        if User.query.filter_by(username=data['username']).first():
            return jsonify({
                'success': False,
                'message': 'Ce nom d\'utilisateur est déjà pris'
            }), 400
        
        if User.query.filter_by(email=data['email']).first():
            return jsonify({
                'success': False,
                'message': 'Cet email est déjà utilisé'
            }), 400
        
        # Créer l'utilisateur
        user = User(
            username=data['username'],
            email=data['email'],
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            role=data.get('role', 'user'),
            is_active=data.get('is_active', True)
        )
        user.set_password(data['password'])
        user.set_permissions(data.get('permissions'))
        
        db.session.add(user)
        db.session.commit()
        
        # Créer une notification pour les admins
        Notification.create_notification(
            user_id=session.get('user_id'),
            title='Nouvel utilisateur créé',
            message=f'L\'utilisateur {user.username} a été ajouté au système',
            type='success'
        )
        
        return jsonify({
            'success': True,
            'message': 'Utilisateur créé avec succès',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }), 400

@api_bp.route('/users/<int:id>', methods=['PUT'])
def update_user(id):
    """Met à jour un utilisateur"""
    try:
        user = User.query.get_or_404(id)
        data = request.get_json()
        
        # Vérifications d'unicité
        new_username = data.get('username', user.username)
        new_email = data.get('email', user.email)
        if new_username != user.username and User.query.filter_by(username=new_username).first():
            return jsonify({
                'success': False,
                'message': 'Ce nom d\'utilisateur est déjà pris'
            }), 400
        if new_email != user.email and User.query.filter_by(email=new_email).first():
            return jsonify({
                'success': False,
                'message': 'Cet email est déjà utilisé'
            }), 400
        
        # Protection du compte personnel
        is_self = session.get('user_id') == id
        if is_self:
            if data.get('is_active') is False:
                return jsonify({
                    'success': False,
                    'message': 'Vous ne pouvez pas désactiver votre propre compte'
                }), 400
            if data.get('role') and data['role'] != 'admin':
                return jsonify({
                    'success': False,
                    'message': 'Vous ne pouvez pas retirer votre rôle administrateur'
                }), 400
        
        user.username = new_username
        user.email = new_email
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.role = data.get('role', user.role)
        user.is_active = data.get('is_active', user.is_active)
        user.set_permissions(data.get('permissions'))
        
        if data.get('password'):
            user.set_password(data['password'])
        
        db.session.commit()
        
        # Créer une notification
        Notification.create_notification(
            user_id=session.get('user_id'),
            title='Utilisateur modifié',
            message=f'L\'utilisateur {user.username} a été modifié',
            type='info'
        )
        
        return jsonify({
            'success': True,
            'message': 'Utilisateur mis à jour avec succès',
            'user': user.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors de la mise à jour: {str(e)}'
        }), 400

@api_bp.route('/users/<int:id>', methods=['DELETE'])
def delete_user(id):
    """Supprime un utilisateur"""
    try:
        user = User.query.get_or_404(id)
        
        # Empêcher la suppression de soi-même
        if session.get('user_id') == id:
            return jsonify({
                'success': False,
                'message': 'Vous ne pouvez pas supprimer votre propre compte'
            }), 400
        
        db.session.delete(user)
        db.session.commit()
        
        # Créer une notification
        Notification.create_notification(
            user_id=session.get('user_id'),
            title='Utilisateur supprimé',
            message=f'L\'utilisateur {user.username} a été supprimé',
            type='warning'
        )
        
        return jsonify({
            'success': True,
            'message': 'Utilisateur supprimé avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }), 400

@api_bp.route('/users/<int:id>/password', methods=['PUT'])
def change_user_password(id):
    """Change le mot de passe d'un utilisateur"""
    try:
        user = User.query.get_or_404(id)
        data = request.get_json()
        
        if not data.get('password'):
            return jsonify({
                'success': False,
                'message': 'Veuillez fournir un mot de passe'
            }), 400
        
        user.set_password(data['password'])
        db.session.commit()
        
        # Créer une notification
        Notification.create_notification(
            user_id=id,
            title='Mot de passe changé',
            message='Votre mot de passe a été modifié par un administrateur',
            type='info'
        )
        
        return jsonify({
            'success': True,
            'message': 'Mot de passe changé avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur lors du changement: {str(e)}'
        }), 400

@api_bp.route('/users/<int:id>/toggle-status', methods=['PUT'])
def toggle_user_status(id):
    """Active/désactive un utilisateur"""
    try:
        user = User.query.get_or_404(id)
        
        # Empêcher la désactivation de soi-même
        if session.get('user_id') == id:
            return jsonify({
                'success': False,
                'message': 'Vous ne pouvez pas désactiver votre propre compte'
            }), 400
        
        user.is_active = not user.is_active
        db.session.commit()
        
        # Créer une notification
        Notification.create_notification(
            user_id=session.get('user_id'),
            title='Statut utilisateur changé',
            message=f'L\'utilisateur {user.username} a été {"activé" if user.is_active else "désactivé"}',
            type='warning'
        )
        
        return jsonify({
            'success': True,
            'message': f'Utilisateur {"activé" if user.is_active else "désactivé"} avec succès',
            'user': user.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

# ==================== API Notifications ====================

@api_bp.route('/notifications', methods=['GET'])
def get_notifications():
    """Récupère les notifications de l'utilisateur connecté"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({
                'success': False,
                'message': 'Non connecté'
            }), 401
        
        notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(20).all()
        
        return jsonify({
            'success': True,
            'notifications': [n.to_dict() for n in notifications]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/notifications/<int:id>/read', methods=['PUT'])
def mark_notification_read(id):
    """Marque une notification comme lue"""
    try:
        notification = Notification.query.get_or_404(id)
        notification.mark_as_read()
        
        return jsonify({
            'success': True,
            'message': 'Notification marquée comme lue'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/notifications/mark-all-read', methods=['PUT'])
def mark_all_notifications_read():
    """Marque toutes les notifications comme lues"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({
                'success': False,
                'message': 'Non connecté'
            }), 401
        
        notifications = Notification.query.filter_by(user_id=user_id, read=False).all()
        for notification in notifications:
            notification.mark_as_read()
        
        return jsonify({
            'success': True,
            'message': 'Toutes les notifications marquées comme lues'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

# ==================== API Taux de Change ====================

@api_bp.route('/taux-change', methods=['GET'])
def get_taux_change():
    """Récupère tous les taux de change"""
    try:
        taux = TauxChange.query.all()
        return jsonify({
            'success': True,
            'taux_change': [t.to_dict() for t in taux]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/taux-change', methods=['POST'])
def create_taux_change():
    """Crée un nouveau taux de change"""
    try:
        data = request.get_json()
        
        taux = TauxChange(
            devise_source=data.get('devise_source'),
            devise_cible=data.get('devise_cible'),
            taux=float(data.get('taux'))
        )
        
        db.session.add(taux)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Taux de change créé avec succès',
            'taux_change': taux.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/taux-change/<int:id>', methods=['PUT'])
def update_taux_change(id):
    """Met à jour un taux de change"""
    try:
        taux = TauxChange.query.get_or_404(id)
        data = request.get_json()
        
        taux.devise_source = data.get('devise_source', taux.devise_source)
        taux.devise_cible = data.get('devise_cible', taux.devise_cible)
        taux.taux = float(data.get('taux', taux.taux))
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Taux de change mis à jour avec succès',
            'taux_change': taux.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400

@api_bp.route('/taux-change/<int:id>', methods=['DELETE'])
def delete_taux_change(id):
    """Supprime un taux de change"""
    try:
        taux = TauxChange.query.get_or_404(id)
        db.session.delete(taux)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Taux de change supprimé avec succès'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }), 400


@api_bp.route('/statistiques/globales', methods=['GET'])
def get_global_statistics():
    """Statistiques globales : toutes les activités de l'application"""
    try:
        taux_cdf = get_exchange_rate('USD', 'CDF') or 2800.0

        # ─── Ventes ───
        total_ventes = Vente.query.count()
        ventes_completed = Vente.query.filter_by(statut='completed').count()
        credits_en_cours = Vente.query.filter(Vente.statut == 'pending').count()

        ca_cdf = 0.0
        ca_usd = 0.0
        for v in Vente.query.all():
            dev = normalize_devise(v.devise)
            m = v.montant or 0.0
            if dev == 'USD':
                ca_usd += m
                ca_cdf += m * (v.taux_change or taux_cdf)
            else:
                ca_cdf += m
                ca_usd += m / taux_cdf if taux_cdf else 0.0

        today = datetime.utcnow().date()
        ventes_aujourdhui = Vente.query.filter(func.date(Vente.date) == today).count()
        panier_moyen = round(ca_cdf / total_ventes, 0) if total_ventes else 0

        ventes_par_mode = {}
        for v in Vente.query.all():
            mode = v.mode_paiement or 'cash'
            ventes_par_mode[mode] = ventes_par_mode.get(mode, 0) + 1

        ventes_par_statut = {}
        for v in Vente.query.all():
            st = v.statut or 'unknown'
            ventes_par_statut[st] = ventes_par_statut.get(st, 0) + 1

        # ─── Top produits vendus ───
        top_rows = db.session.query(
            ProduitVendu.produit_id,
            func.sum(ProduitVendu.quantite).label('total_qty'),
            func.sum(ProduitVendu.quantite * ProduitVendu.prix_vente).label('total_rev')
        ).group_by(ProduitVendu.produit_id).order_by(func.sum(ProduitVendu.quantite).desc()).limit(10).all()

        top_produits = []
        for row in top_rows:
            p = Produit.query.get(row.produit_id)
            top_produits.append({
                'nom': p.nom if p else 'Produit supprimé',
                'reference': p.reference if p else '',
                'quantite': int(row.total_qty or 0),
                'revenu': round(float(row.total_rev or 0), 2)
            })

        # ─── Stock ───
        produits = Produit.query.all()
        stock_faible = sum(1 for p in produits if p.quantite <= p.stock_min and p.quantite > 0)
        stock_epuise = sum(1 for p in produits if p.quantite == 0)

        valeur_stock_cdf = 0.0
        valeur_stock_usd = 0.0
        for p in produits:
            dev = normalize_devise(p.devise)
            qty = p.quantite or 0
            val = (p.prix_achat or 0.0) * qty
            if dev == 'USD':
                valeur_stock_usd += val
                valeur_stock_cdf += val * taux_cdf
            else:
                valeur_stock_cdf += val
                valeur_stock_usd += val / taux_cdf if taux_cdf else 0.0

        # ─── Caisse ───
        solde_usd = get_caisse_balance('USD')
        solde_cdf = get_caisse_balance('CDF')
        total_entrees_usd = db.session.query(func.coalesce(func.sum(CaisseMovement.montant), 0)).filter(
            CaisseMovement.type == 'in', CaisseMovement.devise == 'USD').scalar() or 0
        total_sorties_usd = db.session.query(func.coalesce(func.sum(CaisseMovement.montant), 0)).filter(
            CaisseMovement.type == 'out', CaisseMovement.devise == 'USD').scalar() or 0
        total_entrees_cdf = db.session.query(func.coalesce(func.sum(CaisseMovement.montant), 0)).filter(
            CaisseMovement.type == 'in', CaisseMovement.devise.in_(['CDF', 'FC', 'XAF'])).scalar() or 0
        total_sorties_cdf = db.session.query(func.coalesce(func.sum(CaisseMovement.montant), 0)).filter(
            CaisseMovement.type == 'out', CaisseMovement.devise.in_(['CDF', 'FC', 'XAF'])).scalar() or 0

        # ─── Utilisateurs ───
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        admin_count = User.query.filter_by(role='admin').count()
        managers_count = User.query.filter_by(role='manager').count()

        # ─── Connexions ───
        total_connexions = LoginLog.query.count()
        reussies = LoginLog.query.filter_by(success=True).count()
        echouees = total_connexions - reussies

        return jsonify({
            'success': True,
            'taux_change': taux_cdf,
            'ventes': {
                'total_ventes': total_ventes,
                'ventes_completed': ventes_completed,
                'credits_en_cours': credits_en_cours,
                'ventes_aujourdhui': ventes_aujourdhui,
                'panier_moyen': panier_moyen,
                'ca_cdf': round(ca_cdf, 2),
                'ca_usd': round(ca_usd, 2),
                'par_mode': ventes_par_mode,
                'par_statut': ventes_par_statut
            },
            'stock': {
                'total_produits': len(produits),
                'stock_faible': stock_faible,
                'stock_epuise': stock_epuise,
                'valeur_cdf': round(valeur_stock_cdf, 2),
                'valeur_usd': round(valeur_stock_usd, 2)
            },
            'caisse': {
                'solde_usd': round(solde_usd, 2),
                'solde_cdf': round(solde_cdf, 2),
                'entrees_usd': round(total_entrees_usd, 2),
                'sorties_usd': round(total_sorties_usd, 2),
                'entrees_cdf': round(total_entrees_cdf, 2),
                'sorties_cdf': round(total_sorties_cdf, 2)
            },
            'users': {
                'total': total_users,
                'actifs': active_users,
                'admins': admin_count,
                'managers': managers_count
            },
            'connexions': {
                'total': total_connexions,
                'reussies': reussies,
                'echouees': echouees
            },
            'top_produits': top_produits
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


# ==================== API Comptabilité (PCGC) ====================

@api_bp.route('/compta/resume', methods=['GET'])
def get_compta_resume():
    """Synthèse comptable : nombre de comptes, écritures, total débit/crédit."""
    try:
        total_comptes = CompteComptable.query.count()
        total_ecritures = EcritureComptable.query.count()
        total_debit = db.session.query(func.coalesce(func.sum(EcritureComptable.montant), 0)).scalar() or 0
        total_credit = total_debit
        last_ecriture = EcritureComptable.query.order_by(EcritureComptable.date.desc()).first()
        return jsonify({
            'success': True,
            'total_comptes': total_comptes,
            'total_ecritures': total_ecritures,
            'total_debit': round(float(total_debit), 2),
            'total_credit': round(float(total_credit), 2),
            'derniere_ecriture': last_ecriture.to_dict() if last_ecriture else None
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/plan-comptable', methods=['GET'])
def get_plan_comptable():
    """Liste le plan comptable congolais avec soldes par compte."""
    try:
        classe = request.args.get('classe', type=int)
        search = request.args.get('search', '').strip()
        avec_soldes = request.args.get('soldes', '1') != '0'
        soldes = soldes_par_compte() if avec_soldes else None
        soldes_by_id = {s['id']: s for s in soldes} if soldes is not None else {}

        query = CompteComptable.query
        if classe:
            query = query.filter_by(classe=classe)
        if search:
            query = query.filter(or_(CompteComptable.numero.like(f'%{search}%'),
                                     CompteComptable.libelle.ilike(f'%{search}%')))
        comptes = query.order_by(CompteComptable.numero).all()

        liste = []
        for c in comptes:
            item = c.to_dict()
            if soldes is not None:
                s = soldes_by_id.get(c.id)
                if s:
                    item.update({'total_debit': s['total_debit'], 'total_credit': s['total_credit'],
                                 'solde_debit': s['solde_debit'], 'solde_credit': s['solde_credit'],
                                 'solde': s['solde']})
                else:
                    item.update({'total_debit': 0.0, 'total_credit': 0.0,
                                 'solde_debit': 0.0, 'solde_credit': 0.0, 'solde': 0.0})
            liste.append(item)

        return jsonify({'success': True, 'comptes': liste})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/plan-comptable/actualiser', methods=['POST'])
def actualiser_plan_comptable():
    """Télécharge / met à jour le plan comptable congolais en base."""
    try:
        created, updated = seed_plan_comptable()
        return jsonify({'success': True, 'created': created, 'updated': updated,
                        'message': f'Plan comptable à jour : {created} créé(s), {updated} mis à jour'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/journal', methods=['GET'])
def get_compta_journal():
    """Livre journal : toutes les écritures avec filtres (période, recherche, source)."""
    try:
        periode = request.args.get('periode', 'all')
        search = request.args.get('search', '').strip()
        source = request.args.get('source', '').strip()
        date_start, date_end = get_report_date_range(periode)

        query = EcritureComptable.query
        if date_start:
            query = query.filter(func.date(EcritureComptable.date) >= date_start,
                                 func.date(EcritureComptable.date) <= date_end)
        if source:
            query = query.filter(EcritureComptable.source == source)
        if search:
            query = query.filter(or_(EcritureComptable.libelle.ilike(f'%{search}%'),
                                     EcritureComptable.numero_piece.like(f'%{search}%')))
        ecritures = query.order_by(EcritureComptable.date.desc(), EcritureComptable.id.desc()).all()

        total_debit = sum(e.montant for e in ecritures)

        return jsonify({
            'success': True,
            'periode': periode,
            'total_ecritures': len(ecritures),
            'total_debit': round(total_debit, 2),
            'total_credit': round(total_debit, 2),
            'ecritures': [e.to_dict() for e in ecritures]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/ecritures', methods=['POST'])
def create_ecriture_manuelle():
    """Enregistre une écriture manuelle au livre journal (débit / crédit)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Données manquantes'}), 400

        compte_debit = data.get('compte_debit')
        compte_credit = data.get('compte_credit')
        montant = float(data.get('montant', 0))
        libelle = data.get('libelle', '').strip()

        if not compte_debit or not compte_credit or compte_debit == compte_credit:
            return jsonify({'success': False, 'message': 'Comptes débit et crédit invalides'}), 400
        if montant <= 0:
            return jsonify({'success': False, 'message': 'Montant invalide'}), 400
        if not libelle:
            return jsonify({'success': False, 'message': 'Libellé obligatoire'}), 400

        c_d = CompteComptable.query.filter_by(numero=str(compte_debit)).first()
        c_c = CompteComptable.query.filter_by(numero=str(compte_credit)).first()
        if not c_d or not c_c:
            return jsonify({'success': False, 'message': 'Compte comptable introuvable'}), 400

        date_str = data.get('date')
        date_ecriture = datetime.fromisoformat(date_str) if date_str else datetime.utcnow()
        devise = normalize_devise(data.get('devise', 'USD'))
        taux_change = float(data.get('taux_change')) if data.get('taux_change') else None

        ecriture = EcritureComptable(
            date=date_ecriture,
            libelle=libelle,
            compte_debit_id=c_d.id,
            compte_credit_id=c_c.id,
            montant=montant,
            devise=devise,
            taux_change=taux_change,
            numero_piece=data.get('numero_piece') or f'E{datetime.utcnow():%Y%m%d%H%M%S}',
            source='manuel',
            user_id=session.get('user_id')
        )
        db.session.add(ecriture)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Écriture comptable enregistrée',
                        'ecriture': ecriture.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/ecritures/<int:id>', methods=['DELETE'])
def delete_ecriture(id):
    """Supprime une écriture manuelle du journal."""
    try:
        ecriture = EcritureComptable.query.get_or_404(id)
        if ecriture.source != 'manuel':
            return jsonify({'success': False,
                            'message': 'Cette écriture provient d\'une activité. Supprimez l\'opération source.'}), 400
        db.session.delete(ecriture)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Écriture supprimée'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/grand-livre', methods=['GET'])
def get_grand_livre():
    """Grand livre d'un compte : toutes les écritures avec solde progressif."""
    try:
        compte_id = request.args.get('compte_id', type=int)
        compte = CompteComptable.query.get_or_404(compte_id)
        ecritures = EcritureComptable.query.filter(
            or_(EcritureComptable.compte_debit_id == compte_id,
                EcritureComptable.compte_credit_id == compte_id)
        ).order_by(EcritureComptable.date, EcritureComptable.id).all()

        solde = 0.0
        lignes = []
        for e in ecritures:
            if e.compte_debit_id == compte_id:
                debit = e.montant
                credit = 0.0
                solde += e.montant
            else:
                debit = 0.0
                credit = e.montant
                solde -= e.montant
            item = e.to_dict()
            item['debit'] = round(debit, 2)
            item['credit'] = round(credit, 2)
            item['solde'] = round(solde, 2)
            lignes.append(item)

        return jsonify({
            'success': True,
            'compte': compte.to_dict(),
            'ecritures': lignes,
            'solde_final': round(solde, 2)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/balance', methods=['GET'])
def get_balance_verification():
    """Balance de vérification : total débit/crédit et solde de chaque compte."""
    try:
        soldes = soldes_par_compte()
        total_debit = sum(s['total_debit'] for s in soldes)
        total_credit = sum(s['total_credit'] for s in soldes)
        return jsonify({
            'success': True,
            'comptes': soldes,
            'total_debit': round(total_debit, 2),
            'total_credit': round(total_credit, 2),
            'equilibre': abs(total_debit - total_credit) < 0.01
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/bilan', methods=['GET'])
def get_bilan():
    """Bilan actif / passif calculé depuis le journal."""
    try:
        taux_cdf = get_exchange_rate('USD', 'CDF') or 2800.0
        soldes = soldes_par_compte()

        actif = []
        passif = []
        charges = []
        produits = []
        total_actif = 0.0
        total_passif = 0.0
        total_charges = 0.0
        total_produits = 0.0

        for s in soldes:
            classe = s['classe']
            solde = s['solde']
            if classe in (2, 3) and solde != 0:
                actif.append({**s, 'montant': round(abs(solde), 2)})
                total_actif += abs(solde)
            elif classe == 5 and solde > 0:
                actif.append({**s, 'montant': round(solde, 2)})
                total_actif += solde
            elif classe == 4 and solde > 0:
                actif.append({**s, 'montant': round(solde, 2)})
                total_actif += solde
            elif classe == 1 and solde != 0:
                passif.append({**s, 'montant': round(abs(solde), 2)})
                total_passif += abs(solde)
            elif classe == 4 and solde < 0:
                passif.append({**s, 'montant': round(abs(solde), 2)})
                total_passif += abs(solde)
            elif classe == 5 and solde < 0:
                passif.append({**s, 'montant': round(abs(solde), 2)})
                total_passif += abs(solde)
            elif classe == 6:
                charges.append({**s, 'montant': round(s['total_debit'], 2)})
                total_charges += s['total_debit']
            elif classe == 7:
                produits.append({**s, 'montant': round(s['total_credit'], 2)})
                total_produits += s['total_credit']

        resultat = round(total_produits - total_charges, 2)

        return jsonify({
            'success': True,
            'taux_change': taux_cdf,
            'actif': actif,
            'passif': passif,
            'charges': charges,
            'produits': produits,
            'total_actif': round(total_actif, 2),
            'total_passif': round(total_passif, 2),
            'total_charges': round(total_charges, 2),
            'total_produits': round(total_produits, 2),
            'resultat': resultat,
            'equilibre': abs(total_actif - (total_passif + resultat)) < 1.0
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/compta/synchroniser', methods=['POST'])
def synchroniser_comptabilite():
    """Génère les écritures comptables manquantes à partir des activités existantes."""
    try:
        total = synchroniser_compta(user_id=session.get('user_id'))
        return jsonify({'success': True, 'ecritures_crees': total,
                        'message': f'{total} écriture(s) comptable(s) générée(s) depuis les activités'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


# ==================== API Paramètres ====================

@api_bp.route('/settings', methods=['GET'])
def get_settings():
    """Retourne tous les paramètres de l'application et l'utilisateur connecté."""
    try:
        params = all_params()
        user = User.query.get(session.get('user_id'))
        return jsonify({
            'success': True,
            'parametres': params,
            'user': user.to_dict() if user else None
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/generaux', methods=['PUT'])
def update_settings_generaux():
    """Enregistre les informations générales de l'entreprise."""
    try:
        data = request.get_json() or {}
        champs = ['nom_entreprise', 'slogan', 'adresse', 'telephone', 'email', 'rccm', 'devise_principale']
        for champ in champs:
            if champ in data:
                set_param(champ, data.get(champ) or '')
        db.session.commit()
        return jsonify({'success': True, 'message': 'Informations générales enregistrées avec succès'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/notifications', methods=['PUT'])
def update_settings_notifications():
    """Enregistre les préférences de notifications."""
    try:
        data = request.get_json() or {}
        for champ in ['notif_email', 'notif_stock_faible', 'notif_nouvelles_ventes', 'notif_son',
                      'alert_sound_type', 'alert_sound_frequency']:
            if champ in data:
                set_param(champ, data.get(champ))
        db.session.commit()
        return jsonify({'success': True, 'message': 'Préférences de notifications enregistrées'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/apparence', methods=['PUT'])
def update_settings_apparence():
    """Enregistre les préférences d'apparence (thème, couleur)."""
    try:
        data = request.get_json() or {}
        for champ in ['theme', 'couleur_principale']:
            if champ in data:
                set_param(champ, data.get(champ))
        db.session.commit()
        return jsonify({'success': True, 'message': 'Apparence mise à jour'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/facture', methods=['PUT'])
def update_settings_facture():
    """Enregistre les paramètres de la facture (design, éléments affichés, images)."""
    try:
        data = request.get_json() or {}

        def to_bool(v):
            return 'true' if str(v).lower() in ('true', '1', 'yes', 'on') else 'false'

        texte = ['facture_design', 'facture_titre', 'facture_mention']
        booleen = ['facture_afficher_entreprise', 'facture_afficher_slogan',
                   'facture_afficher_adresse', 'facture_afficher_telephone',
                   'facture_afficher_email', 'facture_afficher_rccm',
                   'facture_afficher_numero', 'facture_afficher_date',
                   'facture_afficher_mention', 'facture_afficher_signatures']
        image = ['facture_signature_image', 'facture_cachet_image']

        for champ in texte:
            if champ in data:
                set_param(champ, (data.get(champ) or '').strip())
        for champ in booleen:
            if champ in data:
                set_param(champ, to_bool(data.get(champ)))
        for champ in image:
            if champ in data:
                valeur = (data.get(champ) or '').strip()
                if valeur.startswith('data:image'):
                    set_param(champ, valeur)
                else:
                    set_param(champ, '')
        db.session.commit()
        return jsonify({'success': True, 'message': 'Paramètres de la facture enregistrés avec succès'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


# ==================== API Rapports Email ====================

@api_bp.route('/settings/rapports-email', methods=['GET'])
def get_rapports_email_config():
    """Retourne la configuration des rapports email et l'état de la file d'attente."""
    try:
        from app.utils.rapports_email import lire_config_public, etat_file
        cfg = lire_config_public()
        jours = ','.join(str(j) for j in sorted(cfg.get('jours') or []))
        return jsonify({
            'success': True,
            'config': {
                'active': cfg['active'],
                'destinataires': get_param('rapport_email_destinataires', ''),
                'destinataires_effectifs': cfg.get('destinataires') or [],
                'destinataires_source': cfg.get('destinataires_source', 'explicite'),
                'email_entreprise': get_param('email', ''),
                'heure': cfg['heure'],
                'jours': jours,
                'smtp_serveur': cfg['smtp_serveur'],
                'smtp_port': cfg['smtp_port'],
                'smtp_utilisateur': cfg['smtp_utilisateur'],
                'smtp_securite': cfg['smtp_securite'],
                'smtp_expediteur_nom': cfg['smtp_expediteur_nom'],
                'smtp_configure': cfg['smtp_configure'],
            },
            'etat': etat_file()
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/rapports-email', methods=['PUT'])
def update_rapports_email_config():
    """Enregistre la configuration des rapports email et tente un premier envoi."""
    try:
        from app.utils.rapports_email import lire_config, planifier_emails_manquants, envoyer_emails_en_attente
        data = request.get_json() or {}

        etait_active = str(get_param('rapport_email_active', 'false') or '').lower() == 'true'
        devient_active = bool(data.get('active'))
        set_param('rapport_email_active', 'true' if devient_active else 'false')

        for champ in ['rapport_email_destinataires', 'rapport_email_heure',
                      'rapport_email_jours', 'smtp_serveur', 'smtp_port', 'smtp_utilisateur',
                      'smtp_securite', 'smtp_expediteur_nom']:
            if champ in data:
                set_param(champ, data.get(champ))
        # le mot de passe SMTP n'est modifié que si une nouvelle valeur est fournie
        if data.get('smtp_mot_de_passe'):
            set_param('smtp_mot_de_passe', data.get('smtp_mot_de_passe').strip())

        if devient_active and not get_param('rapport_email_active_depuis', ''):
            set_param('rapport_email_active_depuis', datetime.utcnow().strftime('%Y-%m-%d'))
        db.session.commit()

        resultat = {'nb_planifies': 0}
        if devient_active:
            planifies = planifier_emails_manquants()
            envoye = envoyer_emails_en_attente(limite=5)
            resultat = {'nb_planifies': planifies, **envoye}

        message = 'Configuration des rapports email enregistrée.'
        if devient_active:
            if resultat.get('nb_envoyes'):
                message += f" {resultat['nb_envoyes']} rapport(s) envoyé(s) immédiatement."
            if resultat.get('nb_restants'):
                message += f" {resultat['nb_restants']} en attente."
        else:
            message = 'Rapports email désactivés.'
        return jsonify({'success': True, 'message': message, 'resultat': resultat})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/rapports-email/test', methods=['POST'])
def envoyer_rapport_email_test():
    """Envoie un email de test (en utilisant les valeurs du formulaire sans les enregistrer)."""
    try:
        from app.utils.rapports_email import lire_config, envoyer_email_test, \
            _nettoyer_destinataires, _nettoyer_jours
        cfg = lire_config()
        data = request.get_json() or {}
        if 'rapport_email_destinataires' in data:
            fournis = _nettoyer_destinataires(data.get('rapport_email_destinataires'))
            if fournis:
                cfg['destinataires'] = fournis
                cfg['destinataires_source'] = 'explicite'
        if 'rapport_email_heure' in data and data.get('rapport_email_heure'):
            cfg['heure'] = data['rapport_email_heure']
        if 'rapport_email_jours' in data:
            cfg['jours'] = _nettoyer_jours(data.get('rapport_email_jours'))
        for champ, cle in [('smtp_serveur', 'smtp_serveur'), ('smtp_port', 'smtp_port'),
                           ('smtp_utilisateur', 'smtp_utilisateur'), ('smtp_securite', 'smtp_securite'),
                           ('smtp_expediteur_nom', 'smtp_expediteur_nom')]:
            if champ in data and data.get(champ):
                cfg[cle] = data[champ]
        if data.get('smtp_mot_de_passe'):
            cfg['smtp_mot_de_passe'] = data['smtp_mot_de_passe']
        ok, message = envoyer_email_test(cfg)
        return jsonify({'success': ok, 'message': message}), (200 if ok else 400)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/rapports-email/envoyer-maintenant', methods=['POST'])
def envoyer_rapports_maintenant():
    """Planifie puis envoie une partie des rapports en attente (le reste est envoyé automatiquement)."""
    try:
        from app.utils.rapports_email import flush_rapports
        resultat = flush_rapports(limite=50)
        message = f"Envoi terminé : {resultat['nb_envoyes']} envoyé(s), {resultat['nb_erreurs']} en erreur, {resultat['nb_restants']} encore en attente (ils seront envoyés automatiquement dès que possible)."
        return jsonify({'success': True, 'message': message, 'resultat': resultat})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/rapports-email/journal', methods=['GET'])
def get_rapports_email_journal():
    """Liste les derniers emails de rapport (envoyés, en attente, en erreur)."""
    try:
        from app.models.envoi_email import EnvoiEmail
        limite = min(int(request.args.get('limite', 30)), 200)
        emails = EnvoiEmail.query.order_by(EnvoiEmail.date_prevue.desc()).limit(limite).all()
        return jsonify({
            'success': True,
            'emails': [e.to_dict() for e in emails]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/change-password', methods=['PUT'])
def change_own_password():
    """Change le mot de passe de l'utilisateur connecté (avec vérification)."""
    try:
        data = request.get_json() or {}
        user = User.query.get(session.get('user_id'))
        if not user:
            return jsonify({'success': False, 'message': 'Utilisateur introuvable'}), 404

        current = data.get('mot_de_passe_actuel', '')
        nouveau = data.get('nouveau_mot_de_passe', '')
        confirmation = data.get('confirmation', '')

        if not user.check_password(current):
            return jsonify({'success': False, 'message': 'Mot de passe actuel incorrect'}), 400
        if len(nouveau) < 6:
            return jsonify({'success': False, 'message': 'Le nouveau mot de passe doit contenir au moins 6 caractères'}), 400
        if nouveau != confirmation:
            return jsonify({'success': False, 'message': 'Les mots de passe ne correspondent pas'}), 400

        user.set_password(nouveau)
        db.session.commit()

        Notification.create_notification(
            user_id=user.id,
            title='Mot de passe modifié',
            message='Votre mot de passe a été changé avec succès.',
            type='success'
        )
        return jsonify({'success': True, 'message': 'Mot de passe changé avec succès'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/export', methods=['GET'])
def export_donnees():
    """Exporte toutes les données de l'application au format JSON."""
    try:
        donnees = {
            'application': 'MotoStockIA #TUMIKA',
            'date_export': datetime.utcnow().isoformat(),
            'parametres': all_params(),
            'utilisateurs': [u.to_dict() for u in User.query.all()],
            'produits': [p.to_dict() for p in Produit.query.all()],
            'ventes': [v.to_dict() for v in Vente.query.all()],
            'caisse': [m.to_dict() for m in CaisseMovement.query.all()],
            'taux_change': [t.to_dict() for t in TauxChange.query.all()],
            'plan_comptable': [c.to_dict() for c in CompteComptable.query.all()],
            'ecritures_comptables': [e.to_dict() for e in EcritureComptable.query.all()],
            'journal_connexions': [l.to_dict() for l in LoginLog.query.all()]
        }
        nom_fichier = f'motostock_backup_{datetime.utcnow():%Y%m%d_%H%M}.json'
        return Response(
            json.dumps(donnees, ensure_ascii=False, indent=2, default=str),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename={nom_fichier}'}
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/settings/reset-data', methods=['POST'])
def reset_donnees():
    """Supprime toutes les données opérationnelles (ventes, stock, caisse, compta)."""
    try:
        confirmation = (request.get_json() or {}).get('confirmation', '')
        if confirmation != 'SUPPRIMER':
            return jsonify({'success': False, 'message': 'Confirmation invalide. Tapez SUPPRIMER.'}), 400

        EcritureComptable.query.delete()
        CaisseMovement.query.delete()
        ProduitVendu.query.delete()
        Vente.query.delete()
        Produit.query.delete()
        LoginLog.query.delete()
        Notification.query.delete()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Toutes les données opérationnelles ont été supprimées'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


# ==================== API Identification des produits (Vision / OCR / YOLO) ====================

import base64

def _extraire_bytes_image():
    """Extrait les octets d'une image depuis multipart ou base64 JSON."""
    if 'image' in request.files and request.files['image'].filename:
        return request.files['image'].read(), 'image'
    data = request.get_json(silent=True) or {}
    img_b64 = data.get('image') or data.get('image_base64')
    if img_b64:
        # strip data URI si présent
        if ',' in img_b64 and 'base64' in img_b64[:40]:
            img_b64 = img_b64.split(',', 1)[1]
        # limiter la taille décodée (éviter les requêtes abusives)
        if len(img_b64) > 22 * 1024 * 1024:  # ~16 Mo décodés
            return None, 'trop_large'
        return base64.b64decode(img_b64), 'image'
    return None, None

@api_bp.route('/identification/analyse', methods=['POST'])
def identification_analyse():
    """Identifie un produit par image, texte ou code (algorithme combiné)."""
    try:
        data = request.get_json(silent=True) or {}

        if data.get('texte'):
            if len(str(data['texte'])) > 200:
                return jsonify({'success': False, 'message': 'Texte trop long'}), 400
            return jsonify(identifier_par_texte(data['texte']))

        if data.get('code'):
            if len(str(data['code'])) > 128:
                return jsonify({'success': False, 'message': 'Code trop long'}), 400
            return jsonify(identifier_par_code(str(data['code'])))

        image_bytes, statut = _extraire_bytes_image()
        if statut == 'trop_large':
            return jsonify({'success': False, 'message': 'Image trop volumineuse (max 16 Mo)'}), 413
        if image_bytes:
            rapide = request.args.get('rapide') in ('1', 'true', 'True', 'oui')
            return jsonify(analyser_image(image_bytes, rapide=rapide))

        return jsonify({'success': False, 'message': 'Fournissez une image, un texte ou un code.'}), 400

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/identification/confirmer', methods=['POST'])
def identification_confirmer():
    """Enregistre une correction du vendeur (apprentissage)."""
    try:
        data = request.get_json(silent=True) or {}
        cle = (data.get('cle_signature') or '').strip()
        produit_id = data.get('produit_id')
        methode = data.get('methode', 'ocr')
        if not cle or not produit_id:
            return jsonify({'success': False, 'message': 'clé et produit requis'}), 400
        produit = Produit.query.get(produit_id)
        if not produit:
            return jsonify({'success': False, 'message': 'Produit introuvable'}), 404

        CorrectionIdentification.enregistrer(cle, produit_id, methode)
        return jsonify({'success': True, 'message': 'Correction enregistrée (apprentissage)'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/identification/dataset', methods=['POST'])
def identification_dataset():
    """Construit/met à jour le dataset visuel à partir des images des produits."""
    try:
        from app.vision import dataset
        upload_folder = current_app.config['UPLOAD_FOLDER']
        nb = dataset.construire_dataset(upload_folder)
        return jsonify({
            'success': True,
            'message': f'Dataset actualisé : {nb} signature(s) enregistrée(s)',
            'signatures': nb
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/identification/dataset', methods=['GET'])
def identification_dataset_info():
    """État du dataset visuel."""
    try:
        from app.models.identification import ProduitSignature, CorrectionIdentification
        total_produits = Produit.query.count()
        total_signatures = ProduitSignature.query.count()
        total_corrections = CorrectionIdentification.query.count()
        produits_avec_image = Produit.query.filter(
            (Produit.image_url_1.isnot(None)) | (Produit.image_url_2.isnot(None))
        ).count()
        return jsonify({
            'success': True,
            'total_produits': total_produits,
            'produits_avec_image': produits_avec_image,
            'total_signatures': total_signatures,
            'total_corrections': total_corrections,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400


@api_bp.route('/produits/<int:id>/signature', methods=['POST'])
def produit_signature(id):
    """(Re)calcule la signature visuelle d'un produit précis."""
    try:
        produit = Produit.query.get_or_404(id)
        from app.vision import dataset
        upload_folder = current_app.config['UPLOAD_FOLDER']
        nb = dataset.mettre_a_jour_signatures_produit(produit, upload_folder)
        return jsonify({
            'success': True,
            'message': f'{nb} signature(s) enregistrée(s) pour ce produit',
            'signatures': nb
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erreur: {str(e)}'}), 400
