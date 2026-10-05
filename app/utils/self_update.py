"""Mise à jour automatique de l'application MotoStock #TUMIKA (100 % hors ligne).

L'utilisateur choisit un dossier (clé USB / dossier livré) contenant les
nouveaux fichiers dans la même arborescence que le projet. L'application :
  1. analyse le dossier et liste les fichiers nouveaux / modifiés ;
  2. copie les fichiers autorisés EN PLACE (aucun fichier déplacé) ;
  3. purge les __pycache__ concernés ;
  4. demande un redémarrage (dialog avec compte à rebours) pour recharger le
     nouveau code Python, sinon redémarre automatiquement (Windows local).

SÉCURITÉ : la base de données (motostock.db), les fichiers *.db/*.sqlite,
*.log, *.pyc et les exécutables ne sont JAMAIS touchés. Aucune donnée
existante n'est modifiée ni supprimée.
"""
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # dossier du projet (contient app/, templates/, static/)

# Dossiers dont les fichiers peuvent être mis à jour.
ALLOWED_DIRS = ("templates", "static", "mobile_pwa", "app", "migrations", "assets")

# Fichiers racine pouvant être mis à jour.
ALLOWED_ROOT_FILES = {
    "app.py", "serve.py", "wsgi.py", "requirements.txt",
    "migrate_db.py", "init_db.py",
}

# Toujours ignorés, même s'ils sont dans un dossier autorisé.
EXCLUDE_NAMES = {
    "__pycache__", ".git", ".github", ".venv", "venv", "node_modules",
    "instance", "setup", "build", "dist", "backups", "uploads",
    "AI-Vision-Assistant-main", "AI-Vision-Assistant", "site-packages",
}

# Extensions toujours ignorées (surtout la base de données et les exécutables).
EXCLUDE_EXT = (".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".pyo",
               ".exe", ".dll", ".bin", ".pyz", ".pyd")


def live_root():
    return ROOT


def restart_flag_path():
    return ROOT / "instance" / "restart.flag"


def auto_restart_possible():
    """Redémarrage automatique possible : Windows + exécution locale (pas Render)."""
    if os.name != "nt":
        return False
    if os.environ.get("RENDER_EXTERNAL_URL"):
        return False
    return True


# ---------------------------------------------------------------------------
# Chemins et autorisation
# ---------------------------------------------------------------------------

def safe_join(root, rel):
    """Renvoie le chemin absolu de `rel` sous `root`, ou None si dangereux."""
    if not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        return None
    rel = rel.replace("\\", "/")
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    if not parts:
        return None
    candidate = root.joinpath(*parts)
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not str(resolved).startswith(str(root.resolve())):
        return None
    return candidate


def is_allowed(rel):
    """Vérifie qu'un fichier relatif fait partie des fichiers autorisés."""
    if not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        return False
    norm = rel.replace("\\", "/").lstrip("/")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts:
        return False
    if any(p in EXCLUDE_NAMES or p == ".." for p in parts):
        return False
    for p in parts:
        if p.startswith(".") and p not in (".",) and p.lower() not in (".env",):
            pass
    if any(p.endswith(EXCLUDE_EXT) for p in parts):
        return False
    if len(parts) == 1:
        return parts[0] in ALLOWED_ROOT_FILES
    return parts[0] in ALLOWED_DIRS


# ---------------------------------------------------------------------------
# Analyse
# ---------------------------------------------------------------------------

def analyze_update(manifest, root=None):
    """Analyse une liste {path, size} et renvoie l'état de chaque fichier."""
    root = Path(root) if root else live_root()
    states = {"nouveau": [], "modifie": [], "identique": [], "ignore": []}
    for entry in manifest or []:
        rel = (entry.get("path") or "").replace("\\", "/").lstrip("/")
        if not is_allowed(rel):
            states["ignore"].append({"path": rel, "status": "ignore"})
            continue
        target = safe_join(root, rel)
        if target is None:
            states["ignore"].append({"path": rel, "status": "ignore"})
            continue
        if not target.exists():
            states["nouveau"].append({"path": rel, "status": "nouveau"})
            continue
        local_size = target.stat().st_size
        remote_size = entry.get("size")
        if remote_size is None or local_size != remote_size:
            states["modifie"].append({"path": rel, "status": "modifie"})
        else:
            states["identique"].append({"path": rel, "status": "identique"})
    states["total_changes"] = len(states["nouveau"]) + len(states["modifie"])
    return states


# ---------------------------------------------------------------------------
# Application (en place, jamais la base)
# ---------------------------------------------------------------------------

def _purge_pycache(root, rel):
    parts = rel.replace("\\", "/").split("/")
    if len(parts) > 1:
        parent = root.joinpath(*parts[:-1])
        pc = parent / "__pycache__"
        if pc.is_dir():
            shutil.rmtree(pc, ignore_errors=True)


