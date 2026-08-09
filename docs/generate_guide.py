# -*- coding: utf-8 -*-
"""
Génération du manuel PDF MotoStockIA #TUMIKA
- Couverture colorée
- Sommaire automatique
- Toutes les fonctionnalités avec captures d'écran
- Technologies
- Annexes juridiques RDC (contrat de licence, contrat développeur/utilisateur, certificat de sécurité, page PDG)
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white, Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Image, PageBreak, Table, TableStyle,
                                Flowable, NextPageTemplate, KeepTogether)
from reportlab.platypus.tableofcontents import TableOfContents
from PIL import Image as PILImage

# ----------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------
PROJ = r'C:\Users\kitima\Desktop\#Tumika'
CAP = os.path.join(PROJ, 'docs', 'captures')
OUT_PDF = os.path.join(PROJ, 'docs', 'Guide_MotoStockIA_TUMIKA.pdf')
TMP = r'C:\Users\kitima\AppData\Local\Temp\opencode\pdf_tmp'
os.makedirs(TMP, exist_ok=True)

W, H = A4
MARGIN = 1.8 * cm
C_PRIM = HexColor('#1e3a8a')    # bleu foncé
C_PRIM2 = HexColor('#1d4ed8')
C_ACCENT = HexColor('#eab308')  # or
C_GREEN = HexColor('#059669')
C_DARK = HexColor('#0f172a')
C_GRAY = HexColor('#64748b')
C_LIGHT = HexColor('#f1f5f9')
C_RED = HexColor('#dc2626')
C_LINE = HexColor('#e2e8f0')

# ----------------------------------------------------------------------
# Polices
# ----------------------------------------------------------------------
def reg(fname, name):
    p = os.path.join(os.environ['WINDIR'], 'Fonts', fname)
    if os.path.exists(p):
        pdfmetrics.registerFont(TTFont(name, p))

reg('segoeui.ttf', 'Segoe')
reg('segoeuib.ttf', 'SegoeB')
reg('segoeuil.ttf', 'SegoeL')
reg('arialbi.ttf', 'ArialIt')

F = 'Segoe'
FB = 'SegoeB'
FI = 'ArialIt'

# ----------------------------------------------------------------------
# Styles
# ----------------------------------------------------------------------
def st(name, **kw):
    base = dict(fontName=F, fontSize=10, leading=14.5, textColor=HexColor('#1e293b'),
                alignment=TA_JUSTIFY, spaceAfter=6)
    base.update(kw)
    return ParagraphStyle(name, **base)

S_H1 = st('h1', fontName=FB, fontSize=20, leading=25, textColor=white,
          alignment=TA_LEFT, spaceAfter=0, spaceBefore=0)
S_H2 = st('h2', fontName=FB, fontSize=13.5, leading=17, textColor=C_PRIM,
          alignment=TA_LEFT, spaceBefore=14, spaceAfter=5)
S_BODY = st('body')
S_BODY_S = st('bodys', fontSize=9.5, leading=13.5)
S_CAP = st('cap', fontSize=8.5, leading=11, textColor=C_GRAY, alignment=TA_CENTER, spaceAfter=2)
S_TOC = st('toc', fontSize=10.5, leading=16, textColor=C_DARK, alignment=TA_LEFT, spaceAfter=2)
S_TOC2 = st('toc2', fontSize=9.5, leading=14, textColor=C_GRAY, alignment=TA_LEFT, spaceAfter=1, leftIndent=16)
S_TITLE_ANNEXE = st('annexe', fontName=FB, fontSize=15, leading=19, textColor=white,
                    alignment=TA_LEFT, spaceAfter=0)

# ----------------------------------------------------------------------
# Flowables personnalisés
# ----------------------------------------------------------------------
class SectionHeader(Flowable):
    """Bandeau de titre de section coloré."""
    def __init__(self, number, title, subtitle=None, skip_toc=False):
        Flowable.__init__(self)
        self.number = number
        self.title = title
        self.subtitle = subtitle
        self.skip_toc = skip_toc
        self.width = W - 2 * MARGIN
        self.height = 1.55 * cm if subtitle else 1.15 * cm

    def wrap(self, aw, ah):
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        x0, x1 = 0, self.width
        # fond
        c.setFillColor(C_PRIM)
        c.roundRect(x0, 0, x1, self.height, 8, stroke=0, fill=1)
        # bande or
        c.setFillColor(C_ACCENT)
        c.rect(x0, 0, 0.18 * cm, self.height, stroke=0, fill=1)
        # numéro
        if self.number:
            c.setFillColor(C_ACCENT)
            c.setFont(FB, 22)
            c.drawString(0.65 * cm, self.height - 0.62 * cm, self.number)
        # titre
        c.setFillColor(white)
        c.setFont(FB, 15)
        tx = (1.75 * cm) if self.number else (0.55 * cm)
        c.drawString(tx, self.height - 0.95 * cm, self.title)
        if self.subtitle:
            c.setFont(F, 8.5)
            c.setFillColor(Color(1, 1, 1, alpha=0.85))
            c.drawString(tx, self.height - 1.32 * cm, self.subtitle)

class RoundedBox(Flowable):
    """Boîte d'information arrondie colorée."""
    def __init__(self, text, bg=HexColor('#eff6ff'), border=C_PRIM2, icon=None, width=None):
        Flowable.__init__(self)
        self.text = text
        self.bg = bg
        self.border = border
        self.icon = icon
        self.width = width or (W - 2 * MARGIN)
        self.height = None
        self._para = Paragraph(self.text, st('infobox', fontSize=9.5, leading=13.5, textColor=HexColor('#1e293b')))

    def wrap(self, aw, ah):
        w, h = self._para.wrap(self.width - 1.1 * cm, ah)
        self.height = h + 0.7 * cm
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(self.bg)
        c.setStrokeColor(self.border)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, self.width, self.height, 7, stroke=1, fill=1)
        if self.icon:
            c.setFont(F, 11)
            c.setFillColor(self.border)
            c.drawString(0.28 * cm, self.height - 0.55 * cm, self.icon)
        self._para.wrapOn(c, self.width - 1.1 * cm, self.height)
        self._para.drawOn(c, 0.6 * cm, 0.35 * cm)
        c.restoreState()

LANDSCAPE_RATIO = 0.78  # hauteur = largeur x 0.78 -> format paysage

def img_flowable(path, max_w=None):
    """Recadre chaque capture en format paysage et l'étire sur toute la largeur."""
    max_w = max_w or (W - 2 * MARGIN)
    im = PILImage.open(path)
    w, h = im.size
    ratio = h / w
    tmp = None
    if ratio > LANDSCAPE_RATIO:
        new_h = int(w * LANDSCAPE_RATIO)
        if new_h < h:
            im2 = im.crop((0, 0, w, new_h))
            tmp = os.path.join(TMP, os.path.basename(path))
            im2.save(tmp)
            im = im2
            w, h = im.size
            ratio = h / w
    disp_w = max_w
    disp_h = disp_w * ratio
    return Image(tmp if tmp else path, width=disp_w, height=disp_h)

def figure(path, caption=None):
    """Image paysage pleine largeur + légende centrée."""
    im = img_flowable(path)
    el = []
    t = Table([[im]], colWidths=[W - 2 * MARGIN])
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    el.append(t)
    if caption:
        el.append(Paragraph(caption, S_CAP))
    el.append(Spacer(1, 10))
    return el

def bullets(items, style=None):
    stl = style or S_BODY_S
    out = []
    for it in items:
        out.append(Paragraph('&#8226; ' + it, stl))
    return out

# ----------------------------------------------------------------------
# Template de document avec sommaire
# ----------------------------------------------------------------------
class Doc(BaseDocTemplate):
    def __init__(self, fn, **kw):
        BaseDocTemplate.__init__(self, fn, pagesize=A4,
                                 leftMargin=MARGIN, rightMargin=MARGIN,
                                 topMargin=1.7 * cm, bottomMargin=1.6 * cm, **kw)
        self._toc_entries = []

    def draw_bg(self, canv, doc):
        canv.saveState()
        # entête
        canv.setStrokeColor(C_LINE)
        canv.setLineWidth(0.6)
        canv.line(MARGIN, H - 1.35 * cm, W - MARGIN, H - 1.35 * cm)
        canv.setFont(F, 7.5)
        canv.setFillColor(C_GRAY)
        canv.drawString(MARGIN, H - 1.15 * cm, 'MotoStockIA — #TUMIKA')
        canv.drawRightString(W - MARGIN, H - 1.15 * cm, 'Manuel d\'utilisation & Guide complet')
        # pied de page
        canv.line(MARGIN, 1.25 * cm, W - MARGIN, 1.25 * cm)
        canv.setFont(F, 8)
        canv.setFillColor(C_GRAY)
        canv.drawCentredString(W / 2, 0.85 * cm, 'Page %d' % doc.page)
        canv.drawString(MARGIN, 0.85 * cm, 'Version 1.0 — République Démocratique du Congo')
        canv.drawRightString(W - MARGIN, 0.85 * cm, 'Confidentiel')
        canv.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, SectionHeader):
            if getattr(flowable, 'skip_toc', False):
                return
            num = flowable.number
            label = (num + '. ' if num else '') + flowable.title
            self.notify('TOCEntry', (0, label, self.page))
        elif isinstance(flowable, Paragraph):
            sty = getattr(flowable, 'style', None)
            if sty is not None:
                name = sty.name
                text = flowable.getPlainText().strip()
                if name == 'h2':
                    self.notify('TOCEntry', (1, text, self.page))

