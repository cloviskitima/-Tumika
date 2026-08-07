# SESSION TUMIKA — Point d'arrêt

> Fichier de reprise créé le 06/08/2026. Relis ce fichier en premier au début d'une nouvelle session.

## Objectif global
Refonte professionnelle des pages de MotoStockIA `#Tumika` (Flask + SQLAlchemy + SQLite), page par page,
dans le style « Paramètres » déjà validé. Backend fonctionnel branché sur les endpoints API réels (pas de maquettes).

## État d'avancement

### ✅ Paramètres — TERMINÉ (validé par l'utilisateur)
- `app/models/parametre.py` : modèle `Parametre` clé/valeur + `DEFAUTS`, `get_param`, `set_param`, `all_params`.
- Endpoints `/api/settings/*` dans `app/routes/api.py` (généraux, notifications, apparence, change-password, export, reset-data).
- `templates/settings.html` : nav latérale 6 onglets, toggles, jauge mot de passe, swatches couleurs, export JSON/CSV, zone danger avec confirmation « SUPPRIMER ».
- `templates/base.html` : application globale de la couleur (`--primary`) + `showToast` défini avant `{% block scripts %}`.

### ✅ Comptabilité — TERMINÉ (work précédent)
- `app/models/comptabilite.py` (CompteComptable, EcritureComptable), `app/utils/comptabilite.py` (PCGC 136 comptes, generation_vente, generation_paiement_credit, generation_caisse, maj_ecriture_vente, synchroniser_compta, soldes_par_compte).
- Endpoints `/api/compta/*` : resume, plan-comptable, plan-comptable/actualiser, journal, ecritures (POST/DELETE), grand-livre, balance, bilan, synchroniser.
- `templates/comptabilite.html` : 5 onglets + impression.

### ✅ Statistiques — TERMINÉ
- `templates/statistiques.html` + endpoint `/api/statistiques/globales`.

### ✅ Utilisateurs — TERMINÉ aujourd'hui (06/08)
- `templates/users.html` **entièrement refondue** : hero, 4 KPI, barre d'outils (recherche + filtres rôle/statut + export CSV), tableau pro (avatars, badges rôle/statut, pastilles permissions, pagination), modales pro (création/édition avec jauge mot de passe + permissions, changement mot de passe, confirmation suppression), toasts partout.
- **Nouveautés backend** :
  - `app/models/user.py` : colonne `permissions` (JSON) + `perms` / `set_permissions` + incluse dans `to_dict()`.
  - `app/__init__.py` (~ligne 58) : **migration légère** → si la colonne `permissions` manque dans la table `user`, `ALTER TABLE "user" ADD COLUMN permissions TEXT` (avec `sa_text`, sinon SQLAlchemy 2.0 lève une erreur). NE PAS SUPPRIMER ce bloc.
  - `app/routes/api.py` : create/update stockent `permissions` ; gardes d'unicité username/email ; auto-protection (pas de désactivation/rétrogradation/suppression de son propre compte).
  - `app/routes/main.py` : la route `/users` passe `current_user_id=session.get('user_id')` au template (pastille « VOUS » + boutons grisés sur soi-même).
- Tests passés : CRUD + permissions, toggle, mot de passe, filtres, auto-protections, migration, JS valide (node --check), 9 pages en 200.

