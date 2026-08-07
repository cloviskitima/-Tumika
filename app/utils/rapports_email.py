"""
Rapports quotidiens par email (#TUMIKA).

Fonctionnement :
  - Les rapports sont programmés chaque jour à une heure choisie (avec des jours
    de la semaine possibles).
  - Chaque rapport prévu devient une ligne « EnvoiEmail » (file d'attente).
  - Lorsque l'application est hors ligne, les emails restent en attente ;
    dès qu'elle retrouve l'internet, ils sont envoyés (rattrapage complet,
    même après des mois).
  - Un thread de fond vérifie la file régulièrement.
"""
import threading
import time
import logging
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, formatdate
from datetime import datetime, timedelta, date, time as dt_time

from app import db
from app.models.parametre import get_param, set_param
from app.models.envoi_email import EnvoiEmail
from app.models.produit import Produit
from app.models.vente import Vente, ProduitVendu
from app.models.caisse import CaisseMovement
from app.models.activite_stock import ActiviteStock

logger = logging.getLogger(__name__)

INTERVALLE_CYCLE = 60  # secondes entre chaque vérification
LIMITE_ENVOI_CYCLE = 10  # emails envoyés par cycle (pour ne pas saturer le serveur SMTP)
MAX_TENTATIVES = 5  # tentatives avant de laisser un email en « erreur »

_tache_demarree = False
_verrou_planification = threading.RLock()

JOURS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
LIBELLES_TYPE_ACTIVITE = {
    'creation': 'Créations', 'modification': 'Modifications', 'reapprovisionnement': 'Réapprovisionnements',
    'vente': 'Ventes', 'epuisement': 'Épuisements', 'retour': 'Annulations', 'suppression': 'Suppressions',
}


# ==================== Petits utilitaires ====================

def _devise_norm(d):
    """Regroupe FC/CDF/XAF ensemble, USD à part."""
    if not d:
        return 'USD'
    v = str(d).upper().strip()
    if v in ['FC', 'CDF', 'XAF']:
        return 'CDF'
    if v in ['USD', '$']:
        return 'USD'
    return v


def _fmt_montant(n, devise):
    try:
        return f"{float(n):,.0f}".replace(',', ' ') + ' ' + (_devise_norm(devise))
    except (TypeError, ValueError):
        return '0 ' + devise


def _fmt_date(dt):
    if not dt:
        return '-'
    return dt.strftime('%d/%m/%Y')


def _fmt_dt(dt):
    if not dt:
        return '-'
    return dt.strftime('%d/%m/%Y %H:%M')


