# -*- coding: utf-8 -*-
"""Génère des vidéos marketing (16:9 et 9:16) de MotoStockIA à partir des captures docs/captures/.

Méthode : rendu PIL de chaque slide (fond flouté + capture encadrée + étalonnage + sous-titre),
puis ffmpeg : zoompan (Ken Burns) sur chaque slide + enchaînement par fondus (xfade), H.264.
"""
import glob
import os
import shutil
import subprocess
import tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAPTURES = os.path.join(ROOT, 'docs', 'captures')
ICON = os.path.join(ROOT, 'assets', 'motostock.png')
OUTDIR = os.path.join(ROOT, 'docs', 'promo')

FONT_BOLD = r'C:\Windows\Fonts\segoeuib.ttf'
FONT_REG = r'C:\Windows\Fonts\segoeui.ttf'

SCALE = 1.5                      # rendu des slides en 1.5x pour une qualité zoom
FPS = 30
CONTENT_SEC = 3.4
INTRO_SEC = 4.0
OUTRO_SEC = 4.0
FADE = 0.6

BLUE_ACCENT = (96, 165, 250, 235)


def find_ffmpeg():
    p = shutil.which('ffmpeg')
    if p:
        return p
    la = os.environ.get('LOCALAPPDATA', '')
    found = glob.glob(os.path.join(la, 'Microsoft', 'WinGet', 'Packages', 'Gyan.FFmpeg*', '**', 'ffmpeg.exe'), recursive=True)
    if found:
        return found[0]
    raise RuntimeError('ffmpeg introuvable')


FFMPEG = find_ffmpeg()


SLIDES = [
    ('01_login.png', 'Connexion sécurisée'),
    ('02_dashboard.png', 'Tableau de bord en temps réel'),
    ('03_stock.png', 'Gestion complète du stock & codes-barres'),
    ('03b_stock_scanner_ia.png', 'Identification IA par photo ou caméra'),
    ('03c_stock_formulaire_produit.png', 'Fiche produit : photos, QR code, compatibilités'),
    ('04_ventes.png', 'Caisse de vente intégrée'),
    ('05_caisse.png', 'Suivi de caisse bi-devise (FC / USD)'),
    ('06_rapports_synthese.png', 'Rapports : synthèse d\'activité'),
    ('06_rapports_capital.png', 'Valeur de votre stock & capital'),
    ('06_rapports_produits.png', 'Analyse des produits & rotation des stocks'),
    ('06_rapports_clients.png', 'Suivi clients & performance'),
    ('06_rapports_dettes.png', 'Créances & recouvrement'),
    ('06_rapports_reappro.png', 'Suivi des réapprovisionnements'),
    ('06_rapports_activites.png', 'Journal détaillé de toutes les activités'),
    ('07_statistiques.png', 'Statistiques en temps réel'),
    ('08_comptabilite_plan.png', 'Comptabilité : plan comptable'),
    ('08_comptabilite_journal.png', 'Journal des écritures'),
    ('08_comptabilite_grandlivre.png', 'Grand livre comptable'),
    ('08_comptabilite_balance.png', 'Balance comptable'),
    ('08_comptabilite_bilan.png', 'Bilan comptable'),
    ('09_users.png', 'Gestion des utilisateurs & rôles'),
    ('10_settings_entreprise.png', 'Paramètres de votre entreprise'),
    ('10_settings_appearance.png', 'Personnalisation : thèmes & couleurs'),
    ('10_settings_security.png', 'Sécurité & mot de passe'),
    ('10_settings_exchange.png', 'Taux de change & bi-devise'),
    ('10_settings_notifications.png', 'Alertes de stock & notifications'),
    ('10_settings_rapportemail.png', 'Rapports automatiques par e-mail'),
    ('10_settings_data.png', 'Sauvegarde, export & réinitialisation'),
    ('11_ventes_facture_tva16.png', 'Facture TVA 16 % personnalisée'),
    ('11_ventes_modale_tva16.png', 'Vente rapide : paiement & TVA'),
    ('12_parametres_facture.png', 'Signature, cachet & mentions légales'),
    ('13_ventes_scanner_integre.png', 'Scanner de code-barres intégré'),
]


# --------------------------------------------------------------------- outils image

def _open(path):
    img = Image.open(path)
    return ImageOps.exif_transpose(img).convert('RGB')


