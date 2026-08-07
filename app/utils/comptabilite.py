"""
Module Comptabilité : Plan Comptable Général Congolais (PCGC) et écritures comptables.
Permet de générer automatiquement les écritures du livre journal à partir des
activités de l'entreprise (ventes, caisse, crédits) ainsi que des écritures manuelles.
"""
from datetime import datetime
from app import db
from app.models.comptabilite import CompteComptable, EcritureComptable
from app.models.vente import Vente
from app.models.caisse import CaisseMovement

# Plan Comptable Général Congolais (PCGC)
# Structure : (numero, libelle, classe, nature)  -- nature = solde normal du compte
PLAN_COMPTABLE = [
    # ─── CLASSE 1 : Comptes de capitaux ───
    ('101', 'Capital social', 1, 'credit'),
    ('102', 'Capital personnel', 1, 'credit'),
    ('104', 'Primes d\'apport et de fusion', 1, 'credit'),
    ('106', 'Réserves', 1, 'credit'),
    ('1061', 'Réserve légale', 1, 'credit'),
    ('107', 'Report à nouveau', 1, 'credit'),
    ('108', 'Compte de l\'exploitant', 1, 'credit'),
    ('11', 'Comptes de liaison', 1, 'debit'),
    ('12', 'Résultat de l\'exercice', 1, 'credit'),
    ('13', 'Subventions d\'investissement', 1, 'credit'),
    ('14', 'Provisions réglementées', 1, 'credit'),
    ('15', 'Provisions pour risques et charges', 1, 'credit'),
    ('16', 'Emprunts et dettes assimilées', 1, 'credit'),
    ('161', 'Emprunts auprès des établissements de crédit', 1, 'credit'),
    ('165', 'Dépôts et cautionnements reçus', 1, 'credit'),
    ('17', 'Dettes de location-acquisition', 1, 'credit'),
    ('18', 'Dettes liées à des participations', 1, 'credit'),
    ('19', 'Provisions financières', 1, 'credit'),

    # ─── CLASSE 2 : Comptes d'immobilisations ───
    ('20', 'Frais d\'établissement', 2, 'debit'),
    ('201', 'Frais de constitution', 2, 'debit'),
    ('21', 'Immobilisations incorporelles', 2, 'debit'),
    ('212', 'Brevets, licences et marques', 2, 'debit'),
    ('213', 'Fonds commercial', 2, 'debit'),
    ('22', 'Immobilisations corporelles', 2, 'debit'),
    ('220', 'Terrains', 2, 'debit'),
    ('221', 'Constructions', 2, 'debit'),
    ('222', 'Installations techniques, matériel et outillage', 2, 'debit'),
    ('223', 'Matériel de transport', 2, 'debit'),
    ('224', 'Matériel informatique', 2, 'debit'),
    ('225', 'Mobilier et matériel de bureau', 2, 'debit'),
    ('226', 'Agencements et aménagements', 2, 'debit'),
    ('23', 'Immobilisations en cours', 2, 'debit'),
    ('24', 'Immobilisations de placement', 2, 'debit'),
    ('25', 'Participations et créances immobilisées', 2, 'debit'),
    ('27', 'Autres immobilisations financières', 2, 'debit'),
    ('28', 'Amortissements des immobilisations', 2, 'credit'),
    ('281', 'Amortissements des immobilisations incorporelles', 2, 'credit'),
    ('282', 'Amortissements des immobilisations corporelles', 2, 'credit'),
    ('29', 'Provisions pour dépréciation des immobilisations', 2, 'credit'),

    # ─── CLASSE 3 : Comptes de stocks ───
    ('31', 'Matières premières', 3, 'debit'),
    ('32', 'Autres approvisionnements', 3, 'debit'),
    ('33', 'En-cours de production', 3, 'debit'),
    ('35', 'Stocks de produits', 3, 'debit'),
    ('352', 'Produits finis', 3, 'debit'),
    ('37', 'Stocks de marchandises', 3, 'debit'),
    ('38', 'Approvisionnements', 3, 'debit'),
    ('39', 'Provisions pour dépréciation des stocks', 3, 'credit'),

    # ─── CLASSE 4 : Comptes de tiers ───
    ('40', 'Fournisseurs et comptes rattachés', 4, 'credit'),
    ('401', 'Fournisseurs', 4, 'credit'),
    ('404', 'Fournisseurs d\'immobilisations', 4, 'credit'),
    ('41', 'Clients et comptes rattachés', 4, 'debit'),
    ('410', 'Clients', 4, 'debit'),
    ('413', 'Effets à recevoir', 4, 'debit'),
    ('418', 'Clients, produits à recevoir', 4, 'debit'),
    ('42', 'Personnel et comptes rattachés', 4, 'debit'),
    ('421', 'Personnel, avances et acomptes', 4, 'debit'),
    ('425', 'Personnel, rémunérations dues', 4, 'credit'),
    ('43', 'État et organismes de sécurité sociale', 4, 'credit'),
    ('431', 'État, impôts et taxes', 4, 'credit'),
    ('437', 'Organismes de sécurité sociale', 4, 'credit'),
    ('45', 'Comptes de trésorerie et de concours bancaires', 4, 'credit'),
    ('46', 'Comptes de l\'exploitant', 4, 'debit'),
    ('47', 'Créances et dettes diverses', 4, 'debit'),
    ('48', 'Comptes de régularisation', 4, 'debit'),
    ('481', 'Charges à payer', 4, 'credit'),
    ('486', 'Produits à recevoir', 4, 'debit'),
    ('487', 'Charges constatées d\'avance', 4, 'debit'),
    ('488', 'Produits constatés d\'avance', 4, 'credit'),
    ('49', 'Provisions pour dépréciation des comptes de tiers', 4, 'credit'),

    # ─── CLASSE 5 : Comptes financiers ───
    ('50', 'Valeurs mobilières de placement', 5, 'debit'),
    ('51', 'Banques, établissements financiers et assimilés', 5, 'debit'),
    ('511', 'Banque', 5, 'debit'),
    ('512', 'Banque, comptes en devises', 5, 'debit'),
    ('52', 'Instruments de trésorerie', 5, 'debit'),
    ('53', 'Caisse', 5, 'debit'),
    ('531', 'Caisse (FC)', 5, 'debit'),
    ('532', 'Caisse (USD)', 5, 'debit'),
    ('54', 'Régies d\'avances et accréditifs', 5, 'debit'),
    ('55', 'Virements internes', 5, 'debit'),
    ('57', 'Comptes de disponibilités', 5, 'debit'),
    ('58', 'Virements de fonds', 5, 'debit'),
    ('59', 'Provisions pour dépréciation des comptes financiers', 5, 'credit'),

    # ─── CLASSE 6 : Comptes de charges ───
    ('60', 'Achats', 6, 'debit'),
    ('601', 'Achats de marchandises', 6, 'debit'),
    ('602', 'Achats de matières premières', 6, 'debit'),
    ('603', 'Achats de fournitures', 6, 'debit'),
    ('605', 'Achats non stockés', 6, 'debit'),
    ('61', 'Transports', 6, 'debit'),
    ('611', 'Transports sur achats', 6, 'debit'),
    ('613', 'Transports sur ventes', 6, 'debit'),
    ('62', 'Autres services extérieurs', 6, 'debit'),
    ('621', 'Locations et charges locatives', 6, 'debit'),
    ('622', 'Entretien et réparations', 6, 'debit'),
    ('623', 'Rémunérations d\'intermédiaires', 6, 'debit'),
    ('624', 'Publicité, publications', 6, 'debit'),
    ('625', 'Déplacements et missions', 6, 'debit'),
    ('626', 'Frais postaux et de télécommunications', 6, 'debit'),
    ('627', 'Frais bancaires et assimilés', 6, 'debit'),
    ('628', 'Frais de formation', 6, 'debit'),
    ('63', 'Impôts, taxes et versements assimilés', 6, 'debit'),
    ('631', 'Impôts et taxes directs', 6, 'debit'),
    ('632', 'Impôts et taxes indirects', 6, 'debit'),
    ('64', 'Charges de personnel', 6, 'debit'),
    ('641', 'Rémunérations du personnel', 6, 'debit'),
    ('644', 'Charges sociales', 6, 'debit'),
    ('65', 'Autres charges opérationnelles', 6, 'debit'),
    ('66', 'Charges financières', 6, 'debit'),
    ('661', 'Intérêts des emprunts', 6, 'debit'),
    ('67', 'Charges exceptionnelles', 6, 'debit'),
    ('68', 'Dotation aux amortissements et provisions', 6, 'debit'),
    ('681', 'Dotation aux amortissements', 6, 'debit'),
    ('686', 'Dotation aux provisions', 6, 'debit'),
    ('69', 'Impôts sur les résultats', 6, 'debit'),
    ('691', 'Impôts sur les bénéfices', 6, 'debit'),

    # ─── CLASSE 7 : Comptes de produits ───
    ('70', 'Ventes', 7, 'credit'),
    ('701', 'Ventes de marchandises', 7, 'credit'),
    ('702', 'Ventes de produits finis', 7, 'credit'),
    ('703', 'Ventes de services', 7, 'credit'),
    ('71', 'Production stockée', 7, 'credit'),
    ('72', 'Production immobilisée', 7, 'credit'),
    ('73', 'Subventions d\'exploitation', 7, 'credit'),
    ('74', 'Autres produits opérationnels', 7, 'credit'),
    ('75', 'Produits financiers', 7, 'credit'),
    ('751', 'Intérêts des placements', 7, 'credit'),
    ('76', 'Produits exceptionnels', 7, 'credit'),
    ('77', 'Reprises sur amortissements et provisions', 7, 'credit'),
    ('78', 'Transferts de charges', 7, 'credit'),

    # ─── CLASSE 8 : Résultats ───
    ('80', 'Résultat de l\'exercice (bénéfice)', 8, 'credit'),
    ('81', 'Résultat en instance d\'affectation', 8, 'credit'),
    ('85', 'Apports de l\'exercice', 8, 'credit'),
    ('86', 'Prélèvements de l\'exercice', 8, 'debit'),
    ('89', 'Résultats et réserves', 8, 'credit'),

    # ─── CLASSE 9 : Engagements hors bilan ───
    ('90', 'Engagements donnés', 9, 'debit'),
    ('91', 'Engagements reçus', 9, 'debit'),
    ('92', 'Engagements réciproques', 9, 'debit'),
    ('93', 'Engagements pour le compte de tiers', 9, 'debit'),
]

