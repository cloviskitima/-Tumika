"""
Générateur de QR codes et codes-barres RÉELS (scannables)
Utilise les librairies qrcode et python-barcode (voir requirements.txt)
"""

from io import BytesIO


def generate_qr_png_bytes(data, size=300):
    """
    Génère un QR code PNG réel contenant `data` (scannable).
    À la lecture, le scanner retrouvera exactement `data`
    (par exemple la référence du produit).
    """
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(str(data))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    if size and size > 0:
        img = img.resize((size, size))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_barcode_png_bytes(code, dpi=200):
    """
    Génère un code-barres PNG réel (Code128) contenant `code`.
    À la lecture, le scanner retrouvera exactement `code`
    (par exemple le code-barres du produit).
    """
    from barcode import Code128
    from barcode.writer import ImageWriter

    options = {
        "module_width": 0.4,
        "module_height": 15.0,
        "font_size": 12,
        "text_distance": 3.0,
        "quiet_zone": 6.5,
        "dpi": dpi,
        "format": "PNG",
    }
    writer = ImageWriter()
    bc = Code128(str(code), writer=writer)
    buf = BytesIO()
    bc.write(buf, options=options)
    return buf.getvalue()