def cover(img, W, H):
    tw, th = img.size
    s = max(W / tw, H / th)
    nw, nh = int(tw * s + 0.5), int(th * s + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - W) // 2, (nh - H) // 2
    return img.crop((x, y, x + W, y + H))


def contain(img, W, H):
    img = img.copy()
    img.thumbnail((W, H), Image.LANCZOS)
    return img


def blur_fast(img, radius):
    """Flou gaussien rapide : floutage sur image réduite puis réagrandissement."""
    w, h = img.size
    s = max(4, int(min(w, h) / 48))
    small = img.resize((max(1, w // s), max(1, h // s)), Image.LANCZOS)
    small = small.filter(ImageFilter.GaussianBlur(max(2.0, radius / s)))
    return small.resize((w, h), Image.LANCZOS)


def vignette(img, strength=0.11):
    W, H = img.size
    y, x = np.ogrid[:H, :W]
    r = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    mask = np.clip((r - 0.55) / 0.85, 0, 1) ** 1.35 * strength
    arr = np.asarray(img, dtype=np.float32)
    arr *= (1 - mask[..., None])
    return Image.fromarray(arr.astype(np.uint8))


def grade(img):
    img = ImageEnhance.Color(img).enhance(1.13)
    img = ImageEnhance.Contrast(img).enhance(1.07)
    img = ImageEnhance.Brightness(img).enhance(0.995)
    return vignette(img)


def gradient_bg(W, H, top=(8, 16, 44), bot=(29, 78, 216)):
    t = np.linspace(0, 1, H)[:, None, None].astype(np.float32)
    col = (1 - t) * np.asarray(top, np.float32) + t * np.asarray(bot, np.float32)
    arr = np.tile(col, (1, W, 1))
    return Image.fromarray(arr.astype(np.uint8), 'RGB')


def draw_tracked(draw, xy, text, font, tracking, fill):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor='lm')
        x += draw.textlength(ch, font=font) + tracking


def brand_badge(img, icon_src):
    W, H = img.size
    base = img.convert('RGBA')
    icon = Image.open(icon_src).convert('RGBA')
    ih = int(H * 0.052)
    iw = max(1, int(icon.width / icon.height * ih))
    icon = icon.resize((iw, ih), Image.LANCZOS)
    px, py = int(W * 0.03), int(H * 0.03)
    base.alpha_composite(icon, (px, py))
    draw = ImageDraw.Draw(base, 'RGBA')
    font = ImageFont.truetype(FONT_BOLD, int(H * 0.033))
    draw.text((px + iw + int(W * 0.012), py + ih // 2), 'MotoStockIA', font=font, fill=(255, 255, 255, 215), anchor='lm')
    return base


def caption_pill(img, text, max_width):
    W, H = img.size
    draw = ImageDraw.Draw(img, 'RGBA')
    base_fs = max(14, int(min(W, H) * 0.036))
    font = ImageFont.truetype(FONT_BOLD, base_fs)

    def fits(t, f):
        return draw.textlength(t, font=f) <= max_width

    lines = [text]
    if not fits(text, font):
        words = text.split(' ')
        for i in range(1, len(words)):
            l1, l2 = ' '.join(words[:i]), ' '.join(words[i:])
            if fits(l1, font) and fits(l2, font):
                lines = [l1, l2]
                break
        if len(lines) == 1:
            fs = base_fs
            while fs > 12 and len(lines) == 1:
                f = ImageFont.truetype(FONT_BOLD, fs)
                for i in range(1, len(words)):
                    l1, l2 = ' '.join(words[:i]), ' '.join(words[i:])
                    if fits(l1, f) and fits(l2, f):
                        lines = [l1, l2]
                        font = f
                        break
                fs -= 1

    bbox = font.getbbox('Ag')
    th = bbox[3] - bbox[1]
    lh = int(th * 1.28)
    padx = int(base_fs * 0.9)
    pady = int(base_fs * 0.5)
    line_w = max(draw.textlength(ln, font=font) for ln in lines)
    accent = int(base_fs * 0.5)
    pw = int(line_w + padx * 2 + accent)
    ph = lh * len(lines) + pady * 2
    x = (W - pw) // 2
    y = H - ph - int(H * 0.032)
    draw.rounded_rectangle((x, y, x + pw, y + ph), radius=ph // 2, fill=(8, 12, 26, 182))
    draw.rounded_rectangle((x, y, x + accent, y + ph), radius=int(accent / 2), fill=BLUE_ACCENT)
    cy = y + pady + lh // 2
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        draw.text((x + padx + accent, cy), ln, font=font, fill=(255, 255, 255, 248), anchor='lm')
        cy += lh
    return img


# --------------------------------------------------------------------- slides

def render_content_slide(capture, caption, W, H):
    cap = _open(capture)
    bg = cover(cap, W, H)
    blur_r = max(10, int(min(W, H) / 26))
    bg = blur_fast(bg, blur_r)
    bg = ImageEnhance.Brightness(bg).enhance(0.40)
    bg = ImageEnhance.Color(bg).enhance(0.5)

    MARGIN = int(W * 0.045)
    CAP_BOTTOM = int(H * (0.135 if H > W else 0.115))
    fg = contain(cap, W - 2 * MARGIN, H - 2 * MARGIN - CAP_BOTTOM)
    radius = int(W * 0.014)

    shadow = Image.new('RGBA', (fg.width + 60, fg.height + 60), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((14, 26, 14 + fg.width, 26 + fg.height), radius=radius, fill=(0, 0, 0, 175))
    shadow = blur_fast(shadow, 18)

    fg_rgba = fg.convert('RGBA')
    mask = Image.new('L', fg_rgba.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fg_rgba.width - 1, fg_rgba.height - 1), radius=radius, fill=255)
    fg_rgba.putalpha(mask)
    border = Image.new('RGBA', fg_rgba.size, (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle((0, 0, fg_rgba.width - 1, fg_rgba.height - 1), radius=radius,
                                             outline=(255, 255, 255, 38), width=2)

    x = (W - fg.width) // 2
    y = MARGIN
    bg.paste(shadow, (x - 30, y - 30), shadow)
    bg.paste(fg_rgba, (x, y), fg_rgba)
    bg.paste(border, (x, y), border)

    bg = grade(bg).convert('RGBA')
    bg = brand_badge(bg, ICON)
    return caption_pill(bg, caption, int(W * 0.72))


def render_intro(W, H):
    u = min(W, H)
    base = gradient_bg(W, H).convert('RGBA')
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W // 2 - int(H * 0.55), int(H * 0.10), W // 2 + int(H * 0.55), int(H * 0.10) + int(H * 1.1)),
                                 fill=(59, 130, 246, 65))
    glow = blur_fast(glow, 130)
    base.alpha_composite(glow)
    base = grade(base)

    draw = ImageDraw.Draw(base, 'RGBA')
    eyebrow = ImageFont.truetype(FONT_REG, int(u * 0.024))
    draw_tracked(draw, (0, int(H * 0.19)), 'P R É S E N T A T I O N   P R O D U I T', eyebrow, int(u * 0.008),
                 fill=(147, 197, 253, 230))

    icon = Image.open(ICON).convert('RGBA')
    ih = int(H * 0.30)
    iw = max(1, int(icon.width / icon.height * ih))
    icon = icon.resize((iw, ih), Image.LANCZOS)
    base.alpha_composite(icon, ((W - iw) // 2, int(H * 0.26)))

    title = ImageFont.truetype(FONT_BOLD, int(u * 0.085))
    draw.text((W // 2, int(H * 0.60)), 'MotoStockIA', font=title, fill=(255, 255, 255, 255), anchor='mm')

    sub = ImageFont.truetype(FONT_REG, int(u * 0.036))
    draw.text((W // 2, int(H * 0.70)), 'La gestion intelligente de votre magasin de pièces moto',
              font=sub, fill=(226, 232, 240, 245), anchor='mm')

    tags = ImageFont.truetype(FONT_REG, int(u * 0.026))
    draw.text((W // 2, int(H * 0.80)),
              'IA • Vision • Code-barres & QR • Caisse bi-devise • Comptabilité',
              font=tags, fill=(148, 163, 184, 235), anchor='mm')
    return base


def render_outro(W, H):
    u = min(W, H)
    base = gradient_bg(W, H).convert('RGBA')
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W // 2 - int(H * 0.5), int(H * 0.08), W // 2 + int(H * 0.5), int(H * 0.08) + int(H * 1.0)),
                                 fill=(59, 130, 246, 60))
    glow = blur_fast(glow, 120)
    base.alpha_composite(glow)
    base = grade(base)

    draw = ImageDraw.Draw(base, 'RGBA')
    icon = Image.open(ICON).convert('RGBA')
    ih = int(H * 0.22)
    iw = max(1, int(icon.width / icon.height * ih))
    icon = icon.resize((iw, ih), Image.LANCZOS)
    base.alpha_composite(icon, ((W - iw) // 2, int(H * 0.17)))

    title = ImageFont.truetype(FONT_BOLD, int(u * 0.07))
    draw.text((W // 2, int(H * 0.45)), 'MotoStockIA', font=title, fill=(255, 255, 255, 255), anchor='mm')

    sub = ImageFont.truetype(FONT_BOLD, int(u * 0.038))
    draw.text((W // 2, int(H * 0.55)), 'Révolutionnez la gestion de votre boutique', font=sub,
              fill=(191, 219, 254, 245), anchor='mm')

    contact = ImageFont.truetype(FONT_REG, int(u * 0.032))
    draw.text((W // 2, int(H * 0.66)), 'Contactez-nous pour une démonstration', font=contact,
              fill=(226, 232, 240, 240), anchor='mm')

    tags = ImageFont.truetype(FONT_REG, int(u * 0.026))
    draw.text((W // 2, int(H * 0.76)),
              'Stock • Ventes • Caisse • Rapports • Comptabilité • IA',
              font=tags, fill=(148, 163, 184, 235), anchor='mm')
    return base


# --------------------------------------------------------------------- ffmpeg

def encode_clip(slide_path, out_mp4, W, H, frames, direction):
    z = 'min(1.0+0.00055*on,1.14)' if direction == 'in' else 'max(1.14-0.00055*on,1.0)'
    vf = "zoompan=z='{}':d={}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={}x{}:fps={}".format(z, frames, W, H, FPS)
    cmd = [FFMPEG, '-y', '-i', slide_path, '-vf', vf, '-frames:v', str(frames),
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-pix_fmt', 'yuv420p', '-an', out_mp4]
    subprocess.run(cmd, check=True, capture_output=True)


def xfade_concat(clips, durations, out_mp4):
    n = len(clips)
    inputs = []
    for c in clips:
        inputs += ['-i', c]
    off = durations[0] - FADE
    offsets = []
    for i in range(1, n):
        offsets.append(round(off, 3))
        off += durations[i] - FADE
    fc = []
    prev = 'v0'
    for i in range(1, n):
        label = 'vx%d' % i
        fc.append('[{}][v{}]xfade=transition=fade:duration={:.3f}:offset={:.3f}[{}]'.format(
            prev, i, FADE, offsets[i - 1], label))
        prev = label
    fc.append('[{}]format=yuv420p[outv]'.format(prev))
    cmd = ([FFMPEG, '-y'] + inputs +
           ['-filter_complex', ';'.join(fc), '-map', '[outv]',
            '-r', str(FPS), '-c:v', 'libx264', '-preset', 'medium', '-crf', '19',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', out_mp4])
    subprocess.run(cmd, check=True, capture_output=True)


def build(fmt, W, H):
    work = tempfile.mkdtemp(prefix='promo_%s_' % fmt)
    out_mp4 = os.path.join(OUTDIR, 'promo_motostock_%s.mp4' % fmt)
    try:
        slides = [('intro', None, INTRO_SEC)] + \
                 [(f, c, CONTENT_SEC) for f, c in SLIDES] + \
                 [('outro', None, OUTRO_SEC)]
        clips, durations = [], []
        SW, SH = int(W * SCALE), int(H * SCALE)
        for idx, (name, cap, dur) in enumerate(slides):
            frames = int(round(dur * FPS))
            if name == 'intro':
                slide = render_intro(SW, SH)
            elif name == 'outro':
                slide = render_outro(SW, SH)
            else:
                slide = render_content_slide(os.path.join(CAPTURES, name), cap, SW, SH)
            png = os.path.join(work, 'slide_%02d.png' % idx)
            slide.convert('RGBA').save(png)
            mp4 = os.path.join(work, 'clip_%02d.mp4' % idx)
            encode_clip(png, mp4, W, H, frames, 'in' if idx % 2 == 0 else 'out')
            clips.append(mp4)
            durations.append(dur)
            print('  [%s] slide %02d/%02d encodé (%.1fs)' % (fmt, idx + 1, len(slides), dur))
        xfade_concat(clips, durations, out_mp4)
        print('OK %s -> %s' % (fmt, out_mp4))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    print('ffmpeg:', FFMPEG)
    build('16x9', 1920, 1080)
    build('9x16', 1080, 1920)


if __name__ == '__main__':
    main()