CLASSES_PCGC = {
    1: 'Capitaux',
    2: 'Immobilisations',
    3: 'Stocks',
    4: 'Tiers',
    5: 'Financiers',
    6: 'Charges',
    7: 'Produits',
    8: 'Résultats',
    9: 'Engagements hors bilan',
}


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


def seed_plan_comptable():
    """Crée ou met à jour le plan comptable congolais en base de données."""
    created = 0
    updated = 0
    for numero, libelle, classe, nature in PLAN_COMPTABLE:
        compte = CompteComptable.query.filter_by(numero=numero).first()
        if compte:
            if compte.libelle != libelle or compte.classe != classe or compte.nature != nature:
                compte.libelle = libelle
                compte.classe = classe
                compte.nature = nature
                updated += 1
        else:
            db.session.add(CompteComptable(
                numero=numero, libelle=libelle, classe=classe, nature=nature
            ))
            created += 1
    db.session.commit()
    return created, updated


def get_compte(numero):
    """Retourne un compte par son numéro."""
    return CompteComptable.query.filter_by(numero=str(numero)).first()


def compte_caisse(devise):
    """Retourne le numéro du compte caisse selon la devise."""
    return '532' if normalize_devise(devise) == 'USD' else '531'


def compte_existe(numero):
    return CompteComptable.query.filter_by(numero=str(numero)).first() is not None