### ✅ Vision / Identification des produits — TERMINÉ (backend + scan au POS, 07/08)
- Cahier de conception : pipeline **Code-barres/QR → OCR (référence) → Recherche texte floue → Visuel (dataset) → YOLO → Historique des corrections**. Chaque méthode renvoie un score ; sous le seuil → top 5 avec %.
- Environnement installé : Tesseract (`winget` UB-Mannheim → `C:\Program Files\Tesseract-OCR\tesseract.exe` v5.4.0.20240606), `pip install opencv-python-headless rapidfuzz ultralytics qrcode python-barcode` (cv2 5.0.0). `yolov8n.pt` → `app\vision\models\`. Langues `eng`+`fra` → `app\vision\tessdata\` (chemin passé par `TESSDATA_PREFIX`, PAS par `--tessdata-dir`). Piège cv2 5.x : `np.frombuffer` au lieu de `cv2.frombuffer`.
- `app/vision/__init__.py` (config + lazy imports), `ocr.py` (`ocr_image`, `--psm 6 -l fra+eng`, regex réf lettre+chiffre), `detection.py` (pyzbar + repli cv2.QRCodeDetector + YOLO seuil 0.4), `signatures.py` (dHash 8x8 + HSV 24 bins, `similitude`, `trouver_similaires` numpy), `dataset.py` (signatures_produit / mettre_a_jour / construire), `identification.py` (pipeline complet, seuils `SEUIL_CERTAIN=0.85`, `SEUIL_PROPOSITION=0.60`, `LIMITE_ALTERNATIVES=5`).
- `app/models/identification.py` : `ProduitSignature` (uniq produit_id+image_key) + `CorrectionIdentification` (`enregistrer`, `boost_par_cle`, bonus `0.05+(n-1)*0.05` cap 0.20).
- Endpoints `/api/identification/*` (analyse image/texte/code, confirmer, dataset GET/POST, `/api/produits/<id>/signature`) + **hooks dataset auto** sur create/update/delete produit.
- Réponses d'analyse : `success/mode/determination/confiance/methode/produit/alternatives/cles_signature/detail_analyse`. `cles_signature` (`code:`, `ref:`, `texte:sha1`, `yolo:`) ajouté ce jour pour l'apprentissage côté client.
- **Frontend Ventes** (`templates/ventes.html`) : bouton « Scanner Intelligent — Webcam / Photo / OCR » + modale `visionScannerModal` (webcam getUserMedia + capture, upload photo, saisie manuelle code/réf), rendu confiance (badge Certain/Probable/Incertain + %), top 5 avec barres + méthode, bouton « Ajouter au panier » / « Choisir ce produit », apprentissage via `/api/identification/confirmer` quand le vendeur corrige (index≠0 ou résultat non certain). Anciens modales barcode/QR morts supprimés.
- **Frontend Stock** (`templates/stock.html`) : bouton « Scanner par Photo » + modale `stockScannerModal` (upload photo, saisie manuelle code/réf + réutilisation de la caméra produit). Si un produit est identifié → cartes avec « Ajouter au stock » (`POST /api/produits/<id>/reapprovisionner`, quantité demandée par prompt) et « Ouvrir la fiche » (`editProduct`). Si aucun produit → « Créer ce produit » : ouvre le formulaire produit pré-rempli (code-barres détecté, référence OCR, catégorie YOLO) + photo scannée attachée en Image 1 (`image1Data` base64) → sauvegarde → dataset auto. Apprentissage via `/api/identification/confirmer` quand le vendeur choisit une alternative non top ou résultat non certain.

### ✅ Caméra web corrigée (08/08) — webcam ne s'ouvrait pas sur PC (fix 100% JS)
- Une tentative HTTPS (certificat auto-signé, `ssl_utils.py`, `installer_certificat.bat`, port 5001) a été **rejetée par l'utilisateur** (« Je n'approuve pas ce méthode », l'app ne s'ouvrait plus). **Revert complet** : `app.py` resert l'app en **HTTP classique** (port 5000), tous les fichiers SSL/certificat et la bannière rouge ont été **supprimés**, `cryptography` retiré de `requirements.txt`.
- **Fix caméra 100% JavaScript** (aucune dépendance HTTPS) :
  - Helper `requestCameraStream()` (stock) / `requestVisionCameraStream()` (ventes) : essaie en cascade `navigator.mediaDevices.getUserMedia` avec `facingMode:'environment'` → `'user'` → `{video:true}` (1280×720), puis **fallback legacy** `navigator.getUserMedia || webkitGetUserMedia || mozGetUserMedia` (style callback) si `mediaDevices` absent.
  - **Plus aucun blocage** : si toute la cascade échoue → toast « Caméra indisponible — utilisez la photo » + **ouverture automatique du sélecteur photo** (`stockFileInput` / `visionFileInput`), le flux d'analyse reste utilisable partout.
  - **Stock — caméra réutilisée** : le « Scanner par Photo » ne possède PLUS de caméra/vidéo séparée. Il réutilise la caméra de l'enregistrement produit (`webcamModal` / `webcamVideo` / `captureWebcam`) via `openWebcamModalForScan()` (mode `webcamScanMode=true` → capture → `analyseStockBlob`). Bouton « Ouvrir la caméra » dans la modale.
  - **Photo produit → analyse + dataset** : `captureWebcam` (mode formulaire produit) appelle `prefillProductFromCapture(imageData)` → analyse `/api/identification/analyse` pour pré-remplir code-barres / référence / catégorie si vides (en plus du dataset auto au save).
- Vérifié : `node --check` OK sur les blocs JS des deux templates, régression 9 pages → 200.
- Tests backend passés (`Temp\opencode\test_identification.py`) : QR 1.0, code-barres 1.0, OCR 0.97 (réf BREMBO-2458), texte 0.85, code saisi 1.0, dataset 9 signatures, visuel top 0.672, apprentissage + suppression OK. Note : le test de dataset a été rendu idempotent (le hook PUT construit déjà la signature → `POST /dataset` peut renvoyer 0 nouveau).
- JS validée (`node --check`), régression 9 pages → 200, flux stock scan → réappro → cleanup validé.

### ✅ Packaging / installation — TERMINÉ
- **`requirements.txt` créé à la racine** : Flask 3.0.0, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.0.5, numpy 2.5.1, opencv-python-headless 5.0.0.93, pytesseract 0.3.13, ultralytics 8.4.115, pyzbar 0.1.9, RapidFuzz 3.14.5, pillow 12.3.0, qrcode 8.2, python-barcode 0.16.1 (+ commentaires = déps système Tesseract 5, yolov8n.pt, tessdata).
- `app/vision/__init__.py` : détection Tesseract renforcée → chemins par défaut puis `shutil.which('tesseract')` (PATH). Vérifié : 13 paquets résolus, tests vision OK.

## Prochaines étapes possibles
1. Vérifier si `templates/caisse.html` doit être refondue (état à confirmer).
2. Dashboard — option d'un widget « dernières reconnaissances » ou accès rapide au scanner.
3. Toute nouvelle page doit rester 100% fonctionnelle (endpoints réels) et suivre le style établi.

## Conventions de style (à respecter)
- Hero : `.dashboard-hero` (dégradé `#0f172a → #1e3a8a`).
- KPI : `.stats-card-refined` + `.icon-badge` (variantes primary/success/indigo/warning/danger/info).
- Cartes : `.report-card`, `.users-card` (bordure `--gray-200`, rayon 16px, ombre douce).
- Feedback : `showToast(message, type)` global défini dans `base.html`.
- Helpers JS recréés localement dans chaque template : `escapeHtml`, `formatDateTime`, `formatNumber`, `debounce`.
- Bootstrap 5.3 + Bootstrap Icons chargés dans `base.html`.
- Devises CDF/USD ; taux par défaut `2800.0` via `get_exchange_rate('USD','CDF')`.
- Style nav latérale/onglets comme `settings.html` / `comptabilite.html`.

## Comment tester (Windows / PowerShell)
- Lancer : `python app.py` depuis `C:\Users\kitima\Desktop\#Tumika`.
  - Accès : **`http://localhost:5000`** (même PC) ou **`http://<IP-du-PC>:5000`** (réseau) — mode HTTP classique, comme avant.
- Tests rapides via le test client Flask (exemples dans `C:\Users\kitima\AppData\Local\Temp\opencode\test_users_refonte.py` et `test_regression.py`).
- Vérifier la JS : extraire le bloc `<script>` et `node --check` (remplacer `{{ current_user_id | tojson }}` par `1` avant le check).

## Fichiers clés
- `templates/settings.html` : **modèle de référence** (style, structure, méthodes JS).
- `templates/ventes.html` : POS + **modale Scanner Intelligent** (vision/OCR/code-barres) branchée sur `/api/identification/analyse` (+ `requestVisionCameraStream` fallback webcam).
- `templates/stock.html` : **modale Scanner par Photo** (ajout au stock : réappro via `/api/produits/<id>/reapprovisionner`, pré-remplissage + création) ; caméra = `webcamModal` produit réutilisée via `openWebcamModalForScan()` + `prefillProductFromCapture`.
- `templates/base.html` : sidebar (Comptabilité et Paramètres dans sections Finance/Système), `showToast`, couleur globale.
- `app/routes/api.py` : tous les endpoints (`/api/users/*` ~1516, `/api/compta/*` ~2139, `/api/settings/*` ~2444, `/api/identification/*` fin de fichier ~2616).
- `app/vision/` : pipeline vision complet. `app/models/identification.py` : dataset + apprentissage.
- `app.py` : sert l'app en **HTTP classique** (port 5000) — les fichiers SSL/certificat (`ssl_utils.py`, `installer_certificat.bat`, `instance/ssl/`) ont été supprimés après rejet de l'approche HTTPS par l'utilisateur.
- `app/models/user.py`, `app/models/parametre.py`, `app/models/comptabilite.py` : modèles.

## Remarques
- Base SQLite : `instance/motostock.db` (colonne `permissions` ajoutée par migration auto).
- Compte admin existant : `admin` (identifiants connus de l'utilisateur).