def apply_update(files, root=None):
    """Enregistre les fichiers reçus (multipart) EN PLACE dans le projet.

    `files` : liste de (rel_path, bytes|file_like). Ne touche jamais à la
    base de données ni aux fichiers exclus.
    """
    root = Path(root) if root else live_root()
    applied = []
    ignored = []
    for rel_raw, data in files:
        rel = (rel_raw or "").replace("\\", "/").lstrip("/")
        if not is_allowed(rel):
            ignored.append(rel)
            continue
        target = safe_join(root, rel)
        if target is None:
            ignored.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(data, "read"):
                with open(target, "wb") as handle:
                    shutil.copyfileobj(data, handle)
            else:
                with open(target, "wb") as handle:
                    handle.write(data)
        except OSError:
            ignored.append(rel)
            continue
        applied.append(rel)
        _purge_pycache(root, rel)
    _marquer_version_appliquee(len(applied), root)
    return {"applied": applied, "ignored": ignored}


def _marquer_version_appliquee(nb_fichiers, root=None):
    """Note la date de la dernière installation dans instance/version_maj.txt.

    Permet à l'utilisateur de vérifier d'un coup d'œil, en bas de la barre
    latérale, que l'interface affichée est bien celle qui vient d'être
    installée.
    """
    root = Path(root) if root else live_root()
    try:
        d = root / "instance"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "version_maj.txt", "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%d/%m/%Y %H:%M"))
    except Exception:
        pass



# ---------------------------------------------------------------------------
# Informations d'état
# ---------------------------------------------------------------------------

def update_info(root=None):
    """Infos affichées dans les réglages."""
    root = Path(root) if root else live_root()
    writable = os.access(str(root), os.W_OK)
    skip_dirs = EXCLUDE_NAMES | {"__pycache__", ".git", ".venv", "node_modules",
                                 "instance", "build", "dist"}
    count = 0
    if root.is_dir():
        for dirpath, dirnames, filenames in os.walk(str(root)):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            count += len([f for f in filenames if os.path.isfile(os.path.join(dirpath, f))])
    return {
        "root": str(root),
        "writable": writable,
        "files": count,
        "auto_restart": auto_restart_possible(),
    }


# ---------------------------------------------------------------------------
# Redémarrage automatique (Windows local)
# ---------------------------------------------------------------------------