def _esc(texte):
    return (texte or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _nettoyer_destinataires(texte):
    """Extrait la liste d'emails à partir d'une chaîne (séparée par virgules, points-virgules ou retours ligne)."""
    resultats = []
    if not texte:
        return resultats
    import re
    for partie in re.split(r'[;,]\s*|\s+', str(texte)):
        partie = partie.strip()
        if partie and '@' in partie:
            resultats.append(partie)
    # dédupliquer en gardant l'ordre
    vus = set()
    return [e for e in resultats if not (e in vus or vus.add(e))]


def _nettoyer_jours(texte):
    """Retourne un ensemble de jours de semaine (1=Lundi..7=Dimanche). Vide = tous les jours."""
    if not texte:
        return set()
    jours = set()
    for p in str(texte).split(','):
        p = p.strip()
        if p.isdigit() and 1 <= int(p) <= 7:
            jours.add(int(p))
    return jours


def _email_entreprise():
    """Email de l'entreprise (paramètre général 'email')."""
    return (get_param('email', '') or '').strip()


def _destinataires_effectifs():
    """Chaîne de décision du destinataire : emails des responsables, sinon adresse SMTP, sinon email entreprise."""
    dests = _nettoyer_destinataires(get_param('rapport_email_destinataires', ''))
    source = 'explicite'
    if not dests:
        smtp_user = (get_param('smtp_utilisateur', '') or '').strip()
        if smtp_user and '@' in smtp_user:
            dests = [smtp_user]
            source = 'smtp_utilisateur'
        else:
            em = _email_entreprise()
            if em:
                dests = [em]
                source = 'entreprise'
    return dests, source


def lire_config():
    """Lit la configuration actuelle des rapports par email (avec le mot de passe SMTP)."""
    dests, source = _destinataires_effectifs()
    return {
        'active': str(get_param('rapport_email_active', 'false') or '').lower() == 'true',
        'destinataires': dests,
        'destinataires_source': source,
        'heure': get_param('rapport_email_heure', '07:00') or '07:00',
        'jours': _nettoyer_jours(get_param('rapport_email_jours', '')),
        'depuis': _parser_date(get_param('rapport_email_active_depuis', '')),
        'smtp_serveur': get_param('smtp_serveur', ''),
        'smtp_port': int(get_param('smtp_port', '587') or 587),
        'smtp_utilisateur': get_param('smtp_utilisateur', ''),
        'smtp_mot_de_passe': get_param('smtp_mot_de_passe', ''),
        'smtp_securite': get_param('smtp_securite', 'starttls') or 'starttls',
        'smtp_expediteur_nom': get_param('smtp_expediteur_nom', '') or get_param('nom_entreprise', 'MotoStockIA'),
    }


def lire_config_public():
    """Configuration sans le mot de passe SMTP (pour l'affichage dans les paramètres)."""
    cfg = lire_config()
    cfg['smtp_mot_de_passe'] = ''
    cfg['smtp_configure'] = bool(cfg['smtp_serveur'] and cfg['smtp_utilisateur'] and
                                 get_param('smtp_mot_de_passe', ''))
    return cfg


def _parser_date(texte):
    if not texte:
        return None
    try:
        return datetime.strptime(str(texte)[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _parser_heure(texte):
    try:
        return datetime.strptime(str(texte)[:5], '%H:%M').time()
    except ValueError:
        return dt_time(7, 0)


# ==================== Construction du rapport ====================

def construire_sujet(date_prevue=None, nom_entreprise='MotoStockIA'):
    base = f'Rapport quotidien {nom_entreprise}'
    if date_prevue:
        base += f' — {date_prevue:%d/%m/%Y}'
    return base


def _agreger_ventes(date_debut, date_fin):
    """Retourne les statistiques des ventes sur la période."""
    ventes = Vente.query.filter(Vente.date >= date_debut, Vente.date <= date_fin).all()

    nb_ventes = len(ventes)
    total_par_devise = {}
    nb_par_devise = {}
    top_produits = {}  # nom -> {qte, montant par devise, categorie}
    benefice_par_devise = {}

    for v in ventes:
        dev = _devise_norm(v.devise)
        total_par_devise[dev] = total_par_devise.get(dev, 0) + (v.montant or 0)
        nb_par_devise[dev] = nb_par_devise.get(dev, 0) + 1
        for pv in v.produits_vendus:
            produit = pv.produit
            nom = produit.nom if produit else f'Produit #{pv.produit_id}'
            info = top_produits.setdefault(nom, {'qte': 0, 'montants': {}, 'categorie': produit.categorie if produit else ''})
            info['qte'] += pv.quantite
            pdev = _devise_norm(produit.devise if produit else v.devise)
            info['montants'][pdev] = info['montants'].get(pdev, 0) + (pv.quantite * (pv.prix_vente or 0))
            benef = ((pv.prix_vente or 0) - (pv.prix_achat or 0)) * pv.quantite
            benefice_par_devise[pdev] = benefice_par_devise.get(pdev, 0) + benef

    top_produits_liste = sorted(top_produits.items(), key=lambda x: -x[1]['qte'])[:8]
    return {
        'nb_ventes': nb_ventes,
        'total_par_devise': total_par_devise,
        'nb_par_devise': nb_par_devise,
        'benefice_par_devise': benefice_par_devise,
        'top_produits': top_produits_liste,
    }


def _agreger_caisse(date_debut, date_fin):
    mouvements = CaisseMovement.query.filter(
        CaisseMovement.date >= date_debut, CaisseMovement.date <= date_fin
    ).all()
    entrees = {}
    sorties = {}
    nb_entrees = nb_sorties = 0
    credits_regles = {}
    nb_credits_regles = 0
    for m in mouvements:
        dev = _devise_norm(m.devise)
        if m.type == 'in':
            entrees[dev] = entrees.get(dev, 0) + (m.montant or 0)
            nb_entrees += 1
            if (m.libelle or '').startswith('Paiement crédit'):
                credits_regles[dev] = credits_regles.get(dev, 0) + (m.montant or 0)
                nb_credits_regles += 1
        else:
            sorties[dev] = sorties.get(dev, 0) + (m.montant or 0)
            nb_sorties += 1
    return {
        'nb_mouvements': len(mouvements),
        'nb_entrees': nb_entrees,
        'nb_sorties': nb_sorties,
        'entrees': entrees,
        'sorties': sorties,
        'nb_credits_regles': nb_credits_regles,
        'credits_regles': credits_regles,
    }


def _agreger_activites(date_debut, date_fin):
    activites = ActiviteStock.query.filter(
        ActiviteStock.date >= date_debut, ActiviteStock.date <= date_fin
    ).all()
    compteur = {}
    for a in activites:
        compteur[a.type] = compteur.get(a.type, 0) + 1
    return {'total': len(activites), 'compteur': compteur}


def _agreger_credits(date_debut, date_fin):
    octroyes = Vente.query.filter(
        Vente.date >= date_debut, Vente.date <= date_fin,
        (Vente.mode_paiement == 'credit') | (Vente.statut == 'pending')
    ).all()
    octroyes_par_devise = {}
    for v in octroyes:
        dev = _devise_norm(v.devise)
        octroyes_par_devise[dev] = octroyes_par_devise.get(dev, 0) + (v.montant or 0)
    restants = Vente.query.filter(
        (Vente.statut == 'pending') | (Vente.mode_paiement == 'credit')
    ).all()
    restants_par_devise = {}
    for v in restants:
        dev = _devise_norm(v.devise)
        restants_par_devise[dev] = restants_par_devise.get(dev, 0) + (v.montant or 0)
    return {
        'nb_octroyes': len(octroyes),
        'octroyes_par_devise': octroyes_par_devise,
        'nb_restants': len(restants),
        'restants_par_devise': restants_par_devise,
    }


def _etat_stock():
    produits = Produit.query.all()
    faible = []
    epuises = []
    for p in produits:
        if p.quantite == 0:
            epuises.append(p)
        elif p.quantite <= (p.stock_min or 0):
            faible.append(p)
    faible.sort(key=lambda x: x.quantite)
    return {'faible': faible[:8], 'epuises': epuises[:8], 'nb_faible': len(faible), 'nb_epuises': len(epuises)}


def _html_entete(cfg, date_prevue, date_debut, date_fin):
    nom = _esc(cfg['smtp_expediteur_nom'] or get_param('nom_entreprise', 'MotoStockIA'))
    return f"""
    <div style="background:linear-gradient(135deg,#0f172a,#1e3a8a);border-radius:14px;padding:26px 30px;color:#ffffff;">
      <div style="font-size:13px;opacity:0.85;">{nom} — rapport automatique</div>
      <div style="font-size:24px;font-weight:800;margin-top:4px;">📊 Rapport quotidien</div>
      <div style="font-size:13px;opacity:0.92;margin-top:8px;">
        Programmé pour le <b>{_fmt_date(date_prevue)}</b> — Période couverte :
        du <b>{_fmt_date(date_debut)}</b> au <b>{_fmt_date(date_fin)}</b>
      </div>
    </div>"""


def _html_section(titre, contenu):
    return f"""
    <div style="border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;margin-top:18px;">
      <div style="background:#f8fafc;padding:11px 16px;font-weight:800;font-size:14px;color:#0f172a;border-bottom:1px solid #e5e7eb;">{titre}</div>
      <div style="padding:14px 16px;">{contenu}</div>
    </div>"""


def _html_kpi(libelle, valeur):
    return f"""
    <td style="width:25%;padding:8px;">
      <div style="background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:11px;color:#64748b;font-weight:600;">{libelle}</div>
        <div style="font-size:17px;font-weight:800;color:#0f172a;margin-top:3px;">{valeur}</div>
      </div>
    </td>"""


def _html_table(entetes, lignes):
    thead = ''.join(f'<th style="padding:8px 10px;text-align:left;font-size:12px;color:#475569;font-weight:700;background:#f8fafc;">{h}</th>' for h in entetes)
    corps = ''
    for ligne in lignes:
        corps += '<tr>' + ''.join(
            f'<td style="padding:7px 10px;border-top:1px solid #f1f5f9;font-size:13px;color:#334155;">{c}</td>' for c in ligne
        ) + '</tr>'
    if not corps:
        corps = '<tr><td colspan="%d" style="padding:12px;text-align:center;color:#94a3b8;font-size:13px;">Aucune donnée</td></tr>' % len(entetes)
    return f'<table style="width:100%;border-collapse:collapse;">{thead}{corps}</table>'


def construire_rapport_html(cfg, date_prevue, date_debut, date_fin):
    """Construit le corps HTML complet du rapport quotidien."""
    ventes = _agreger_ventes(date_debut, date_fin)
    caisse = _agreger_caisse(date_debut, date_fin)
    activites = _agreger_activites(date_debut, date_fin)
    credits = _agreger_credits(date_debut, date_fin)
    stock = _etat_stock()

    # KPI
    kpi_total = []
    if ventes['nb_ventes']:
        kpi_total.append(_html_kpi('Ventes (journée)', f"{ventes['nb_ventes']}"))
        for dev in sorted(ventes['total_par_devise']):
            kpi_total.append(_html_kpi('Montant ' + dev, _fmt_montant(ventes['total_par_devise'][dev], dev)))
    else:
        kpi_total.append(_html_kpi('Ventes (journée)', '0'))
    for dev in sorted(ventes['benefice_par_devise']):
        kpi_total.append(_html_kpi('Bénéfice ' + dev, _fmt_montant(ventes['benefice_par_devise'][dev], dev)))
    kpi_html = '<table style="width:100%;border-collapse:collapse;">' + ''.join(kpi_total) + '</table>'

    # Top produits
    lignes_top = []
    for nom, info in ventes['top_produits']:
        montants = ', '.join(f"{_fmt_montant(m, d)}" for d, m in sorted(info['montants'].items()))
        lignes_top.append([_esc(nom), _esc(info['categorie'] or '-'), str(info['qte']), montants])
    top_html = _html_table(['Produit', 'Catégorie', 'Qté vendue', 'Montant'], lignes_top)

    # Caisse
    ligne_caisse = []
    entrees_str = ' · '.join(f"{_fmt_montant(m, d)}" for d, m in sorted(caisse['entrees'].items())) or '0'
    sorties_str = ' · '.join(f"{_fmt_montant(m, d)}" for d, m in sorted(caisse['sorties'].items())) or '0'
    if caisse['nb_mouvements'] or entrees_str or sorties_str:
        ligne_caisse.append(_html_table(['', 'Entrées', 'Sorties', 'Mouvements'],
                                        [['Caisse', entrees_str, sorties_str, str(caisse['nb_mouvements'])]]))
        if caisse['nb_credits_regles']:
            credits_regles_str = ' · '.join(f"{_fmt_montant(m, d)}" for d, m in sorted(caisse['credits_regles'].items()))
            ligne_caisse.append(_html_table(['Crédits réglés'],
                                            [[credits_regles_str + f" ({caisse['nb_credits_regles']} paiement(s))"]]))
    caisse_html = ''.join(ligne_caisse) or '<div style="color:#94a3b8;">Aucun mouvement de caisse sur la période.</div>'

    # Activités stock
    activites_lignes = []
    for t, lib in LIBELLES_TYPE_ACTIVITE.items():
        n = activites['compteur'].get(t, 0)
        if n:
            activites_lignes.append([lib, str(n)])
    activites_html = _html_table(['Activité', 'Nombre'], activites_lignes) if activites_lignes else \
        '<div style="color:#94a3b8;">Aucune activité de stock sur la période.</div>'

    # Stock faible / épuisé
    stock_lignes = []
    for p in stock['faible']:
        stock_lignes.append([_esc(p.nom), p.quantite, '⚠️ Stock faible'])
    for p in stock['epuises']:
        stock_lignes.append([_esc(p.nom), '0', '🚫 Épuisé'])
    stock_html = _html_table(['Produit', 'Stock actuel', 'Alerte'], stock_lignes) if stock_lignes else \
        '<div style="color:#94a3b8;">Aucun stock faible ni épuisé. 👍</div>'

    # Crédits
    octroyes_str = ' · '.join(f"{_fmt_montant(m, d)}" for d, m in sorted(credits['octroyes_par_devise'].items())) or '0'
    restants_str = ' · '.join(f"{_fmt_montant(m, d)}" for d, m in sorted(credits['restants_par_devise'].items())) or '0'
    credits_html = _html_table(['Crédits octroyés', 'Total restant dû'],
                               [[f"{octroyes_str} ({credits['nb_octroyes']})", f"{restants_str} ({credits['nb_restants']})"]])

    generated = datetime.utcnow()
    return f"""<!DOCTYPE html>
<html lang="fr"><body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:20px;">
    {_html_entete(cfg, date_prevue, date_debut, date_fin)}
    {_html_section('Résumé du jour', kpi_html)}
    {_html_section('🛒 Produits les plus vendus', top_html)}
    {_html_section('💵 Caisse (entrées / sorties)', caisse_html)}
    {_html_section('📦 Activités de stock', activites_html)}
    {_html_section('🚨 Stock faible & épuisé', stock_html)}
    {_html_section('🧾 Crédits (octroyés / dus)', credits_html)}
    <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:22px;">
      Généré automatiquement par #TUMIKA le {_fmt_dt(generated)}. Ceci est un message automatique, merci de ne pas y répondre.
    </div>
  </div>
</body></html>"""


# ==================== Planification ====================

def _dates_jours_souhaites(cfg, aujourdhui):
    """Génère toutes les dates (jours) devant recevoir un rapport, de l'activation jusqu'à aujourd'hui."""
    depuis = cfg['depuis'] or (aujourdhui - timedelta(days=1))
    if depuis > aujourdhui:
        depuis = aujourdhui
    jours = cfg['jours']
    d = depuis
    while d <= aujourdhui:
        if (not jours) or (d.isoweekday() in jours):
            yield d
        d += timedelta(days=1)


def planifier_emails_manquants():
    """Crée les lignes EnvoiEmail manquantes pour les jours programmés (idempotent)."""
    cfg = lire_config()
    if not cfg['active']:
        return 0
    dests = cfg['destinataires']
    if not dests:
        return 0
    heure = _parser_heure(cfg['heure'])
    maintenant = datetime.utcnow()
    ajoutes = 0

    with _verrou_planification:
        for jour in _dates_jours_souhaites(cfg, maintenant.date()):
            prevue = datetime.combine(jour, heure)
            if jour == maintenant.date() and prevue > maintenant:
                continue  # l'heure du jour n'est pas encore arrivée
            for dest in dests:
                existe = EnvoiEmail.query.filter_by(destinataire=dest, date_prevue=prevue).first()
                if existe:
                    continue
                debut = datetime.combine(jour - timedelta(days=1), dt_time(0, 0, 0))
                fin = datetime.combine(jour, dt_time(0, 0, 0)) - timedelta(seconds=1)
                db.session.add(EnvoiEmail(
                    destinataire=dest,
                    sujet=construire_sujet(prevue, cfg['smtp_expediteur_nom']),
                    date_prevue=prevue,
                    date_debut=debut,
                    date_fin=fin,
                    statut='en_attente',
                ))
                ajoutes += 1
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return ajoutes


# ==================== Envoi SMTP ====================

def _envoyer_smtp(cfg, destinataire, sujet, html):
    """Envoie un email via SMTP. Retourne (ok, message_erreur)."""
    serveur = (cfg.get('smtp_serveur') or '').strip()
    utilisateur = (cfg.get('smtp_utilisateur') or '').strip()
    # Les mots de passe d'application Gmail s'affichent avec des espaces ; on les retire
    # (ainsi qu'éventuels espaces collés autour) avant l'authentification.
    mot_de_passe = (cfg.get('smtp_mot_de_passe') or '').strip().replace(' ', '')
    if not serveur or not utilisateur:
        return False, 'Configuration SMTP incomplète (serveur ou utilisateur manquant).'
    port = int(cfg.get('smtp_port') or 587)
    securite = cfg.get('smtp_securite') or 'starttls'
    nom_expediteur = cfg.get('smtp_expediteur_nom') or get_param('nom_entreprise', 'MotoStockIA')

    message = MIMEMultipart('alternative')
    message['Subject'] = sujet
    message['From'] = formataddr((nom_expediteur, utilisateur))
    message['To'] = destinataire
    message['Date'] = formatdate(localtime=True)
    message.attach(MIMEText('Rapport quotidien — ouvrez cet email dans votre messagerie pour voir le rapport.', 'plain', 'utf-8'))
    message.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        if securite == 'ssl':
            smtp = smtplib.SMTP_SSL(serveur, port, timeout=25)
        else:
            smtp = smtplib.SMTP(serveur, port, timeout=25)
            smtp.ehlo()
            if securite == 'starttls':
                smtp.starttls()
                smtp.ehlo()
        try:
            if mot_de_passe:
                smtp.login(utilisateur, mot_de_passe)
            smtp.sendmail(utilisateur, [destinataire], message.as_string())
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
        return True, None
    except smtplib.SMTPAuthenticationError as e:
        return False, f'Erreur d’authentification SMTP : {e.smtp_error or e}'
    except (smtplib.SMTPException, OSError, socket.error) as e:
        return False, f'Connexion SMTP impossible ({type(e).__name__}) : {e}'
    except Exception as e:
        return False, f'Erreur inconnue : {e}'


def _envoyer_un(email, cfg):
    """Envoie un EnvoiEmail donné. Met à jour statut et tentatives."""
    email.nb_tentatives = (email.nb_tentatives or 0) + 1
    email.derniere_tentative = datetime.utcnow()
    sujet = email.sujet or construire_sujet(email.date_prevue, cfg['smtp_expediteur_nom'])
    html = construire_rapport_html(cfg, email.date_prevue, email.date_debut, email.date_fin)
    ok, erreur = _envoyer_smtp(cfg, email.destinataire, sujet, html)
    if ok:
        email.statut = 'envoye'
        email.date_envoi = datetime.utcnow()
        email.erreur = None
        return True
    email.erreur = erreur[:500]
    if email.nb_tentatives >= MAX_TENTATIVES:
        email.statut = 'erreur'
    else:
        email.statut = 'en_attente'  # on retentera plus tard (hors ligne / panne passagère)
    return False


def _requeue_erreurs():
    """Remet en file les emails en erreur pour les retenter (jusqu'au max de tentatives)."""
    for e in EnvoiEmail.query.filter(EnvoiEmail.statut == 'erreur').all():
        if e.nb_tentatives < MAX_TENTATIVES:
            e.statut = 'en_attente'
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def envoyer_emails_en_attente(limite=None):
    """Envoie les emails en attente. Retourne les compteurs."""
    cfg = lire_config()
    if not cfg['active']:
        return {'nb_envoyes': 0, 'nb_erreurs': 0, 'nb_restants': 0}
    if not (cfg['smtp_serveur'] and cfg['smtp_utilisateur'] and cfg['smtp_mot_de_passe']):
        set_param('rapport_email_derniere_erreur', 'Configuration SMTP incomplète — envois en attente.')
        db.session.commit()
        return {'nb_envoyes': 0, 'nb_erreurs': 0, 'nb_restants': EnvoiEmail.query.filter_by(statut='en_attente').count()}

    requete = EnvoiEmail.query.filter_by(statut='en_attente').order_by(EnvoiEmail.date_prevue.asc())
    total_restants = requete.count()
    a_envoyer = requete.limit(limite if limite else total_restants).all()

    nb_envoyes = 0
    nb_erreurs = 0
    derniere_erreur = None
    for email in a_envoyer:
        if _envoyer_un(email, cfg):
            nb_envoyes += 1
        else:
            nb_erreurs += 1
            derniere_erreur = email.erreur
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        time.sleep(1.5)  # espace les envois (politesse serveur SMTP)

    if derniere_erreur:
        set_param('rapport_email_derniere_erreur', derniere_erreur)
    elif nb_envoyes:
        set_param('rapport_email_dernier_envoi', datetime.utcnow().isoformat())
        set_param('rapport_email_derniere_erreur', '')
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    restants_apres = EnvoiEmail.query.filter_by(statut='en_attente').count()
    return {'nb_envoyes': nb_envoyes, 'nb_erreurs': nb_erreurs, 'nb_restants': restants_apres}


def envoyer_email_test(config_override=None):
    """Envoie un email de test (petit message) au premier destinataire configuré."""
    cfg = lire_config()
    if config_override:
        cfg.update(config_override)
    if not cfg['destinataires']:
        return False, ("Aucun email destinataire. Renseignez l'email des responsables ci-dessus, "
                       "ou l'adresse d'envoi SMTP, ou l'email de l'entreprise (Paramètres → Entreprise).")
    if not (cfg['smtp_serveur'] and cfg['smtp_utilisateur'] and cfg['smtp_mot_de_passe']):
        return False, 'Configuration SMTP incomplète : renseignez serveur, utilisateur et mot de passe.'

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,Helvetica,sans-serif;background:#f1f5f9;padding:20px;">
  <div style="max-width:520px;margin:auto;background:#ffffff;border-radius:12px;padding:24px;border:1px solid #e5e7eb;">
    <h2 style="margin:0 0 6px;color:#0f172a;">✅ Email de test — {_esc(cfg['smtp_expediteur_nom'])}</h2>
    <p style="color:#475569;font-size:14px;line-height:1.6;">
      Votre configuration est opérationnelle !<br>
      L'application vous enverra désormais le rapport quotidien du stock et des ventes aux adresses
      programmées. Ce message confirme simplement que les emails partent bien.
    </p>
    <p style="color:#94a3b8;font-size:12px;">Envoyé le {_fmt_dt(datetime.utcnow())} par #TUMIKA.</p>
  </div>
</body></html>"""
    sujet = f"Test — Rapport automatique {_esc(cfg['smtp_expediteur_nom'])}"
    ok, erreur = _envoyer_smtp(cfg, cfg['destinataires'][0], sujet, html)
    return ok, (erreur or 'Email de test envoyé avec succès.')


def etat_file():
    """État de la file d'attente (pour l'interface)."""
    en_attente = EnvoiEmail.query.filter_by(statut='en_attente').count()
    envoyes = EnvoiEmail.query.filter_by(statut='envoye').count()
    erreurs = EnvoiEmail.query.filter_by(statut='erreur').count()
    dernier = EnvoiEmail.query.filter_by(statut='envoye').order_by(EnvoiEmail.date_envoi.desc()).first()
    derniere_erreur = get_param('rapport_email_derniere_erreur', '')
    return {
        'en_attente': en_attente,
        'envoyes': envoyes,
        'erreurs': erreurs,
        'total': en_attente + envoyes + erreurs,
        'dernier_envoi': dernier.date_envoi.isoformat() if dernier and dernier.date_envoi else None,
        'derniere_erreur': derniere_erreur or None,
    }


# ==================== Tâche de fond ====================

def flush_rapports(limite=None):
    """Planifie les emails manquants puis envoie ce qui est possible. Utilisé au démarrage et manuellement."""
    with _verrou_planification:
        planifie = planifier_emails_manquants()
        resultat = envoyer_emails_en_attente(limite=limite)
    resultat['nb_planifies'] = planifie
    return resultat


def _boucle_tache(app, arret):
    logger.info('Tâche de fond « rapports email » démarrée.')
    while not arret.is_set():
        try:
            with app.app_context():
                _requeue_erreurs()
                planifier_emails_manquants()
                envoyer_emails_en_attente(limite=LIMITE_ENVOI_CYCLE)
        except Exception:
            logger.exception('Erreur dans la tâche de fond des rapports email')
        arret.wait(INTERVALLE_CYCLE)


def demarrer_tache_rapports_email(app):
    """Démarre (une seule fois) le thread de fond qui envoie les rapports programmés."""
    global _tache_demarree
    if _tache_demarree:
        return
    _tache_demarree = True
    arret = threading.Event()
    app._arret_rapports_email = arret
    t = threading.Thread(target=_boucle_tache, args=(app, arret), daemon=True, name='rapports-email')
    t.start()
