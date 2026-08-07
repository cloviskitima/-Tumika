"""
Backfill de l'historique des activités de stock.

Lorsque la table `activite_stock` est vide (premier lancement après l'ajout
du module), on reconstitue l'historique à partir des données existantes :
- création de chaque produit
- ventes passées (avec stock avant/après reconstitué) + épuisements
- réapprovisionnements enregistrés

La reconstitution part du stock actuel et "remonte" le temps événement par
événement. C'est une approximation raisonnable de l'historique réel.
"""
from datetime import datetime
from app import db
from app.models.produit import Produit
from app.models.vente import ProduitVendu, Vente
from app.models.reapprovisionnement import Reapprovisionnement
from app.models.activite_stock import ActiviteStock


def backfill_activites_stock():
    """Reconstitue l'historique des activités de stock si la table est vide."""
    if db.session.query(ActiviteStock.id).first() is not None:
        return 0

    produits = Produit.query.all()
    reaps = db.session.query(Reapprovisionnement).order_by(Reapprovisionnement.date.asc()).all()
    pv_lignes = (
        db.session.query(ProduitVendu)
        .join(Vente, ProduitVendu.vente_id == Vente.id)
        .order_by(Vente.date.asc(), ProduitVendu.id.asc())
        .all()
    )

    # Événements par produit : (date, type, quantite, client)
    evenements = {}
    for pv in pv_lignes:
        vente = pv.vente
        client = (vente.client or '').strip() or 'Client comptant'
        evenements.setdefault(pv.produit_id, []).append(
            (vente.date or vente.id, 'vente', pv.quantite, client, pv.id)
        )
    for r in reaps:
        evenements.setdefault(r.produit_id, []).append(
            (r.date or r.id, 'reapprovisionnement', r.quantite, '', r.id)
        )

    produits_by_id = {p.id: p for p in produits}
    total = 0

    for pid, evts in evenements.items():
        p = produits_by_id.get(pid)
        if p is None:
            continue
        evts.sort(key=lambda e: e[0])
        stock = p.quantite
        logs = []
        for date_e, type_e, qte, client, _ in reversed(evts):
            if type_e == 'vente':
                avant = stock + qte
                logs.append(('vente', avant, stock,
                             f"Vente de {qte} unité(s) à {client} — stock {avant} → {stock}", date_e))
                if stock == 0 and avant > 0:
                    logs.append(('epuisement', avant, 0,
                                 f"Stock épuisé après la vente à {client}", date_e))
                stock = avant
            elif type_e == 'reapprovisionnement':
                avant = stock - qte
                logs.append(('reapprovisionnement', avant, stock,
                             f"Réapprovisionnement : ajout de +{qte} unités — stock {avant} → {stock}", date_e))
                stock = avant
        logs.reverse()
        # Création initiale du produit
        logs.insert(0, ('creation', 0, stock,
                        "Produit présent dans l'inventaire (historique reconstitué)", evts[0][0]))
        for type_l, avant, apres, desc, date_e in logs:
            db.session.add(ActiviteStock(
                produit_id=pid,
                type=type_l,
                quantite_avant=avant,
                quantite_apres=apres,
                variation=apres - avant,
                description=desc,
                date=date_e if isinstance(date_e, datetime) else None
            ))
            total += 1

    # Produits sans aucun événement : simple création avec le stock actuel
    for p in produits:
        if p.id not in evenements:
            db.session.add(ActiviteStock(
                produit_id=p.id,
                type='creation',
                quantite_avant=0,
                quantite_apres=p.quantite or 0,
                variation=p.quantite or 0,
                description="Produit présent dans l'inventaire (historique reconstitué)"
            ))
            total += 1

    db.session.commit()
    return total