def toc_heading(level, text):
    if level == 0:
        return Paragraph(text, S_TOC)
    return Paragraph(text, S_TOC2)

# ----------------------------------------------------------------------
# Construction du sommaire
# ----------------------------------------------------------------------
def make_toc():
    toc = TableOfContents()
    toc.dotsMinLevel = 0
    toc.levelStyles = [S_TOC, S_TOC2]
    toc.delimiter = ' . '
    return toc

# ----------------------------------------------------------------------
# Contenu
# ----------------------------------------------------------------------
def build():
    story = []
    toc = make_toc()

    # ===================== SOMMAIRE =====================
    story.append(Spacer(1, 0.2 * cm))
    story.append(SectionHeader(None, 'Sommaire', skip_toc=True))
    story.append(Spacer(1, 12))
    story.append(toc)
    story.append(PageBreak())

    # ===================== 1. INTRODUCTION =====================
    story.append(SectionHeader('1', 'Présentation de l\'application',
                               'Qu\'est-ce que MotoStockIA #TUMIKA et ce qu\'elle peut faire pour vous'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        '<b>MotoStockIA (#TUMIKA)</b> est une application complète de gestion commerciale '
        'développée en <b>République Démocratique du Congo</b>. Elle permet à un commerce '
        '(boutique de pièces moto, quincaillerie, supermarché, pharmacie…) de gérer au '
        'quotidien son <b>stock</b>, ses <b>ventes</b>, sa <b>caisse</b>, ses <b>clients</b>, '
        'ses <b>dettes et crédits</b>, ainsi que sa <b>comptabilité</b> — le tout dans une '
        'seule application simple, rapide et pensée pour fonctionner même hors connexion.', S_BODY))
    story.append(Paragraph(
        'Le nom <b>#TUMIKA</b> évoque la force et la solidité. L\'application a été conçue '
        'pour être utilisée par des commerçants et des chefs d\'entreprise congolais, avec '
        'une interface en français, un support des deux devises (<b>FC</b> et <b>USD</b>) et '
        'des fonctionnalités avancées d\'<b>intelligence artificielle</b> : reconnaissance '
        'de produits par photo, lecture de code-barres et OCR.', S_BODY))
    story.append(Spacer(1, 4))
    story.append(RoundedBox(
        '<b>Ce manuel vous guide pas à pas :</b> installation, connexion, utilisation de '
        'chaque module (avec captures d\'écran), technologies employées, puis les annexes '
        'juridiques : contrat de licence, contrat développeur/utilisateur et certificat de '
        'sécurité.', bg=HexColor('#fefce8'), border=HexColor('#ca8a04'), icon='&#9888;'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('1.1. À qui s\'adresse l\'application ?', S_H2))
    story.extend(bullets([
        '<b>Gérants de boutiques et magasins</b> qui veulent suivre leur stock et leurs ventes.',
        '<b>Commerçants</b> qui accordent des crédits et des dettes à leurs clients.',
        '<b>Comptables et gestionnaires</b> qui ont besoin de rapports fiables et d\'une comptabilité simple.',
        '<b>Entreprises</b> qui veulent recevoir automatiquement leurs rapports par email.',
    ]))

    story.append(Paragraph('1.2. Les 9 modules principaux', S_H2))
    mods = [
        ['Module', 'Rôle'],
        ['Tableau de bord', 'Vue d\'ensemble de l\'activité : chiffre d\'affaires, bénéfice, alertes stock.'],
        ['Stock', 'Produits, quantités, prix, stock minimal, alertes, scan par photo (IA).'],
        ['Ventes', 'Enregistrement des ventes en FC et en USD, tickets et historique.'],
        ['Caisse', 'Entrées et sorties d\'argent, solde en FC et USD, mouvements.'],
        ['Rapports', '7 rapports : capital, synthèse, produits, réappro, activités, clients, dettes.'],
        ['Statistiques', 'Analyses chiffrées de l\'évolution de l\'activité.'],
        ['Comptabilité', 'Plan comptable, journal, grand livre, balance, bilan (OHADA).'],
        ['Utilisateurs', 'Comptes du personnel avec rôles et permissions.'],
        ['Paramètres', 'Entreprise, sécurité, notifications, taux de change, apparence, emails.'],
    ]
    t = Table(mods, colWidths=[3.4 * cm, (W - 2 * MARGIN - 3.4 * cm)])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIM),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), FB),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -1), F),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ===================== 2. DÉMARRAGE =====================
    story.append(SectionHeader('2', 'Démarrage rapide', 'Installation, lancement et première connexion'))
    story.append(Spacer(1, 10))
    story.append(Paragraph('2.1. Installation', S_H2))
    story.extend(bullets([
        'Installer <b>Python 3.12+</b> (Windows 64 bits recommandé).',
        'Installer les dépendances Python : <font face="Segoe">python -m pip install -r requirements.txt</font>',
        'Installer <b>Tesseract OCR 5.x</b> (lecture de texte sur les photos d\'étiquettes).',
        'Le modèle <b>YOLOv8</b> et les langues OCR (français/anglais) sont fournis avec le projet.',
        'Initialiser la base de données et lancer l\'application (voir 2.2).',
    ]))
    story.append(Paragraph('2.2. Lancement', S_H2))
    story.extend(bullets([
        'Lancer le serveur : <font face="Segoe">python app.py</font>',
        'L\'application est alors disponible dans le navigateur à l\'adresse <b>http://127.0.0.1:5000</b>.',
        'Un compte administrateur est créé lors de la première installation.',
        'Connectez-vous avec vos identifiants (voir 2.3).',
    ]))
    story.append(Paragraph('2.3. Connexion', S_H2))
    story.extend(bullets([
        'Saisissez votre <b>adresse email</b> (ou nom d\'utilisateur) et votre <b>mot de passe</b>.',
        'En cas d\'erreurs répétées, la connexion est temporairement bloquée (protection anti force brute).',
        'Chaque connexion est consignée dans un journal de sécurité consultable.',
    ]))
    story.extend(figure(os.path.join(CAP, '01_login.png'),
                        'Écran de connexion — accès sécurisé par identifiants'))
    story.append(Paragraph('2.4. Structure générale de l\'application', S_H2))
    story.append(Paragraph(
        'Une fois connecté, un <b>menu latéral</b> permet de naviguer entre les modules : '
        '<b>Tableau de bord</b>, <b>Stock</b>, <b>Ventes</b>, <b>Caisse</b>, <b>Rapports</b>, '
        '<b>Statistiques</b>, <b>Comptabilité</b>, <b>Utilisateurs</b> et <b>Paramètres</b>. '
        'Chaque écran est conçu pour rester simple et lisible sur ordinateur comme sur tablette.', S_BODY))
    story.extend(figure(os.path.join(CAP, '02_dashboard.png'),
                        'Tableau de bord — point d\'entrée de l\'application'))
    story.append(PageBreak())

    # ===================== 3. TABLEAU DE BORD =====================
    story.append(SectionHeader('3', 'Tableau de bord', 'L\'état de votre commerce en un coup d\'œil'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le <b>Tableau de bord</b> regroupe les indicateurs essentiels : <b>chiffre d\'affaires</b>, '
        '<b>bénéfice</b>, <b>nombre de ventes</b>, <b>produits en stock</b>, ainsi que les '
        '<b>alertes</b> (stock faible, produits à réapprovisionner). Les graphiques montrent '
        'l\'évolution des ventes et des encaissements pour la période choisie.', S_BODY))
    story.extend(bullets([
        '<b>KPI en temps réel</b> : CA, bénéfice, ventes, stock (séparés par devise FC/USD).',
        '<b>Graphiques d\'évolution</b> (Chart.js) : ventes, caisse, produits.',
        '<b>Alertes intelligentes</b> : stock minimal atteint, produits épuisés.',
        '<b>Sélecteur de période</b> : aujourd\'hui, 7 jours, ce mois, cette année.',
    ]))
    story.extend(figure(os.path.join(CAP, '02_dashboard.png'),
                        'Tableau de bord : indicateurs, graphiques et alertes'))
    story.append(PageBreak())

    # ===================== 4. STOCK =====================
    story.append(SectionHeader('4', 'Gestion du Stock', 'Produits, inventaire, alertes et reconnaissance par IA'))
    story.append(Spacer(1, 10))
    story.append(Paragraph('4.1. Inventaire des produits', S_H2))
    story.append(Paragraph(
        'Le module <b>Stock</b> liste tous vos produits avec leur <b>référence</b>, <b>désignation</b>, '
        '<b>catégorie</b>, <b>quantité</b>, <b>prix d\'achat</b> et <b>prix de vente</b> en FC et en '
        'USD. Vous pouvez rechercher un produit, le modifier ou le supprimer en un clic.', S_BODY))
    story.extend(figure(os.path.join(CAP, '03_stock.png'),
                        'Gestion du stock : liste des produits et indicateurs'))
    story.append(Paragraph('4.2. Stock minimal et alertes', S_H2))
    story.append(Paragraph(
        'Chaque produit peut avoir un <b>stock minimal</b>. Dès que la quantité descend sous ce '
        'seuil, une <b>alerte</b> apparaît et le produit est signalé « à réapprovisionner ». '
        'L\'application met aussi à jour automatiquement le stock lors des ventes et des '
        'réapprovisionnements.', S_BODY))
    story.append(Paragraph('4.3. Scanner par Photo — Intelligence Artificielle', S_H2))
    story.append(Paragraph(
        'La fonction <b>« Scanner par Photo »</b> (bouton <b>Scanner par Photo</b> de l\'écran Stock) '
        'permet d\'<b>identifier automatiquement un produit à partir d\'une photo</b> prise avec la '
        'caméra ou importée. Le moteur combine plusieurs technologies :', S_BODY))
    story.extend(bullets([
        '<b>Lecture de code-barres</b> (EAN, UPC) via pyzbar.',
        '<b>OCR</b> (Tesseract) : lecture du texte de l\'étiquette (référence, nom).',
        '<b>Reconnaissance visuelle</b> (YOLOv8 + signatures d\'images) pour retrouver un produit déjà connu.',
        '<b>Correspondance floue</b> (RapidFuzz) pour tolérer les fautes de saisie.',
    ]))
    story.extend(figure(os.path.join(CAP, '03b_stock_scanner_ia.png'),
                        'Scanner par Photo : identification automatique d\'un produit (IA)'))
    story.append(Paragraph('4.4. Ajout et modification d\'un produit', S_H2))
    story.append(Paragraph(
        'Le formulaire produit permet de renseigner la <b>référence</b>, la <b>désignation</b>, '
        'la <b>catégorie</b>, les <b>quantités</b> et les <b>prix</b> en FC et en USD, le '
        '<b>stock minimal</b>, ainsi que d\'ajouter une <b>photo</b> du produit (utile pour la '
        'reconnaissance par IA).', S_BODY))
    story.extend(figure(os.path.join(CAP, '03c_stock_formulaire_produit.png'),
                        'Formulaire d\'enregistrement d\'un produit avec photo et stock minimal'))
    story.append(PageBreak())

    # ===================== 5. VENTES =====================
    story.append(SectionHeader('5', 'Ventes', 'Enregistrement et suivi de vos ventes'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le module <b>Ventes</b> permet d\'enregistrer chaque vente en <b>FC</b> ou en <b>USD</b>. '
        'L\'application met à jour le stock automatiquement, calcule le <b>total</b>, et conserve '
        'l\'<b>historique complet</b> des ventes (date, client, produits, montant).', S_BODY))
    story.extend(bullets([
        '<b>Enregistrement rapide</b> : recherche du produit, quantité, devise.',
        '<b>Gestion des clients</b> : vente rattachée à un client ou vente au comptoir.',
        '<b>Crédits</b> : possibilité de vendre à crédit (suivi des créances).',
        '<b>Historique</b> consultable et filtrable par période.',
    ]))
    story.extend(figure(os.path.join(CAP, '04_ventes.png'),
                        'Écran des ventes : enregistrement et historique'))
    story.append(Paragraph('5.1. Scanner intelligent intégré', S_H2))
    story.append(Paragraph(
        'Le bouton <b>Scanner Intelligent</b> ouvre un panneau directement dans la page de vente '
        '(plus besoin d\'une fenêtre séparée). Le <b>scan est continu pour toutes les technologies</b> '
        'tant que la caméra est active : <b>codes-barres et QR</b> (détectés instantanément dans le '
        'navigateur), <b>étiquettes et textes</b> (OCR), et <b>images de produits</b> (reconnaissance '
        'visuelle). Chaque produit reconnu est affiché et vous pouvez le <b>sélectionner pour le '
        'mettre dans le panier</b> ; la caméra reste ouverte pour scanner les produits suivants et '
        's\'arrête quand vous avez terminé.', S_BODY))
    story.extend(bullets([
        '<b>Détection continue</b> : code-barres, QR, image, OCR et texte analysés automatiquement sans bouton de capture.',
        '<b>Sélection au panier</b> : les produits correspondants s\'affichent, cliquez sur « Ajouter au panier » puis scannez le suivant.',
        '<b>Ajout automatique (optionnel)</b> : une case à cocher ajoute directement au panier les codes-barres / QR certains.',
        '<b>Rapidité maximale</b> : les codes-barres sont décodés dans le navigateur, et l\'analyse image en continu utilise un mode accéléré (YOLO désactivé) pour exploiter au mieux la puissance de l\'ordinateur.',
        '<b>Capturer &amp; identifier</b> : prise d\'une photo via la caméra pour une analyse complète (image + OCR + YOLO).',
        '<b>Photo / Fichier</b> : import d\'une image existante pour identification.',
        '<b>Saisie manuelle</b> : entrée du code-barres ou de la référence pour un ajout direct.',
        '<b>Bips sonores</b> : un son distinct confirme chaque image capturée, chaque produit reconnu, « peut-être reconnu » ou inconnu — pratique pour scanner sans regarder l\'écran.',
        '<b>Arrêt automatique</b> : la caméra est libérée dès la fermeture de la vente.',
    ]))
    story.extend(figure(os.path.join(CAP, '13_ventes_scanner_integre.png'),
                        'Scanner intelligent intégré à la page de vente : détection continue et ajout direct au panier'))
    story.append(Paragraph('5.2. Facture simplifiée', S_H2))
    story.append(Paragraph(
        'La facture générée à la fin de chaque vente affiche un <b>total unique</b> en francs '
        'congolais avec sa conversion en dollars, <b>sans lignes « sous-total HT » ni « TVA »</b> : '
        'le prix affiché est le prix final payé par le client.', S_BODY))
    story.extend(bullets([
        '<b>Total clair</b> : montant en FC + conversion en USD (taux configuré).',
        '<b>Présentation professionnelle</b> : en-tête entreprise, numéro et date, signatures.',
        '<b>Personnalisable</b> depuis Paramètres → Facture (voir 11.7).',
    ]))
    story.extend(figure(os.path.join(CAP, '11_ventes_facture_tva16.png'),
                        'Facture simplifiée : un seul total, plus de ligne TVA / HT'))
    story.append(PageBreak())

    # ===================== 6. CAISSE =====================
    story.append(SectionHeader('6', 'Caisse', 'Suivi des encaissements et des dépenses'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le module <b>Caisse</b> enregistre toutes les <b>entrées</b> (ventes, remboursements) et '
        '<b>sorties</b> (achats, dépenses) d\'argent, séparément en <b>FC</b> et en <b>USD</b>. '
        'Le <b>solde</b> est recalculé en permanence et l\'historique des mouvements reste '
        'consultable à tout moment.', S_BODY))
    story.extend(bullets([
        '<b>Solde en FC et en USD</b> affiché en permanence.',
        '<b>Mouvements</b> : entrées et sorties avec motif et date.',
        '<b>Conversion FC/USD</b> selon le taux configuré.',
        '<b>Journal de caisse</b> complet et filtrable.',
    ]))
    story.extend(figure(os.path.join(CAP, '05_caisse.png'),
                        'Caisse : entrées, sorties et solde en FC et USD'))
    story.append(PageBreak())

    # ===================== 7. RAPPORTS =====================
    story.append(SectionHeader('7', 'Rapports', 'Sept rapports pour piloter votre activité'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le module <b>Rapports</b> regroupe <b>7 rapports détaillés</b>, filtrables par période :',
        S_BODY))
    reports = [
        ['Onglet', 'Contenu'],
        ['Capital & Actifs', 'Capital investi, actifs, stocks évalués, valeur de l\'entreprise.'],
        ['Synthèse', 'CA, bénéfice, marge, top produits — vue d\'ensemble.'],
        ['Produits & Stock', 'Valorisation du stock, mouvements par produit, stock faible/épuisé.'],
        ['Réapprovisionnements', 'Achats, retours fournisseurs, coûts de réapprovisionnement.'],
        ['Historique des activités', 'Journal complet du stock et de la caisse : qui, quoi, quand.'],
        ['Clients', 'Ventes par client, meilleurs clients, soldes.'],
        ['Dettes & Crédits', 'Créances clients, dettes fournisseurs, échéances.'],
    ]
    t = Table(reports, colWidths=[5.2 * cm, (W - 2 * MARGIN - 5.2 * cm)])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIM),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), FB),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -1), F),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    for tab, label in [
        ('capital', 'Capital & Actifs'),
        ('synthese', 'Synthèse'),
        ('produits', 'Produits & Stock'),
        ('reappro', 'Réapprovisionnements'),
        ('activites', 'Historique des activités'),
        ('clients', 'Clients'),
        ('dettes', 'Dettes & Crédits'),
    ]:
        story.append(Paragraph('7.%d. %s' % (reports.index([x for x in reports[1:] if x[0] == label][0]) + 1, label), S_H2))
        story.extend(figure(os.path.join(CAP, '06_rapports_%s.png' % tab),
                            'Rapport « %s »' % label))
    story.append(PageBreak())

    # ===================== 8. STATISTIQUES =====================
    story.append(SectionHeader('8', 'Statistiques', 'Analyse chiffrée de votre activité'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le module <b>Statistiques</b> offre des analyses plus poussées : <b>évolution des ventes</b>, '
        '<b>tendances</b>, <b>répartition par catégorie</b>, <b>meilleures périodes</b>… Les données '
        'sont présentées sous forme de tableaux et de graphiques pour faciliter la prise de décision.', S_BODY))
    story.extend(figure(os.path.join(CAP, '07_statistiques.png'),
                        'Statistiques : graphiques et indicateurs d\'évolution'))
    story.append(PageBreak())

    # ===================== 9. COMPTABILITÉ =====================
    story.append(SectionHeader('9', 'Comptabilité', 'Plan comptable, journal, grand livre, balance et bilan'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le module <b>Comptabilité</b> s\'inspire du <b>plan comptable OHADA</b>. Il s\'articule '
        'autour de cinq écrans :', S_BODY))
    story.extend(bullets([
        '<b>Plan comptable</b> : liste des comptes (classes 1 à 9).',
        '<b>Journal</b> : toutes les écritures comptables chronologiques.',
        '<b>Grand livre</b> : détail des mouvements par compte.',
        '<b>Balance</b> : débit/crédit par compte, soldes.',
        '<b>Bilan</b> : actif et passif synthétiques.',
    ]))
    for tab, label in [
        ('plan', 'Plan comptable'),
        ('journal', 'Journal des écritures'),
        ('grandlivre', 'Grand livre'),
        ('balance', 'Balance des comptes'),
        ('bilan', 'Bilan'),
    ]:
        story.append(Paragraph('9.%d. %s' % ([x[0] for x in
                          [('plan','Plan comptable'),('journal','Journal des écritures'),
                           ('grandlivre','Grand livre'),('balance','Balance des comptes'),
                           ('bilan','Bilan')]].index(tab) + 1, label), S_H2))
        story.extend(figure(os.path.join(CAP, '08_comptabilite_%s.png' % tab),
                            'Comptabilité — %s' % label))
    story.append(PageBreak())

    # ===================== 10. UTILISATEURS =====================
    story.append(SectionHeader('10', 'Utilisateurs', 'Comptes du personnel et permissions'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le module <b>Utilisateurs</b> permet de créer les comptes des employés (vendeurs, '
        'caissiers, gestionnaires) avec un <b>rôle</b> et des <b>permissions</b> adaptés. '
        'Chaque action sensible est tracée pour garantir la traçabilité.', S_BODY))
    story.extend(bullets([
        '<b>Création de comptes</b> avec mot de passe sécurisé.',
        '<b>Rôles</b> : administrateur, gestionnaire, vendeur…',
        '<b>Activation/désactivation</b> d\'un compte.',
        '<b>Journal des connexions</b> pour la sécurité.',
    ]))
    story.extend(figure(os.path.join(CAP, '09_users.png'),
                        'Gestion des utilisateurs et de leurs droits'))
    story.append(PageBreak())

    # ===================== 11. PARAMÈTRES =====================
    story.append(SectionHeader('11', 'Paramètres', 'Entreprise, sécurité, notifications, devises, apparence'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le module <b>Paramètres</b> regroupe <b>8 panneaux</b> de configuration :', S_BODY))
    panels = [
        ['Panneau', 'Utilité'],
        ['Entreprise', 'Nom, adresse, email, téléphone de votre société.'],
        ['Facture', 'Design, titre, éléments affichés, mention, signature et cachet des factures.'],
        ['Profil & Sécurité', 'Compte administrateur, changement de mot de passe.'],
        ['Notifications', 'Alertes sonores et visuelles.'],
        ['Taux de change', 'Taux de conversion FC / USD en vigueur.'],
        ['Apparence', 'Thème et couleurs de l\'interface.'],
        ['Rapports Email', 'Envois automatiques quotidiens par email.'],
        ['Données', 'Sauvegarde et export (JSON, CSV).'],
    ]
    t = Table(panels, colWidths=[4.4 * cm, (W - 2 * MARGIN - 4.4 * cm)])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIM),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), FB),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -1), F),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    for panel, label in [
        ('entreprise', 'Entreprise'),
        ('security', 'Profil & Sécurité'),
        ('notifications', 'Notifications'),
        ('exchange', 'Taux de change'),
        ('appearance', 'Apparence'),
        ('data', 'Données — Sauvegarde & Export'),
    ]:
        story.append(Paragraph('11.%d. %s' % (
            [x[0] for x in [('entreprise','Entreprise'),('security','Profil & Sécurité'),
                            ('notifications','Notifications'),('exchange','Taux de change'),
                            ('appearance','Apparence'),('data','Données — Sauvegarde & Export')]].index(panel) + 1,
            label), S_H2))
        story.extend(figure(os.path.join(CAP, '10_settings_%s.png' % panel),
                            'Paramètres — %s' % label))
    story.append(Paragraph('11.7. Facture — personnalisation complète', S_H2))
    story.append(Paragraph(
        'Le panneau <b>Facture</b> permet de personnaliser entièrement vos factures : choix du '
        '<b>design</b> (moderne, classique ou minimal), <b>titre</b> modifiable, affichage ou '
        'masquage de chaque élément (entreprise, slogan, adresse, téléphone, email, RCCM, '
        'numéro et date, signatures), <b>mention personnalisée</b> et images de <b>signature</b> '
        'et de <b>cachet</b>.', S_BODY))
    story.extend(figure(os.path.join(CAP, '12_parametres_facture.png'),
                        'Paramètres — Facture : designs, éléments à afficher, mention et signature / cachet'))
    story.append(PageBreak())

    # ===================== 12. RAPPORTS EMAIL =====================
    story.append(SectionHeader('12', 'Rapports Email automatiques',
                               'Recevez votre rapport quotidien où que vous soyez'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le panneau <b>Rapports Email</b> programme l\'envoi automatique, chaque jour à l\'heure '
        'choisie, d\'un <b>rapport complet par email</b> : ventes, bénéfice, caisse, stock, '
        'crédits. Les rapports sont envoyés à une ou plusieurs adresses.', S_BODY))
    story.extend(bullets([
        '<b>Activation en un clic</b> + choix de l\'heure et des jours (Lun–Dim).',
        '<b>Plusieurs destinataires</b> (chef de stock, directeur…).',
        '<b>File d\'attente intelligente</b> : hors connexion, les rapports sont mis en attente puis '
        'envoyés automatiquement dès qu\'internet revient (rattrapage des jours manqués).',
        '<b>Bouton « Envoyer maintenant »</b> et <b>« Envoyer un email de test »</b>.',
        '<b>Journal des envois</b> : statut, date, erreurs éventuelles.',
        '<b>SMTP sécurisé</b> : STARTTLS ou SSL, mot de passe d\'application.',
    ]))
    story.extend(figure(os.path.join(CAP, '10_settings_rapportemail.png'),
                        'Paramètres Rapports Email : envois automatiques et file d\'attente'))
    story.append(PageBreak())

    # ===================== 13. TECHNOLOGIES =====================
    story.append(SectionHeader('13', 'Technologies utilisées', 'Le socle technique de l\'application'))
    story.append(Spacer(1, 10))
    story.append(Paragraph('13.1. Architecture générale', S_H2))
    story.append(Paragraph(
        'MotoStockIA #TUMIKA est une application <b>web</b> qui tourne en local sur le PC du '
        'commerce. Elle repose sur une architecture <b>Flask (Python)</b> côté serveur et des '
        'pages <b>HTML/CSS/JavaScript</b> côté navigateur. Toutes les données sont stockées dans '
        'une <b>base de données SQLite</b> : un simple fichier, portable, qui ne nécessite aucun '
        'serveur de base de données externe.', S_BODY))
    story.append(Spacer(1, 4))
    tech = [
        ['Couche', 'Technologies'],
        ['Langage serveur', 'Python 3.12 (Windows 64 bits)'],
        ['Framework web', 'Flask 3.0 — routes, sessions, sécurité'],
        ['Base de données', 'SQLite (fichier motostock.db)'],
        ['ORM', 'Flask-SQLAlchemy 3.1 + Flask-Migrate (migrations)'],
        ['Templates', 'Jinja2 (HTML dynamique)'],
        ['Interface', 'Bootstrap 5.3, Bootstrap Icons, JavaScript'],
        ['Graphiques', 'Chart.js 4.4'],
        ['Vision / IA', 'OpenCV, Tesseract OCR, YOLOv8 (Ultralytics), pyzbar, RapidFuzz, Pillow'],
        ['Génération codes', 'qrcode, python-barcode'],
        ['Envoi email', 'SMTP (smtplib) avec STARTTLS / SSL'],
    ]
    t = Table(tech, colWidths=[4.4 * cm, (W - 2 * MARGIN - 4.4 * cm)])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIM),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), FB),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -1), F),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph('13.2. Intelligence artificielle & vision', S_H2))
    story.append(Paragraph(
        'Le module <b>vision</b> de l\'application permet d\'identifier des produits à partir de '
        'photos : <b>détection de codes-barres</b> (pyzbar), <b>OCR</b> des étiquettes (Tesseract, '
        'langues français/anglais), <b>reconnaissance d\'objets</b> (YOLOv8) et <b>signatures '
        'visuelles</b> (empreintes d\'images par hachage perceptuel et histogrammes) avec '
        'correspondance <b>floue</b> pour tolérer les variantes.', S_BODY))
    story.append(Paragraph('13.3. Sécurité', S_H2))
    story.extend(bullets([
        '<b>Mots de passe hachés</b> (Werkzeug, non réversibles).',
        '<b>Sessions sécurisées</b> signées avec cookies HTTPOnly.',
        '<b>Protection anti force brute</b> : blocage temporaire après échecs répétés.',
        '<b>Journal des connexions</b> (succès et échecs) pour l\'audit.',
        '<b>Sauvegarde</b> et export des données (JSON, CSV).',
        '<b>Envoi email chiffré</b> : STARTTLS / SSL (mots de passe d\'application).',
        '<b>Conformité RDC</b> : protections prévues par le Code du numérique congolais.',
    ]))
    story.append(PageBreak())

    # ===================== 14. ANNEXES JURIDIQUES =====================
    story.append(SectionHeader('14', 'Annexes juridiques',
                               'Contrat de licence, contrat développeur/utilisateur, certificat de sécurité'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Les documents suivants encadrent l\'utilisation du logiciel en <b>République Démocratique '
        'du Congo</b>. Ils se réfèrent notamment à l\'<b>Ordonnance-loi n° 23/010 du 13 mars 2023 '
        'portant Code du numérique</b>, à la <b>Loi n° 20/017 du 25 novembre 2020</b> relative aux '
        'télécommunications et TIC, et à la <b>Convention de l\'Union africaine sur la cybersécurité '
        'et la protection des données à caractère personnel (Malabo, 27 juin 2014)</b>, ratifiée par '
        'l\'ordonnance-loi n° 23/008 du 10 mars 2023.', S_BODY))
    story.append(RoundedBox(
        '<b>Note importante :</b> ces documents sont fournis à titre indicatif. Il est recommandé '
        'de les faire valider par un conseil juridique avant toute utilisation commerciale.',
        bg=HexColor('#fef2f2'), border=C_RED, icon='&#9888;'))
    story.append(NextPageTemplate('annexe'))
    story.append(PageBreak())

    return story


