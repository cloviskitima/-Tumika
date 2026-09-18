# =====================================================================
#  MotoStockIA #TUMIKA — Image Docker pour hébergement (Render, …)
#  Python 3.12 + dépendances système : OCR Tesseract, code-barres (zbar),
#  OpenCV/vision (gl/glib), et le serveur Gunicorn.
# =====================================================================
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# --- Dépendances système ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-fra \
        libzbar0 \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# --- Dépendances Python ---
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Code de l'application ---
COPY app ./app
COPY templates ./templates
COPY static ./static
COPY wsgi.py app.py serve.py init_db.py ./

# Dossier des images téléversées (créé aussi automatiquement au démarrage)
RUN mkdir -p static/uploads

ENV HOST=0.0.0.0

EXPOSE 8000

CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile -"]