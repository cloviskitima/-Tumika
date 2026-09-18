# Déploiement MotoStockIA #TUMIKA sur Render (plan gratuit)

Ce guide permet de mettre l'application en ligne sur [Render](https://render.com)
(plan **Free**, 750 h/mois), accessible depuis n'importe quel poste connecté,
**sans mise en veille** grâce à une tâche anti-veille intégrée.

---

## 1. Pré-requis

- Un compte GitHub, et ce dépôt déjà poussé sur GitHub (fait).
- Un compte [Render](https://render.com) gratuit.

---

## 2. Déploiement en 3 clics

1. Connectez-vous sur [dashboard.render.com](https://dashboard.render.com).
2. Bouton **New** → **Blueprint**.
3. Sélectionnez le dépôt GitHub `-Tumika`.
4. Render lit le fichier `render.yaml` et crée tout seul le service web
   `tumika` (plan free) puis le démarre (premier build : ~5-10 min).

Votre application est alors en ligne à l'adresse :

> `https://tumika.onrender.com`

(Le nom exact dépend de votre organisation/URL choisie par Render.)

---

## 3. Première connexion

- Ouvrez l'URL en ligne (`/login`).
- Compte par défaut (créé automatiquement si aucun utilisateur n'existe) :
  - **Nom d'utilisateur** : `admin`
  - **Mot de passe** : `admin123`
- **Changez immédiatement ce mot de passe** dans *Réglages → Sécurité*.

---

## 4. Anti-veille (l'application ne dort jamais)

Render free met l'instance en veille après **~15 minutes d'inactivité**.
Ce projet embarque une **tâche anti-veille** (`app/keepalive.py`) qui
s'auto-interroge toutes les **9 minutes** via votre URL publique
(`RENDER_EXTERNAL_URL`, renseignée automatiquement par Render) :

- Activée par la variable `ENABLE_KEEPALIVE=1` (déjà dans `render.yaml`).
- Endpoint interrogé : `/health` (public, très léger).

Aucune action supplémentaire n'est nécessaire : tant que l'application tourne,
elle se ping elle-même et ne se met jamais en veille.

> Option de secours externe (facultative) : vous pouvez aussi créer un
> "moniteur" gratuit sur [uptimerobot.com](https://uptimerobot.com) ou
> [cron-job.org](https://cron-job.org) qui consulte `https://<votre-url>/health`
> toutes les 5-10 min.

---

## 5. Sauvegarde des données (IMPORTANT)

- Sur le plan **free**, le disque est **éphémère** : toute donnée écrite en
  local (base SQLite `instance/motostock.db`, images uploadées) **est perdue**
  à chaque redémarrage / redéploiement.
- Pour protéger vos données : utilisez le bouton
  **Réglages → Sauvegarde GitHub** (configuré) pour pousser la base vers votre
  dépôt `-Tumika-backup`, et ce régulièrement.
- **Solution de persistance (optionnel)** : ajoutez une base PostgreSQL gratuite
  sur Render (*New → PostgreSQL*, plan free) puis décommentez le bloc
  `databases` / `DATABASE_URL` dans `render.yaml` et redéployez.
  ⚠️ L'application a été testée avec SQLite : **exportez vos données**
  (Réglages → Données → Exporter JSON) avant de basculer.

---

## 6. Variables d'environnement gérées

| Variable | Défaut | Rôle |
|---|---|---|
| `SECRET_KEY` | génération auto (Render) | chiffrement des sessions |
| `ENABLE_KEEPALIVE` | `1` | active l'anti-veille |
| `KEEP_ALIVE_INTERVAL` | `540` | intervalle (s) entre deux pings |
| `KEEP_ALIVE_URL` | `RENDER_EXTERNAL_URL` | URL publique interrogée |
| `PORT` | 8000 | port d'écoute (fourni par Render) |
| `DATABASE_URL` | — | PostgreSQL optionnel |

---

## 7. Dépannage rapide

- **Page 502 / build échoué** : consultez *Logs* de l'instance (build logs).
- **Camera/OCR capricieux en ligne** : ce sont des fonctionnalités locales
  (nécessitent la webcam) ; en ligne, scannez les produits via photo upload.
- **Images uploadées perdues** : normal sur le disque éphémère — préférez la
  sauvegarde GitHub.
- **Réinitialisation des données** : redéployez sans `DATABASE_URL` → la base
  repart à zéro puis recrée `admin` / `admin123`.

---

## 8. Re-déploiements futurs

Chaque `git push` sur `main` déclenche automatiquement un nouveau build
(`autoDeploy: true`). Vérifiez le statut sur le dashboard Render.