# ----------------------------------------------------------------------
# Annexes officielles RDC (cadres, drapeau, armoiries, cachet, filigrane)
# ----------------------------------------------------------------------
ANX_ASSETS = os.path.join(PROJ, 'docs', 'assets')
ANX_FLAG = os.path.join(ANX_ASSETS, 'drapeau_rdc.png')
ANX_ARMS = os.path.join(ANX_ASSETS, 'armoiries_rdc.png')
ANX_WATER = os.path.join(TMP, 'armoiries_water.png')
ANX_M = MARGIN + 0.35 * cm


def make_watermark():
    if os.path.exists(ANX_WATER) or not os.path.exists(ANX_ARMS):
        return
    try:
        im = PILImage.open(ANX_ARMS).convert('RGBA')
        r, g, b, a = im.split()
        a = a.point(lambda x: int(x * 0.055))
        PILImage.merge('RGBA', (r, g, b, a)).save(ANX_WATER)
    except Exception:
        pass


class Cachet(Flowable):
    """Cachet rond officiel (sceau rouge)."""

    def __init__(self, color=HexColor('#b91c1c'), d=3.3 * cm):
        Flowable.__init__(self)
        self.d = d
        self.color = color
        self.width = d
        self.height = d

    def draw(self):
        import math
        c = self.canv
        c.saveState()
        cx = cy = self.d / 2
        c.setStrokeColor(self.color)
        c.setLineWidth(2.4)
        c.circle(cx, cy, self.d / 2 - 2, stroke=1, fill=0)
        c.setLineWidth(0.8)
        c.circle(cx, cy, self.d / 2 - 7, stroke=1, fill=0)
        R = self.d * 0.17
        pts = []
        for k in range(10):
            r = R if k % 2 == 0 else R * 0.4
            ang = -math.pi / 2 + k * math.pi / 5
            pts.append((cx + r * math.cos(ang), cy + 3 + r * math.sin(ang)))
        p = c.beginPath()
        p.moveTo(*pts[0])
        for x, y in pts[1:]:
            p.lineTo(x, y)
        p.close()
        c.setFillColor(self.color)
        c.drawPath(p, stroke=0, fill=1)
        c.setFont(FB, 7.5)
        c.drawCentredString(cx, cy + self.d / 2 - 11, 'CERTIFIÉ CONFORME')
        c.setFont(F, 6)
        c.drawCentredString(cx, cy - self.d / 2 + 8, 'MotoStockIA #TUMIKA · 2026')
        c.restoreState()