def add_ecriture(date, libelle, compte_debit, compte_credit, montant,
                 devise='USD', taux_change=None, numero_piece=None,
                 source='manuel', source_id=None, user_id=None):
    """Ajoute une écriture au journal (sans commit)."""
    if montant <= 0:
        return None
    compte_d = get_compte(compte_debit)
    compte_c = get_compte(compte_credit)
    if not compte_d or not compte_c:
        return None
    ecriture = EcritureComptable(
        date=date,
        libelle=libelle,
        compte_debit_id=compte_d.id,
        compte_credit_id=compte_c.id,
        montant=float(montant),
        devise=normalize_devise(devise),
        taux_change=taux_change,
        numero_piece=numero_piece,
        source=source,
        source_id=source_id,
        user_id=user_id
    )
    db.session.add(ecriture)
    return ecriture


def ecriture_existe(source, source_id):
    return EcritureComptable.query.filter_by(source=source, source_id=source_id).first()


def generation_vente(vente, user_id=None):
    """Génère l'écriture comptable d'une vente (comptant ou crédit)."""
    if ecriture_existe('vente', vente.id):
        return None
    dev = normalize_devise(vente.devise)
    num_caisse = compte_caisse(dev)
    if vente.statut == 'pending' or vente.mode_paiement == 'credit':
        compte_debit = '410'  # Clients
        source = 'vente_credit'
    else:
        compte_debit = num_caisse  # Caisse
        source = 'vente'
    libelle = f'Vente n°{vente.id} - {vente.client or "Client comptant"}'
    return add_ecriture(
        date=vente.date or datetime.utcnow(),
        libelle=libelle,
        compte_debit=compte_debit,
        compte_credit='701',  # Ventes de marchandises
        montant=vente.montant,
        devise=dev,
        taux_change=vente.taux_change,
        numero_piece=f'V{vente.id:06d}',
        source=source,
        source_id=vente.id,
        user_id=user_id
    )