def _build_restart_helper(port, pid, python, serve_py, root, log_path):
    """Script détaché en DEUX étapes qui ferme l'application puis la relance.

    Pourquoi deux étapes (constat de test sur poste réel) :
      le helper est lancé PAR le serveur. Un taskkill /T sur le serveur
      tue donc le helper avec lui, et la relance n'a jamais lieu. L'étape 1
      tue le serveur SANS /T, puis lance l'étape 2 qui, elle, est déjà
      orpheline : elle n'appartient plus à l'arbre du serveur et ne peut
      plus être tuée par accident.

    Autres corrections :
      - on attend que le port soit réellement libéré (le sleep d'1 seconde
        d'avant ne suffisait pas : serve.py voyait "port occupé" et
        sortait aussitôt, donc aucun redémarrage) ;
      - relance avec 5 tentatives et vérification que l'application répond ;
      - journal dans instance/restart.log.

    Les valeurs sont injectées par remplacement de jetons, jamais par
    l'opérateur %, car le code généré contient lui-même des %d et %s.
    """
    code = (
        "import os, socket, subprocess, sys, time\n"
        "PORT = @@PORT@@\n"
        "HOST = '127.0.0.1'\n"
        "LOG = @@LOG@@\n"
        "PYTHON = @@PYTHON@@\n"
        "SERVE = @@SERVE@@\n"
        "ROOT = @@ROOT@@\n"
        "PID = @@PID@@\n"
        "MOI = os.getpid()\n"
        "def log(msg):\n"
        "    try:\n"
        "        with open(LOG, 'a', encoding='utf-8') as f:\n"
        "            f.write(time.strftime('%H:%M:%S ') + msg + '\\n')\n"
        "    except Exception:\n"
        "        pass\n"
        "def pids_on_port():\n"
        "    pids = set()\n"
        "    try:\n"
        "        out = subprocess.run(['netstat', '-ano'], stdout=subprocess.PIPE,\n"
        "                             stderr=subprocess.DEVNULL, timeout=25)\n"
        "    except Exception:\n"
        "        return pids\n"
        "    for line in out.stdout.decode('latin-1', 'replace').splitlines():\n"
        "        parts = line.split()\n"
        "        if len(parts) < 5 or parts[0].upper() != 'TCP':\n"
        "            continue\n"
        "        if parts[1].rsplit(':', 1)[-1] != str(PORT):\n"
        "            continue\n"
        "        if parts[3].upper() != 'LISTENING':\n"
        "            continue\n"
        "        try:\n"
        "            pids.add(int(parts[4]))\n"
        "        except ValueError:\n"
        "            pass\n"
        "    return pids\n"
        "def port_occupe():\n"
        "    try:\n"
        "        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:\n"
        "            s.settimeout(0.5)\n"
        "            return s.connect_ex((HOST, PORT)) == 0\n"
        "    except Exception:\n"
        "        return True\n"
        "def tuer(p):\n"
        "    if int(p) == MOI:\n"
        "        return\n"
        "    try:\n"
        "        subprocess.run(['taskkill', '/PID', str(p), '/F'],\n"
        "                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "    except Exception:\n"
        "        pass\n"
        "def attendre_libre(limite):\n"
        "    fin = time.time() + limite\n"
        "    while time.time() < fin:\n"
        "        if not port_occupe() and not pids_on_port():\n"
        "            return True\n"
        "        for p in pids_on_port():\n"
        "            tuer(p)\n"
        "        time.sleep(0.5)\n"
        "    return False\n"
        "def etape2():\n"
        "    log('etape 2 : attente de la liberation du port %d' % PORT)\n"
        "    if not attendre_libre(45):\n"
        "        log('ECHEC : le port %d reste occupe apres 45 s' % PORT)\n"
        "    else:\n"
        "        log('port %d libere' % PORT)\n"
        "    for essai in range(1, 6):\n"
        "        try:\n"
        "            env = os.environ.copy()\n"
        "            env['MOTOSTOCK_WAIT_PORT'] = '45'\n"
        "            env['MOTOSTOCK_PORT'] = str(PORT)\n"
        "            subprocess.Popen([PYTHON, SERVE], cwd=ROOT, env=env,\n"
        "                             creationflags=subprocess.CREATE_NEW_CONSOLE)\n"
        "        except Exception as e:\n"
        "            log('relance impossible : %s' % e)\n"
        "            continue\n"
        "        for _ in range(20):\n"
        "            time.sleep(1)\n"
        "            if not port_occupe():\n"
        "                log('application relancee (essai %d), de nouveau en ecoute' % essai)\n"
        "                return\n"
        "        time.sleep(2)\n"
        "        log('essai %d : le port %d ne reparait pas' % (essai, PORT))\n"
        "    log('ECHEC : application non redemarree apres 5 tentatives')\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'etape2':\n"
        "    etape2()\n"
        "    sys.exit(0)\n"
        "log('etape 1 : arret du serveur port %d, pid %d' % (PORT, PID))\n"
        "time.sleep(1.5)\n"
        "tuer(PID)\n"
        "for p in pids_on_port():\n"
        "    tuer(p)\n"
        "log('etape 1 : serveur arrete, passement a l etape 2')\n"
        "try:\n"
        "    flags = getattr(subprocess, 'DETACHED_PROCESS', 8) | "
        "getattr(subprocess, 'CREATE_NO_WINDOW', 0)\n"
        "    subprocess.Popen([PYTHON, os.path.abspath(__file__), 'etape2'],\n"
        "                     cwd=ROOT, creationflags=flags,\n"
        "                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, close_fds=True)\n"
        "except Exception as e:\n"
        "    log('impossible de lancer l etape 2 : %s' % e)\n"
    )
    valeurs = {
        '@@PORT@@': repr(int(port)),
        '@@LOG@@': repr(str(log_path)),
        '@@PYTHON@@': repr(str(python)),
        '@@SERVE@@': repr(str(serve_py)),
        '@@ROOT@@': repr(str(root)),
        '@@PID@@': repr(int(pid)),
    }
    for jeton, valeur in valeurs.items():
        code = code.replace(jeton, valeur)
    return code


def schedule_restart():
    """Ferme l'application puis la relance.

    Réponse HTTP renvoyée d'abord : un assistant détaché prend le relais,
    arrête le serveur, attend la libération du port, relance serve.py et
    vérifie que l'application écoute de nouveau.
    Journal de diagnostic : instance/restart.log
    """
    if not auto_restart_possible():
        try:
            restart_flag_path().write_text("1", encoding="utf-8")
        except Exception:
            pass
        return False

    pid = os.getpid()
    python = sys.executable or "python"
    serve_py = str((ROOT / "serve.py").resolve())
    root = str(ROOT.resolve())
    try:
        restart_flag_path().write_text("1", encoding="utf-8")
    except Exception:
        pass

    try:
        port = int(os.environ.get("MOTOSTOCK_PORT", "5000"))
    except (TypeError, ValueError):
        port = 5000

    instance = ROOT / "instance"
    try:
        instance.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    log_path = str(instance / "restart.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("--- redemarrage %s ---\n" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass

    helper = instance / "restart_helper.py"
    try:
        helper.write_text(_build_restart_helper(port, pid, python, serve_py, root, log_path),
                          encoding="utf-8")
    except Exception:
        return False

    try:
        flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "DETACHED_PROCESS", 8)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.Popen([python, str(helper)],
                         creationflags=flags,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         cwd=root,
                         close_fds=True)
        return True
    except Exception:
        return False