def doc_title(title, ref):
    """Barre de titre de document officiel : règle bleue en haut, règle or en bas."""
    p = Paragraph('<b>%s</b>' % title, st('dtt', fontName=FB, fontSize=14, leading=18,
                                          alignment=TA_CENTER, textColor=C_PRIM, spaceAfter=0))
    r = Paragraph('<font size=7.5 color="#64748b">%s</font>' % ref, st('dtr', alignment=TA_CENTER, spaceAfter=0))
    t = Table([[p], [r]], colWidths=[W - 2 * ANX_M])
    t.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 1.4, C_PRIM),
        ('LINEBELOW', (0, -1), (-1, -1), 1.4, C_ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def meta_table(pairs):
    """Tableau de renseignements d'un acte (émetteur, date, références…)."""
    rows = [[Paragraph('<b>%s</b>' % k, st('mk', fontName=FB, fontSize=8.5, textColor=C_DARK,
                                           alignment=TA_LEFT, spaceAfter=0)),
             Paragraph(v, st('mv', fontSize=9, textColor=HexColor('#334155'), alignment=TA_LEFT, spaceAfter=0))]
            for k, v in pairs]
    t = Table(rows, colWidths=[4.2 * cm, W - 2 * ANX_M - 4.2 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, C_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def article_block(titre, texte):
    """Article numéroté avec pastille bleue de référence."""
    badge = Paragraph(titre, st('ab', fontName=FB, fontSize=7.5, textColor=white,
                                alignment=TA_CENTER, spaceAfter=0))
    body = Paragraph(texte, S_BODY_S)
    t = Table([[badge, body]], colWidths=[2.4 * cm, W - 2 * ANX_M - 2.4 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), C_PRIM2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (0, 0), 3),
        ('RIGHTPADDING', (0, 0), (0, 0), 3),
        ('LEFTPADDING', (1, 0), (1, 0), 8),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, C_LINE),
    ]))
    return t


