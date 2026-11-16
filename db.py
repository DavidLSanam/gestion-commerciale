"""Connexion à la base MySQL (locale ou distante FreeDB).

Les paramètres sont lus dans les variables d'environnement :
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.
En local, ils peuvent être placés dans un fichier .env (jamais publié sur GitHub).
Sur Render, ils sont définis dans l'onglet "Environment" du service.
"""
import os

import pymysql
from flask import g

try:  # python-dotenv est facultatif (utile en local)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_db():
    """Ouvre une connexion par requête HTTP (FreeDB limite le nombre de connexions)."""
    if "db" not in g:
        g.db = pymysql.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", 3306)),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "gestion_commerciale"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            connect_timeout=10,
        )
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=(), one=False):
    """Exécute un SELECT et renvoie une liste de dictionnaires (ou un seul)."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    """Exécute un INSERT / UPDATE / DELETE et valide la transaction."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, params)
        db.commit()
    except Exception:
        db.rollback()
        raise
