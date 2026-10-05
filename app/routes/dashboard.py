"""Routes du tableau de bord : indicateurs et series pour les graphiques.

Tout est calcule en base et renvoye en JSON, pour que les graphiques
fonctionnent entierement en local, sans service externe.

La serie principale est au format OHLC (ouverture / plus haut / plus bas /
cloture) par jour, convertie en une seule devise : c'est ce qui permet
d'afficher un vrai graphique en chandeliers, comme sur les plateformes
de marche.
"""
from datetime import date as date_cls, datetime, timedelta

from flask import jsonify, request

from app import db
from app.models.produit import Produit
from app.models.vente import Vente
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.routes.api import api_bp, get_exchange_rate

# Nombre de jours couverts par chaque periode proposee dans le tableau de bord
PERIODES = {
    '7j': 7,
    '30j': 30,
    '90j': 90,
    '365j': 365,
}


def _montant_xaf(vente):
    """Convertit le montant d'une vente en francs CFA."""
    try:
        montant = float(vente.montant or 0)
    except (TypeError, ValueError):
        return 0.0
    if (vente.devise or 'XAF').upper() in ('USD', '$'):
        taux = vente.taux_change or get_exchange_rate('USD', 'XAF', vente.date)
        try:
            taux = float(taux)
        except (TypeError, ValueError):
            taux = 0.0
        return montant * taux if taux else montant
    return montant


def _chiffre_affaires_ventes(ventes):
    return round(sum(_montant_xaf(v) for v in ventes), 0)