def annexe_bg(canv, doc):
    """Arrière-plan des pages d'annexes : cadre double officiel, drapeau,
    armoiries, bande tricolore nationale et filigrane."""
    make_watermark()
    canv.saveState()
    w, h = A4
    # cadre double officiel
    canv.setStrokeColor(C_PRIM)
    canv.setLineWidth(2.2)
    canv.rect(MARGIN, MARGIN, w - 2 * MARGIN, h - 2 * MARGIN)
    canv.setStrokeColor(C_ACCENT)
    canv.setLineWidth(0.8)
    canv.rect(MARGIN + 4.5, MARGIN + 4.5, w - 2 * MARGIN - 9, h - 2 * MARGIN - 9)
    # filigrane armoiries
    if os.path.exists(ANX_WATER):
        cw = 8.5 * cm
        ch = cw * 881.0 / 960.0
        canv.drawImage(ANX_WATER, (w - cw) / 2, (h - ch) / 2 - 0.4 * cm,
                       width=cw, height=ch, mask='auto', preserveAspectRatio=True)
    # drapeau (gauche)
    if os.path.exists(ANX_FLAG):
        fw = 3.0 * cm
        canv.drawImage(ANX_FLAG, MARGIN + 0.9 * cm, h - 4.05 * cm, width=fw, height=fw * 2 / 3,
                       mask='auto', preserveAspectRatio=True)
    # armoiries (droite)
    if os.path.exists(ANX_ARMS):
        aw_ = 2.6 * cm
        canv.drawImage(ANX_ARMS, w - MARGIN - 0.9 * cm - aw_, h - 3.7 * cm, width=aw_, height=aw_ * 881 / 960,
                       mask='auto', preserveAspectRatio=True)
    # en-tête central
    canv.setFillColor(HexColor('#0e6eb8'))
    canv.setFont(FB, 13.5)
    canv.drawCentredString(w / 2, h - 2.5 * cm, 'RÉPUBLIQUE DÉMOCRATIQUE DU CONGO')
    canv.setFillColor(HexColor('#c9122c'))
    canv.setFont(FB, 9.5)
    canv.drawCentredString(w / 2, h - 3.0 * cm, 'TRAVAIL · JUSTICE · SOLIDARITÉ')
    canv.setFillColor(C_GRAY)
    canv.setFont(F, 7.5)
    canv.drawCentredString(w / 2, h - 3.42 * cm, 'MotoStockIA #TUMIKA — Direction générale')
    # bande tricolore
    bx = MARGIN + 0.8 * cm
    bw = w - 2 * MARGIN - 1.6 * cm
    by = h - 4.6 * cm
    for i, col in enumerate([HexColor('#0e6eb8'), HexColor('#f7d117'), HexColor('#ce1126')]):
        canv.setFillColor(col)
        canv.rect(bx + i * bw / 3, by, bw / 3, 0.16 * cm, stroke=0, fill=1)
    # pied de page
    canv.setStrokeColor(C_ACCENT)
    canv.setLineWidth(0.8)
    canv.line(MARGIN + 1.0 * cm, 1.72 * cm, w - MARGIN - 1.0 * cm, 1.72 * cm)
    canv.setFont(F, 7.5)
    canv.setFillColor(C_GRAY)
    canv.drawCentredString(w / 2, 1.32 * cm, 'République Démocratique du Congo — Kinshasa')
    canv.drawString(MARGIN + 1.0 * cm, 1.32 * cm, 'N° MSIA-DOC-2026')
    canv.drawRightString(w - MARGIN - 1.0 * cm, 1.32 * cm, 'Page %d' % doc.page)
    canv.restoreState()


