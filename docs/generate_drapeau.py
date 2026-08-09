# -*- coding: utf-8 -*-
"""Génère le drapeau de la République Démocratique du Congo (PNG) : bleu ciel,
étoile jaune en chef (canton supérieur gauche), bande diagonale rouge bordée de jaune."""
import math
from PIL import Image, ImageDraw

OUT = r"C:\Users\kitima\AppData\Local\Temp\opencode\rdc_assets"
import os
os.makedirs(OUT, exist_ok=True)

W, H = 1200, 800
BLEU = (0, 162, 232)       # bleu ciel officiel
JAUNE = (247, 209, 23)     # jaune
ROUGE = (206, 17, 38)      # rouge

img = Image.new("RGB", (W, H), BLEU)
dr = ImageDraw.Draw(img)

# Étoile jaune à cinq branches, centrée dans le canton supérieur gauche
cx, cy = 0.15 * W, 0.19 * H
R_EXT = 0.13 * H
R_INT = R_EXT * 0.382
pts = []
for k in range(10):
    r = R_EXT if k % 2 == 0 else R_INT
    ang = -math.pi / 2 + k * math.pi / 5
    pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
dr.polygon(pts, fill=JAUNE)

# Bande diagonale rouge bordée de jaune, du coin inférieur au battant au coin supérieur au drapeau
A = (0, H * 0.86)
B = (W, H * 0.02)
dx, dy = B[0] - A[0], B[1] - A[1]
L = math.hypot(dx, dy)
ux, uy = dx / L, dy / L
px, py = -uy, ux          # perpendiculaire

bande = 0.13 * H
bord = 0.02 * H

def poly(off):
    o = off
    return [
        (A[0] + px * o, A[1] + py * o),
        (B[0] + px * o, B[1] + py * o),
        (B[0] - px * o, B[1] - py * o),
        (A[0] - px * o, A[1] - py * o),
    ]

dr.polygon(poly(bande / 2 + bord), fill=JAUNE)
dr.polygon(poly(bande / 2), fill=ROUGE)

path = os.path.join(OUT, "drapeau_rdc.png")
img.save(path, "PNG")
print("drapeau:", path, os.path.getsize(path) // 1024, "Ko", img.size)
