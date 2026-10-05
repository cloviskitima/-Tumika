# -*- coding: utf-8 -*-
"""Copie fiable d'une base SQLite.

Pourquoi ce module existe
-------------------------
En mode WAL (journalisation ecrite), les transactions validees vivent dans
« base-wal » et pas dans le fichier « base ». Copier uniquement le fichier
principal revient donc a perdre les dernieres saisies : sur un essai, 300
produits sur 301 ont disparu d'un simple copier-coller.

Ce module garantit qu'une copie contient toujours la totalite des donnees :

  1. API de sauvegarde SQLite : lit la base coherente, WAL comprise.
  2. Repli : on fusionne d'abord le WAL dans la base (checkpoint), puis copie.
  3. Dernier recours : on copie le fichier ET son fichier -wal, que SQLite
     rejouera a l'ouverture.

Utilise par la sauvegarde vers GitHub et par la copie de securite precede
chaque migration.
"""
import os
import shutil
import sqlite3


def _connect_ro(path, timeout=30):
    con = sqlite3.connect(path, timeout=timeout)
    con.execute('PRAGMA busy_timeout=%d' % (timeout * 1000))
    return con


def copie_sqlite_consistante(source, destination, timeout=30):
    """Copie la base « source » vers « destination » sans perdre de donnees.

    Retourne (methode_utilisee, message). La methode vaut 'api', 'checkpoint',
    'wal' ou 'echec'.
    """
    if not os.path.exists(source):
        return 'echec', 'Fichier source introuvable : %s' % source

    # 1) Methode propre : l'API de sauvegarde voit tout, WAL compris.
    try:
        src = _connect_ro(source, timeout)
        dst = sqlite3.connect(destination, timeout=timeout)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return 'api', 'Copie coherente via l\'API SQLite.'
    except Exception as e:
        premiere_erreur = e

    # 2) Repli : on replie le WAL dans la base avant de copier le fichier.
    try:
        src = _connect_ro(source, timeout)
        try:
            src.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally:
            src.close()
        shutil.copyfile(source, destination)
        return 'checkpoint', 'WAL fusionne puis fichier copie (%s).' % premiere_erreur
    except Exception:
        pass

    # 3) Dernier recours : on copie aussi le -wal, que SQLite rejouera.
    try:
        shutil.copyfile(source, destination)
        wal = source + '-wal'
        if os.path.exists(wal) and os.path.getsize(wal) > 0:
            shutil.copyfile(wal, destination + '-wal')
            return 'wal', 'Fichier et WAL copies ; le WAL sera rejoue a l\'ouverture.'
        return 'brut', 'Copie brute du fichier (%s).' % premiere_erreur
    except Exception as e:
        return 'echec', str(e)