def legal_docs():
    story = []
    w_anx = W - 2 * ANX_M

    # ============ ANNEXE A : CONTRAT DE LICENCE ============
    story.append(Spacer(1, 2))
    story.append(doc_title('CONTRAT DE LICENCE DE LOGICIEL',
                           'N° MSIA-LIC-2026-001 · Références : Code du numérique RDC'))
    story.append(Spacer(1, 8))
    story.append(meta_table([
        ('Émetteur', '<b>MotoStockIA #TUMIKA</b> — société de droit congolais, siège à Kinshasa (RDC), '
                     'représentée par son Président Directeur Général (ci-après « l\'Éditeur »).'),
        ('Bénéficiaire', 'Toute personne physique ou morale autorisée à installer et à utiliser le Logiciel '
                         '(ci-après « l\'Utilisateur »).'),
        ('Date et lieu', 'Fait à Kinshasa, République Démocratique du Congo, le ____________.'),
        ('Textes de référence', 'Ordonnance-loi n° 23/010 du 13 mars 2023 portant Code du numérique ; '
                                'loi n° 20/017 du 25 novembre 2020 ; Convention de Malabo ratifiée par '
                                'l\'ordonnance-loi n° 23/008 du 10 mars 2023.'),
    ]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        '<b>ENTRE LES SOUSSIGNÉS :</b><br/><br/>'
        '<b>L\'ÉDITEUR :</b> la société <b>MotoStockIA #TUMIKA</b>, conçue et développée par ses '
        'créateurs, dont le siège est en République Démocratique du Congo, représentée par son '
        'Président Directeur Général, dûment habilité aux présentes (ci-après « l\'Éditeur ») ;<br/><br/>'
        '<b>ET</b><br/><br/>'
        '<b>L\'UTILISATEUR :</b> toute personne physique ou morale qui installe ou utilise le '
        'logiciel (ci-après « l\'Utilisateur »).<br/><br/>'
        'Il est convenu ce qui suit :', S_BODY_S))
    story.append(Spacer(1, 8))

    articles_licence = [
        ('Article 1 — Objet', 'Le présent contrat a pour objet de définir les conditions dans lesquelles '
         'l\'Éditeur concède à l\'Utilisateur un droit d\'utilisation du logiciel <b>MotoStockIA #TUMIKA</b> '
         '(ci-après « le Logiciel »), à l\'exclusion de tout transfert de propriété.'),
        ('Article 2 — Octroi de la licence', 'L\'Éditeur accorde à l\'Utilisateur une licence d\'utilisation '
         '<b>non exclusive, non cessible et non transférable</b>, pour la durée du présent contrat, '
         'sur un nombre d\'installations limité et convenu entre les parties.'),
        ('Article 3 — Droits de propriété intellectuelle', 'Le Logiciel, sa documentation, son code source '
         'et ses interfaces demeurent la <b>propriété exclusive de l\'Éditeur</b>. Toute reproduction, '
         'modification, décompilation ou commercialisation sans autorisation écrite est interdite, '
         'conformément à l\'ordonnance-loi n° 23/010 du 13 mars 2023 portant Code du numérique.'),
        ('Article 4 — Obligations de l\'Utilisateur', 'L\'Utilisateur s\'engage à : utiliser le Logiciel '
         'conformément à sa destination ; préserver la confidentialité de ses identifiants ; ne pas '
         'tenter d\'accéder aux données d\'autrui ; informer l\'Éditeur de toute anomalie ou incident '
         'de sécurité.'),
        ('Article 5 — Données à caractère personnel', 'Conformément au <b>Livre III du Code du numérique '
         'congolais</b> (notamment les dispositions sur la licéité, la transparence et la sécurisation des '
         'traitements) et à la Convention de Malabo ratifiée par l\'ordonnance-loi n° 23/008 du 10 mars 2023, '
         'l\'Utilisateur est responsable des traitements de données qu\'il réalise avec le Logiciel. Il '
         's\'engage à respecter les droits des personnes concernées (information, accès, rectification, '
         'suppression).'),
        ('Article 6 — Garanties', 'Le Logiciel est fourni « en l\'état ». L\'Éditeur garantit néanmoins '
         'la conformité du Logiciel à sa documentation et s\'engage à corriger, dans un délai raisonnable, '
         'toute anomalie qui lui sera signalée.'),
        ('Article 7 — Responsabilité', 'L\'Éditeur ne saurait être tenu responsable des dommages indirects '
         '(perte de chiffre d\'affaires, perte de données) résultant d\'une utilisation du Logiciel '
         'non conforme à sa documentation ou à ses obligations. L\'Utilisateur est invité à effectuer '
         'des sauvegardes régulières.'),
        ('Article 8 — Confidentialité', 'Les parties s\'engagent à garder confidentielles les informations '
         'techniques et commerciales dont elles auraient connaissance à l\'occasion du contrat, sous peine '
         'des sanctions prévues par le Code du numérique congolais.'),
        ('Article 9 — Durée et résiliation', 'Le contrat prend effet à la première installation du Logiciel. '
         'Chaque partie peut y mettre fin en cas de manquement grave de l\'autre partie, après mise en '
         'demeure restée sans effet pendant trente (30) jours.'),
        ('Article 10 — Droit applicable et juridiction', 'Le présent contrat est régi par le <b>droit '
         'congolais</b>. Tout litige relève des <b>juridictions de la République Démocratique du Congo</b>.'),
        ('Article 11 — Sanctions', 'La manipulation non autorisée de données à caractère personnel est punie '
         'd\'amendes pouvant aller de <b>8 000 000 à 200 000 000 de francs congolais</b>, sans préjudice '
         'des sanctions pénales prévues par le Code du numérique congolais et des dommages et intérêts '
         'civils.'),
        ('Article 12 — Dispositions finales', 'Les annexes éventuelles font partie intégrante du contrat. '
         'Toute modification du présent contrat doit être écrite et signée par les deux parties.'),
    ]
    for titre, texte in articles_licence:
        story.append(article_block(titre, texte))
        story.append(Spacer(1, 3))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Fait en deux (2) exemplaires originaux, à Kinshasa, République Démocratique du Congo.',
        S_BODY_S))
    story.append(Spacer(1, 14))
    sig_a = Table([
        [Paragraph('<b>L\'Éditeur</b>', st('se', fontName=FB, fontSize=10, alignment=TA_LEFT, spaceAfter=0)),
         Paragraph('<b>L\'Utilisateur</b>', st('se2', fontName=FB, fontSize=10, alignment=TA_LEFT, spaceAfter=0))],
        [Cachet(), ''],
        [Paragraph('Nom, qualité et signature, précédés de la mention « lu et approuvé »',
                   st('ss', fontSize=8, fontName=FI, textColor=C_GRAY, alignment=TA_LEFT, spaceAfter=0)),
         Paragraph('Nom, qualité et signature, précédés de la mention « lu et approuvé »',
                   st('ss', fontSize=8, fontName=FI, textColor=C_GRAY, alignment=TA_LEFT, spaceAfter=0))],
    ], colWidths=[w_anx / 2, w_anx / 2])
    sig_a.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.0, C_LINE),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, C_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(sig_a)
    story.append(PageBreak())

    # ============ ANNEXE B : CONTRAT DÉVELOPPEUR / UTILISATEUR ============
    story.append(Spacer(1, 2))
    story.append(doc_title('CONTRAT ENTRE LES CRÉATEURS / DÉVELOPPEURS ET L\'UTILISATEUR',
                           'N° MSIA-DEV-2026-001 · Licence, services et maintenance'))
    story.append(Spacer(1, 8))
    story.append(meta_table([
        ('Partie 1', '<b>Les Créateurs</b> : concepteurs et développeurs du logiciel MotoStockIA #TUMIKA '
                     '(ci-après « les Créateurs »).'),
        ('Partie 2', '<b>Le Client</b> : gérant, commerçant ou entreprise qui acquiert le droit '
                     'd\'utilisation (ci-après « le Client »).'),
        ('Date et lieu', 'Fait à Kinshasa, République Démocratique du Congo, le ____________.'),
        ('Textes de référence', 'Ordonnance-loi n° 23/010 du 13 mars 2023 (Code du numérique) ; '
                                'loi n° 20/017 du 25 novembre 2020 (TIC).'),
    ]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Le présent contrat règle la relation entre les <b>créateurs et développeurs</b> du logiciel '
        '<b>MotoStockIA #TUMIKA</b> (ci-après « les Créateurs ») et l\'<b>Utilisateur</b> final '
        '(gérant, commerçant, entreprise) qui acquiert le droit d\'utilisation (ci-après « le Client »).',
        S_BODY_S))
    story.append(Spacer(1, 8))
    articles_dev = [
        ('Article 1 — Définitions', '« Logiciel » : le progiciel de gestion commerciale MotoStockIA #TUMIKA. '
         '« Licence » : droit d\'utilisation concédé au Client. « Services » : installation, formation, '
         'maintenance, assistance et mises à jour proposés par les Créateurs.'),
        ('Article 2 — Objet', 'Les Créateurs s\'engagent à livrer le Logiciel au Client, à l\'installer '
         'sur l\'équipement du Client et à lui fournir les Services convenus. Le Client s\'engage à payer '
         'le prix convenu.'),
        ('Article 3 — Installation et formation', 'Les Créateurs assurent l\'installation du Logiciel, '
         'la création du compte administrateur et une session de formation aux modules essentiels '
         '(stock, ventes, caisse, rapports).'),
        ('Article 4 — Maintenance et mises à jour', 'Pendant la durée du contrat, les Créateurs '
         'fournissent les correctifs et les mises à jour du Logiciel, ainsi qu\'une assistance à '
         'distance. La maintenance ne couvre pas les dommages dus à une mauvaise utilisation ou à '
         'un matériel défectueux.'),
        ('Article 5 — Données du Client', 'Les données saisies par le Client (produits, ventes, clients) '
         'lui appartiennent. Les Créateurs s\'engagent à ne pas les utiliser ni les divulguer, '
         'conformément au <b>Code du numérique congolais</b> et à la Convention de Malabo. Le Client '
         'effectue des sauvegardes régulières de ses données.'),
        ('Article 6 — Prix et paiement', 'Le prix de la licence et des Services est fixé d\'un commun '
         'accord et payable en francs congolais ou en dollars américains, selon le mode convenu. '
         'Tout retard de paiement peut suspendre la maintenance.'),
        ('Article 7 — Garantie et responsabilité', 'Les Créateurs garantissent le bon fonctionnement '
         'du Logiciel dans son environnement standard. Ils ne sont pas responsables des dommages '
         'indirects. La responsabilité globale des Créateurs est limitée au montant payé par le '
         'Client au titre de la licence.'),
        ('Article 8 — Propriété intellectuelle', 'Le code source et tous les droits afférents au '
         'Logiciel restent la propriété exclusive des Créateurs. Le Client ne peut ni le revendre, '
         'ni le céder, ni le modifier sans accord écrit.'),
        ('Article 9 — Durée', 'Le présent contrat est conclu pour une durée d\'un (1) an renouvelable '
         'par tacite reconduction, sauf dénonciation par écrit trente (30) jours avant l\'échéance.'),
        ('Article 10 — Résiliation', 'En cas de manquement grave, l\'une ou l\'autre partie peut '
         'résilier le contrat après mise en demeure restée sans effet pendant trente (30) jours. '
         'Les droits de propriété intellectuelle survivent à la résiliation.'),
        ('Article 11 — Droit applicable', 'Le présent contrat est régi par le droit de la République '
         'Démocratique du Congo, notamment l\'ordonnance-loi n° 23/010 du 13 mars 2023 portant Code '
         'du numérique et la loi n° 20/017 du 25 novembre 2020 sur les TIC. Les tribunaux congolais '
         'sont seuls compétents.'),
        ('Article 12 — Intégralité et modifications', 'Le présent contrat constitue l\'intégralité de '
         'l\'accord des parties. Toute modification doit faire l\'objet d\'un avenant écrit signé.'),
    ]
    for titre, texte in articles_dev:
        story.append(article_block(titre, texte))
        story.append(Spacer(1, 3))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Fait à Kinshasa, République Démocratique du Congo, le ____________.<br/><br/>'
        '<b>Pour les Créateurs</b> (nom, qualité, signature) : ________________________<br/><br/>'
        '<b>Le Client</b> (nom, qualité, signature) : ________________________', S_BODY_S))
    story.append(PageBreak())

    # ============ ANNEXE C : CERTIFICAT DE SÉCURITÉ ============
    story.append(Spacer(1, 2))
    story.append(doc_title('CERTIFICAT DE SÉCURITÉ ET DE CONFORMITÉ',
                           'N° MSIA-SEC-2026-001 · Déclaré conforme'))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        '<b>Il est certifié que le logiciel MotoStockIA #TUMIKA, version 1.0, a fait l\'objet '
        'd\'une vérification complète de sécurité et répond aux exigences suivantes :</b>', S_BODY))
    story.append(Spacer(1, 6))
    sec_items = [
        ['Vérification', 'Résultat'],
        ['Authentification des utilisateurs', 'Conforme — mots de passe hachés et salés'],
        ['Gestion des sessions', 'Conforme — sessions signées, cookies HTTPOnly'],
        ['Protection anti force brute', 'Conforme — blocage temporaire après échecs répétés'],
        ['Journalisation des connexions', 'Conforme — traçabilité des accès'],
        ['Contrôle des accès par rôle', 'Conforme — permissions par module'],
        ['Protection des données personnelles', 'Conforme — principes du Code du numérique congolais'],
        ['Confidentialité des données commerciales', 'Conforme — données stockées en local'],
        ['Sauvegarde et export des données', 'Conforme — export JSON / CSV'],
        ['Envoi d\'emails sécurisé', 'Conforme — STARTTLS / SSL, mot de passe d\'application'],
        ['Conformité légale RDC', 'Conforme — ordonnance-loi n° 23/010 du 13/03/2023 et loi n° 20/017'],
    ]
    t = Table(sec_items, colWidths=[9.5 * cm, w_anx - 9.5 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_GREEN),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), FB),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -1), F),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#ecfdf5')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    outer = Table([[t]], colWidths=[w_anx])
    outer.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 2.0, C_ACCENT),
        ('LINEABOVE', (0, 0), (-1, 0), 0.8, C_PRIM),
        ('LINEBELOW', (0, -1), (-1, -1), 0.8, C_PRIM),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(outer)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        '<b>Approuvé par le développeur :</b> le présent certificat est délivré et approuvé par '
        'les créateurs et développeurs du logiciel MotoStockIA #TUMIKA.', S_BODY))
    story.append(Spacer(1, 18))
    sig_c = Table([
        [Paragraph('Fait à Kinshasa, le ____________<br/><br/>'
                   '<b>Cachet et signature des créateurs / développeurs :</b>',
                   st('sc', fontSize=9.5, leading=14, alignment=TA_LEFT, spaceAfter=0)),
         Cachet()],
    ], colWidths=[w_anx - 4.0 * cm, 4.0 * cm])
    sig_c.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(sig_c)
    story.append(PageBreak())

    # ============ ANNEXE D : PAGE PDG ============
    story.append(Spacer(1, 2))
    story.append(doc_title('MOT DU PRÉSIDENT DIRECTEUR GÉNÉRAL',
                           'N° MSIA-PDG-2026-001 · Signature officielle'))
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        '<b>« MotoStockIA #TUMIKA est née d\'une conviction : chaque commerçant congolais mérite '
        'des outils modernes, simples et puissants pour bâtir une entreprise solide. Ce manuel '
        'vous accompagne dans la maîtrise de chaque fonctionnalité. Nous restons à vos côtés pour '
        'que la technologie serve réellement votre croissance. »</b>', S_BODY))
    story.append(Spacer(1, 26))
    sig_d = Table([
        [Cachet(),
         Paragraph('<b>Président Directeur Général</b>', st('s1', fontName=FB, fontSize=11, alignment=TA_LEFT, spaceAfter=0))],
        ['', Paragraph('Nom complet : __________________________', st('s2', fontSize=9.5, alignment=TA_LEFT, spaceAfter=0))],
        ['', Paragraph('Qualité : _______________________________', st('s2', fontSize=9.5, alignment=TA_LEFT, spaceAfter=0))],
        ['', Paragraph('Lieu et date : __________________________', st('s2', fontSize=9.5, alignment=TA_LEFT, spaceAfter=0))],
        ['', Paragraph('Signature / Cachet : ____________________', st('s2', fontSize=9.5, alignment=TA_LEFT, spaceAfter=0))],
        ['', Paragraph('Tél / Email : ____________________________', st('s2', fontSize=9.5, alignment=TA_LEFT, spaceAfter=0))],
    ], colWidths=[4.6 * cm, w_anx - 4.6 * cm])
    sig_d.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.2, C_PRIM),
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f8fafc')),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, C_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(sig_d)
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        '<br/><center><font face="SegoeB" color="#1e3a8a" size=11>Merci de votre confiance.</font>'
        '<br/><font face="Segoe" color="#64748b" size=9>© %s MotoStockIA #TUMIKA — Tous droits réservés.'
        '<br/>République Démocratique du Congo</font></center>' % '2026', S_BODY))

    return story