def maj_ecriture_vente(vente):
    """Met à jour le montant de l'écriture d'une vente modifiée."""
    ecriture = ecriture_existe('vente', vente.id) or ecriture_existe('vente_credit', vente.id)
    if ecriture:
        ecriture.montant = vente.montant
        ecriture.libelle = f'Vente n°{vente.id} - {vente.client or "Client"}'
        return ecriture
    return None


def generation_paiement_credit(vente, montant, caisse_mouvement=None, user_id=None):
    """Génère l'écriture du paiement d'une vente à crédit."""
    if ecriture_existe('vente_paiement', vente.id):
        return None
    dev = normalize_devise(vente.devise)
    num_caisse = compte_caisse(dev)
    return add_ecriture(
        date=caisse_mouvement.date if caisse_mouvement and caisse_mouvement.date else datetime.utcnow(),
        libelle=f'Paiement crédit Vente n°{vente.id}',
        compte_debit=num_caisse,      # Caisse
        compte_credit='410',          # Clients
        montant=montant,
        devise=dev,
        taux_change=vente.taux_change,
        numero_piece=f'R{vente.id:06d}',
        source='vente_paiement',
        source_id=vente.id,
        user_id=user_id
    )


def generation_caisse(mouvement, user_id=None):
    """Génère l'écriture comptable d'un mouvement de caisse manuel."""
    if ecriture_existe('caisse', mouvement.id):
        return None
    dev = normalize_devise(mouvement.devise)
    num_caisse = compte_caisse(dev)
    if mouvement.type == 'in':
        compte_debit = num_caisse
        compte_credit = '74'  # Autres produits opérationnels
    else:
        compte_debit = '62'   # Autres services extérieurs
        compte_credit = num_caisse
    return add_ecriture(
        date=mouvement.date or datetime.utcnow(),
        libelle=mouvement.libelle or f'Mouvement {mouvement.type}',
        compte_debit=compte_debit,
        compte_credit=compte_credit,
        montant=mouvement.montant,
        devise=dev,
        taux_change=mouvement.taux_change,
        numero_piece=f'C{mouvement.id:06d}',
        source='caisse',
        source_id=mouvement.id,
        user_id=user_id
    )


def synchroniser_compta(user_id=None):
    """Crée les écritures manquantes à partir de toutes les activités existantes."""
    total = 0
    for vente in Vente.query.all():
        if ecriture_existe('vente', vente.id) or ecriture_existe('vente_credit', vente.id):
            continue
        if generation_vente(vente, user_id=user_id):
            total += 1
    for mvt in CaisseMovement.query.filter_by(vente_id=None).all():
        if ecriture_existe('caisse', mvt.id):
            continue
        if generation_caisse(mvt, user_id=user_id):
            total += 1
    if total:
        db.session.commit()
    return total


def soldes_par_compte():
    """Calcule les soldes (débit/crédit) de chaque compte à partir du journal."""
    from sqlalchemy import func
    debits = dict(db.session.query(
        EcritureComptable.compte_debit_id,
        func.sum(EcritureComptable.montant)
    ).group_by(EcritureComptable.compte_debit_id).all())
    credits = dict(db.session.query(
        EcritureComptable.compte_credit_id,
        func.sum(EcritureComptable.montant)
    ).group_by(EcritureComptable.compte_credit_id).all())

    resultats = []
    for compte in CompteComptable.query.order_by(CompteComptable.classe, CompteComptable.numero).all():
        total_debit = round(float(debits.get(compte.id, 0) or 0), 2)
        total_credit = round(float(credits.get(compte.id, 0) or 0), 2)
        solde = round(total_debit - total_credit, 2)
        resultats.append({
            'id': compte.id,
            'numero': compte.numero,
            'libelle': compte.libelle,
            'classe': compte.classe,
            'nature': compte.nature,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'solde_debit': solde if solde > 0 else 0.0,
            'solde_credit': abs(solde) if solde < 0 else 0.0,
            'solde': solde
        })
    return resultats