@api_bp.route('/dashboard/serie', methods=['GET'])
def dashboard_serie():
    """Indicateurs + serie OHLC + repartition du stock pour le tableau de bord."""
    try:
        periode = (request.args.get('periode') or '30j').lower()
        nb_jours = PERIODES.get(periode, 30)
        today = date_cls.today()
        debut = today - timedelta(days=nb_jours - 1)

        # ---------------------------------------------------------- ventes
        # joinedload : les lignes de vente sont chargees en meme temps, donc
        # le calcul des meilleurs produits ne relance pas une requete par ligne
        ventes = Vente.query.options(joinedload(Vente.produits_vendus)).filter(
            Vente.date >= datetime.combine(debut, datetime.min.time())
        ).order_by(Vente.date.asc()).all()

        # Regroupement par jour
        par_jour = {}
        for v in ventes:
            cle = (v.date.date() if v.date else today)
            par_jour.setdefault(cle, []).append(v)

        candles = []
        for i in range(nb_jours):
            jour = debut + timedelta(days=i)
            du_jour = par_jour.get(jour, [])
            montants = [_montant_xaf(v) for v in du_jour]
            if montants:
                ouverture = round(montants[0], 0)
                plus_haut = round(max(montants), 0)
                plus_bas = round(min(montants), 0)
                cloture = round(montants[-1], 0)
            else:
                ouverture = plus_haut = plus_bas = cloture = 0.0
            candles.append({
                'ts': int(datetime.combine(jour, datetime.min.time()).timestamp() * 1000),
                'jour': jour.isoformat(),
                'o': ouverture,
                'h': plus_haut,
                'b': plus_bas,
                'c': cloture,
                'v': len(du_jour),
                'ca': round(sum(montants), 0),
            })

        # ------------------------------------------------------ indicateurs
        ventes_aujourdhui = Vente.query.filter(
            func.date(Vente.date) == today
        ).all()
        ca_jour = _chiffre_affaires_ventes(ventes_aujourdhui)

        toutes_ventes = Vente.query.all()
        ca_total = _chiffre_affaires_ventes(toutes_ventes)
        panier_moyen = round(ca_total / len(toutes_ventes), 0) if toutes_ventes else 0

        # Periode precedente de meme longueur, pour la variation
        debut_prec = debut - timedelta(days=nb_jours)
        ventes_prec = Vente.query.filter(
            Vente.date >= datetime.combine(debut_prec, datetime.min.time()),
            Vente.date < datetime.combine(debut, datetime.min.time())
        ).all()
        ca_periode = _chiffre_affaires_ventes(ventes)
        ca_periode_prec = _chiffre_affaires_ventes(ventes_prec)
        if ca_periode_prec > 0:
            variation = round((ca_periode - ca_periode_prec) / ca_periode_prec * 100, 1)
        else:
            variation = 100.0 if ca_periode > 0 else 0.0

        # ---------------------------------------------------------- stock
        # Taux courant : il sert a ramener le stock dans une seule devise, car
        # le stock n'a pas de date de vente associee.
        taux_usd = get_exchange_rate('USD', 'XAF') or 0
        try:
            taux_usd = float(taux_usd)
        except (TypeError, ValueError):
            taux_usd = 0.0

        produits = Produit.query.all()
        produits_par_id = {p.id: p for p in produits}
        valeur_stock_xaf = 0.0
        valeur_stock_usd = 0.0
        alertes = 0
        par_categorie = {}
        for p in produits:
            valeur = float(p.prix_achat or 0) * int(p.quantite or 0)
            if (p.devise or 'XAF').upper() in ('USD', '$'):
                valeur_stock_usd += valeur
                # On convertit pour que toutes les parts du donut soient
                # comparables entre elles (et cohérentes avec l'indicant)
                valeur_xaf = valeur * taux_usd if taux_usd else valeur
            else:
                valeur_stock_xaf += valeur
                valeur_xaf = valeur
            if p.quantite is not None and p.quantite <= (p.stock_min or 0):
                alertes += 1
            cat = (p.categorie or 'Non classé').strip() or 'Non classé'
            c = par_categorie.setdefault(cat, {'categorie': cat, 'produits': 0,
                                               'quantite': 0, 'valeur': 0.0})
            c['produits'] += 1
            c['quantite'] += int(p.quantite or 0)
            c['valeur'] += valeur_xaf

        repartition = sorted(par_categorie.values(),
                             key=lambda x: x['valeur'], reverse=True)[:8]
        for c in repartition:
            c['valeur'] = round(c['valeur'], 0)

        # Valeur totale du stock en une seule devise, pour un indicant unique
        valeur_stock_totale = round(valeur_stock_xaf + valeur_stock_usd * taux_usd, 0)

        # ------------------------------------------------- meilleurs produits
        # Sur la periode choisie, comme l'annonce le graphique.
        # Le montant de chaque ligne est converti avec le taux de la vente
        # elle-meme : c'est la devise reellement encaissee.
        ca_par_produit = {}
        for v in ventes:
            taux_vente = v.taux_change
            if (v.devise or 'XAF').upper() in ('USD', '$'):
                if not taux_vente:
                    taux_vente = get_exchange_rate('USD', 'XAF', v.date)
                try:
                    taux_vente = float(taux_vente)
                except (TypeError, ValueError):
                    taux_vente = 0.0
            else:
                taux_vente = 1.0

            for lv in v.produits_vendus:
                brut = float(lv.quantite or 0) * float(lv.prix_vente or 0)
                net = max(0.0, brut - float(lv.remise or 0))
                if taux_vente:
                    net = net * taux_vente
                cle = lv.produit_id or 0
                ca_par_produit[cle] = ca_par_produit.get(cle, 0.0) + net

        top = sorted(ca_par_produit.items(), key=lambda x: x[1], reverse=True)[:6]
        meilleurs = []
        for pid, ca in top:
            p = produits_par_id.get(pid)
            if p is None:
                continue
            meilleurs.append({
                'id': p.id,
                'nom': p.nom,
                'reference': p.reference,
                'ca': round(ca, 0),
                'quantite': int(p.quantite or 0),
            })

        return jsonify({
            'success': True,
            'periode': periode,
            'jours': nb_jours,
            'devise': 'XAF',
            'taux_usd': taux_usd,
            'candles': candles,
            'indicateurs': {
                'ventes_jour': len(ventes_aujourdhui),
                'ca_jour': ca_jour,
                'ca_total': ca_total,
                'panier_moyen': panier_moyen,
                'ca_periode': ca_periode,
                'variation_periode': variation,
                'produits': len(produits),
                'valeur_stock': valeur_stock_totale,
                'valeur_stock_xaf': round(valeur_stock_xaf, 0),
                'valeur_stock_usd': round(valeur_stock_usd, 0),
                'alertes_stock': alertes,
            },
            'repartition_stock': repartition,
            'meilleurs_produits': meilleurs,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Erreur tableau de bord : {str(e)}'
        }), 400