# ----------------------------------------------------------------------
# Couverture
# ----------------------------------------------------------------------
class CoverCanvas:
    """Dessine la couverture en pleine page."""
    @staticmethod
    def draw(canv, doc):
        canv.saveState()
        w, h = A4
        # dégradé vertical
        top = HexColor('#0f172a')
        mid = HexColor('#1e3a8a')
        bot = HexColor('#1d4ed8')
        steps = 180
        for i in range(steps):
            t = i / (steps - 1)
            # haut -> milieu -> bas
            if t < 0.55:
                tt = t / 0.55
                r = top.red + (mid.red - top.red) * tt
                g = top.green + (mid.green - top.green) * tt
                b = top.blue + (mid.blue - top.blue) * tt
            else:
                tt = (t - 0.55) / 0.45
                r = mid.red + (bot.red - mid.red) * tt
                g = mid.green + (bot.green - mid.green) * tt
                b = mid.blue + (bot.blue - mid.blue) * tt
            y = h * (1 - t)
            canv.setFillColor(Color(r, g, b, alpha=1))
            canv.rect(0, y, w, h / steps + 1, stroke=0, fill=1)
        # cercles décoratifs
        canv.setFillColor(Color(1, 1, 1, alpha=0.06))
        canv.circle(0.15 * w, 0.9 * h, 3.2 * cm, stroke=0, fill=1)
        canv.setFillColor(Color(1, 1, 1, alpha=0.04))
        canv.circle(0.92 * w, 0.78 * h, 2.6 * cm, stroke=0, fill=1)
        canv.setFillColor(Color(1, 1, 1, alpha=0.05))
        canv.circle(0.06 * w, 0.12 * h, 2.0 * cm, stroke=0, fill=1)
        # titre
        canv.setFillColor(HexColor('#eab308'))
        canv.setFont(FB, 11)
        canv.drawString(2.2 * cm, h - 4.4 * cm, 'MOTOSTOCKIA')
        canv.setFont(FB, 46)
        canv.setFillColor(white)
        canv.drawString(2.2 * cm, h - 9.2 * cm, '#TUMIKA')
        # ligne or
        canv.setStrokeColor(HexColor('#eab308'))
        canv.setLineWidth(0.25 * cm)
        canv.line(2.2 * cm, h - 10.1 * cm, 10.5 * cm, h - 10.1 * cm)
        # sous-titre
        canv.setFont(F, 15)
        canv.setFillColor(Color(1, 1, 1, alpha=0.95))
        canv.drawString(2.2 * cm, h - 11.6 * cm, 'Manuel d\'utilisation & Guide complet')
        canv.setFont(F, 10.5)
        canv.setFillColor(Color(1, 1, 1, alpha=0.75))
        canv.drawString(2.2 * cm, h - 12.5 * cm,
                        'Gestion commerciale : Stock  ·  Ventes  ·  Caisse  ·  Rapports  ·  Comptabilité')
        # encadré fonctionnalités
        canv.setFont(F, 9.5)
        canv.setFillColor(Color(1, 1, 1, alpha=0.85))
        feats = ['Intelligence artificielle & vision', 'Rapports automatiques par email',
                 'Deux devises FC / USD', 'Base de données locale sécurisée']
        y = h - 15.5 * cm
        for fx in feats:
            canv.circle(2.6 * cm, y + 0.13 * cm, 0.12 * cm, stroke=0, fill=1)
            canv.setFillColor(Color(1, 1, 1, alpha=0.85))
            canv.drawString(3.1 * cm, y, fx)
            y -= 0.75 * cm
        # bas de page
        canv.setStrokeColor(Color(1, 1, 1, alpha=0.25))
        canv.setLineWidth(0.6)
        canv.line(2.2 * cm, 3.4 * cm, w - 2.2 * cm, 3.4 * cm)
        canv.setFont(FB, 9.5)
        canv.setFillColor(Color(1, 1, 1, alpha=0.9))
        canv.drawCentredString(w / 2, 2.7 * cm, 'Version 1.0  ·  République Démocratique du Congo')
        canv.setFont(F, 8.5)
        canv.setFillColor(Color(1, 1, 1, alpha=0.6))
        canv.drawCentredString(w / 2, 2.1 * cm, 'Conçu et développé par les créateurs de MotoStockIA — © 2026')
        canv.restoreState()


