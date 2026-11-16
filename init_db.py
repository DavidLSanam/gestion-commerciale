"""Crée les tables dans la base (locale ou FreeDB) à partir de schema.sql.

Usage :  python init_db.py
Les paramètres de connexion sont lus dans .env / les variables d'environnement.
(Alternative : copier-coller schema.sql dans phpMyAdmin de FreeDB.)
"""
import os
import re

import pymysql
from dotenv import load_dotenv

load_dotenv()

with open("schema.sql", encoding="utf-8") as f:
    sql = re.sub(r"--[^\n]*", "", f.read())          # retire les commentaires
instructions = [s.strip() for s in sql.split(";") if s.strip()]

conn = pymysql.connect(
    host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT", 3306)),
    user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"], charset="utf8mb4",
)
with conn.cursor() as cur:
    for s in instructions:
        cur.execute(s)
conn.commit()
conn.close()
print(f"{len(instructions)} instructions exécutées : tables créées dans {os.environ['DB_NAME']}.")
