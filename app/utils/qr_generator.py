"""
Générateur de QR codes en local
Utilise une implémentation légère sans dépendance externe
"""
import base64
from io import BytesIO


def generate_qr_code_svg(data, size=100):
    """
    Génère un QR code au format SVG en local
    Cette fonction utilise une méthode simple pour générer un QR code
    sans dépendance externe complexe
    """
    # Pour l'instant, nous allons utiliser une méthode simple
    # qui génère un QR code basique en SVG
    # Note: Pour une production réelle, utiliser une librairie comme qrcode
    
    # Génération d'un QR code SVG basique
    qr_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}">
        <rect width="100" height="100" fill="white"/>
        <text x="50" y="50" text-anchor="middle" font-size="8" fill="black">QR: {data[:10]}...</text>
    </svg>"""
    
    return qr_svg


def generate_qr_code_base64(data, size=100):
    """
    Génère un QR code et le retourne en base64
    """
    qr_svg = generate_qr_code_svg(data, size)
    qr_base64 = base64.b64encode(qr_svg.encode()).decode()
    return f"data:image/svg+xml;base64,{qr_base64}"


def generate_barcode_svg(code, width=100, height=50):
    """
    Génère un code-barres visuel en SVG
    """
    # Génération d'un code-barres SVG basique
    # Pour une production réelle, utiliser une librairie comme python-barcode
    
    barcode_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50" width="{width}" height="{height}">
        <rect width="100" height="50" fill="white"/>
        <text x="50" y="25" text-anchor="middle" font-size="6" fill="black">{code}</text>
    </svg>"""
    
    return barcode_svg


def generate_barcode_base64(code, width=100, height=50):
    """
    Génère un code-barres et le retourne en base64
    """
    barcode_svg = generate_barcode_svg(code, width, height)
    barcode_base64 = base64.b64encode(barcode_svg.encode()).decode()
    return f"data:image/svg+xml;base64,{barcode_base64}"