class CoverTemplate(PageTemplate):
    def __init__(self, id, pagesize):
        self.pagesize = pagesize
        PageTemplate.__init__(self, id, frames=[Frame(0, 0, pagesize[0], pagesize[1], id='cover')],
                              onPage=CoverCanvas.draw)


# ----------------------------------------------------------------------
# Lancement
# ----------------------------------------------------------------------
def main():
    from reportlab.platypus import BaseDocTemplate, NextPageTemplate, PageBreak
    doc = Doc(OUT_PDF)
    doc.addPageTemplates([
        PageTemplate(id='cover', frames=[Frame(0, 0, W, H, id='cov')], onPage=CoverCanvas.draw),
        PageTemplate(id='content', frames=[Frame(MARGIN, 1.6 * cm, W - 2 * MARGIN, H - 1.7 * cm - 1.6 * cm, id='main')],
                     onPage=doc.draw_bg),
        PageTemplate(id='annexe', frames=[Frame(ANX_M, 1.9 * cm, W - 2 * ANX_M, H - 5.15 * cm - 1.9 * cm, id='anx')],
                     onPage=annexe_bg),
    ])
    story = []
    # page de couverture
    story.append(NextPageTemplate('content'))
    story.append(Spacer(1, 0))  # placeholder pour déclencher la page cover
    story.append(PageBreak())
    story += build()
    story += legal_docs()
    doc.multiBuild(story)
    print('PDF généré :', OUT_PDF)
    print('Taille :', os.path.getsize(OUT_PDF) // 1024, 'Ko')


if __name__ == '__main__':
    main()
