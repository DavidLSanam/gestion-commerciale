"""Application de gestion commerciale pour les acteurs du secteur informel.

Modules : catégories, produits, approvisionnements, ventes, dépenses,
tableau de bord statistique.
"""
import os
from collections import defaultdict
from datetime import date

from flask import Flask, flash, redirect, render_template, request, url_for
from pymysql.err import IntegrityError

from db import close_db, execute, query

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cle-de-dev-a-changer")
app.teardown_appcontext(close_db)


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
@app.template_filter("fcfa")
def fcfa(valeur):
    """Formate un montant : 1234567.5 -> '1 234 568 FCFA'."""
    try:
        return f"{float(valeur or 0):,.0f}".replace(",", " ") + " FCFA"
    except (TypeError, ValueError):
        return valeur


def lire_nombre(champ, entier=False, minimum=0, strict=False):
    """Lit un champ numérique du formulaire et vérifie sa validité."""
    brut = (request.form.get(champ) or "").replace(" ", "").replace(",", ".")
    try:
        val = int(brut) if entier else float(brut)
    except ValueError:
        raise ValueError(f"Le champ « {champ} » doit être un nombre.")
    if val < minimum or (strict and val == minimum):
        signe = ">" if strict else "≥"
        raise ValueError(f"Le champ « {champ} » doit être {signe} {minimum}.")
    return val


def lire_texte(champ):
    val = (request.form.get(champ) or "").strip()
    if not val:
        raise ValueError(f"Le champ « {champ} » est obligatoire.")
    return val


def lire_date(champ):
    val = request.form.get(champ) or ""
    try:
        return date.fromisoformat(val).isoformat()
    except ValueError:
        raise ValueError(f"Le champ « {champ} » doit être une date valide.")


def stock_produit(id_produit):
    """Stock = total approvisionné - total vendu."""
    r = query(
        """SELECT
             COALESCE((SELECT SUM(quantite) FROM APPROVISIONNEMENT WHERE id_produit=%s),0)
           - COALESCE((SELECT SUM(quantite) FROM VENTE WHERE id_produit=%s),0) AS stock""",
        (id_produit, id_produit), one=True)
    return int(r["stock"] or 0)


def liste_produits():
    return query(
        """SELECT p.id_produit, p.designation, p.prix_vente, c.libelle AS categorie
           FROM PRODUIT p JOIN CATEGORIE_PRODUIT c ON c.id_categorie = p.id_categorie
           ORDER BY p.designation""")


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    debut = request.args.get("debut") or "1900-01-01"
    fin = request.args.get("fin") or "2999-12-31"

    ventes = query(
        """SELECT v.date_vente AS d, v.id_produit, v.quantite, v.prix_unitaire, p.designation
           FROM VENTE v JOIN PRODUIT p ON p.id_produit = v.id_produit
           WHERE v.date_vente BETWEEN %s AND %s""", (debut, fin))
    appros = query(
        """SELECT date_appro AS d, id_produit, quantite, prix_achat
           FROM APPROVISIONNEMENT WHERE date_appro BETWEEN %s AND %s""", (debut, fin))
    depenses = query(
        "SELECT date_depense AS d, montant FROM DEPENSE WHERE date_depense BETWEEN %s AND %s",
        (debut, fin))

    # Coût unitaire moyen pondéré d'achat par produit (sur tout l'historique)
    cmup = {r["id_produit"]: float(r["cout"]) for r in query(
        """SELECT id_produit, SUM(quantite*prix_achat)/SUM(quantite) AS cout
           FROM APPROVISIONNEMENT GROUP BY id_produit""")}

    ca = sum(float(v["quantite"]) * float(v["prix_unitaire"]) for v in ventes)
    cout_ventes = sum(v["quantite"] * cmup.get(v["id_produit"], 0) for v in ventes)
    achats = sum(float(a["quantite"]) * float(a["prix_achat"]) for a in appros)
    total_dep = sum(float(d["montant"]) for d in depenses)
    marge = ca - cout_ventes
    resultat = marge - total_dep

    # Évolution mensuelle
    mois = defaultdict(lambda: {"ca": 0.0, "achats": 0.0, "depenses": 0.0})
    for v in ventes:
        mois[str(v["d"])[:7]]["ca"] += float(v["quantite"]) * float(v["prix_unitaire"])
    for a in appros:
        mois[str(a["d"])[:7]]["achats"] += float(a["quantite"]) * float(a["prix_achat"])
    for d in depenses:
        mois[str(d["d"])[:7]]["depenses"] += float(d["montant"])
    evolution = [{"mois": m, **mois[m]} for m in sorted(mois)]

    # Top 5 des produits par chiffre d'affaires
    par_produit = defaultdict(lambda: {"quantite": 0, "ca": 0.0})
    for v in ventes:
        par_produit[v["designation"]]["quantite"] += v["quantite"]
        par_produit[v["designation"]]["ca"] += float(v["quantite"]) * float(v["prix_unitaire"])
    top = sorted(par_produit.items(), key=lambda kv: kv[1]["ca"], reverse=True)[:5]

    # Stocks
    stocks = query(
        """SELECT p.designation,
             COALESCE((SELECT SUM(quantite) FROM APPROVISIONNEMENT a WHERE a.id_produit=p.id_produit),0)
           - COALESCE((SELECT SUM(quantite) FROM VENTE v WHERE v.id_produit=p.id_produit),0) AS stock
           FROM PRODUIT p ORDER BY stock, p.designation""")

    return render_template(
        "index.html", ca=ca, achats=achats, depenses=total_dep, marge=marge,
        resultat=resultat, nb_ventes=len(ventes),
        taux_marge=(marge / ca * 100) if ca else 0,
        evolution=evolution, top=top, stocks=stocks,
        debut=request.args.get("debut", ""), fin=request.args.get("fin", ""))


# ---------------------------------------------------------------------------
# Module 1a : catégories
# ---------------------------------------------------------------------------
@app.route("/categories")
def categories():
    rows = query(
        """SELECT c.id_categorie, c.libelle, COUNT(p.id_produit) AS nb_produits
           FROM CATEGORIE_PRODUIT c LEFT JOIN PRODUIT p ON p.id_categorie = c.id_categorie
           GROUP BY c.id_categorie, c.libelle ORDER BY c.libelle""")
    return render_template("categories.html", categories=rows)


@app.route("/categories/ajouter", methods=["GET", "POST"])
@app.route("/categories/<int:id>/modifier", methods=["GET", "POST"])
def categorie_form(id=None):
    cat = query("SELECT * FROM CATEGORIE_PRODUIT WHERE id_categorie=%s", (id,), one=True) if id else None
    if id and not cat:
        flash("Catégorie introuvable.", "danger")
        return redirect(url_for("categories"))
    if request.method == "POST":
        try:
            libelle = lire_texte("libelle")
            if id:
                execute("UPDATE CATEGORIE_PRODUIT SET libelle=%s WHERE id_categorie=%s", (libelle, id))
                flash("Catégorie modifiée.", "success")
            else:
                execute("INSERT INTO CATEGORIE_PRODUIT (libelle) VALUES (%s)", (libelle,))
                flash("Catégorie ajoutée.", "success")
            return redirect(url_for("categories"))
        except ValueError as e:
            flash(str(e), "danger")
        except IntegrityError:
            flash("Cette catégorie existe déjà.", "danger")
        cat = {"libelle": request.form.get("libelle", "")}
    return render_template("categorie_form.html", cat=cat, id=id)


@app.route("/categories/<int:id>/supprimer", methods=["POST"])
def categorie_supprimer(id):
    try:
        execute("DELETE FROM CATEGORIE_PRODUIT WHERE id_categorie=%s", (id,))
        flash("Catégorie supprimée.", "success")
    except IntegrityError:
        flash("Impossible : des produits appartiennent à cette catégorie.", "danger")
    return redirect(url_for("categories"))


# ---------------------------------------------------------------------------
# Module 1b : produits
# ---------------------------------------------------------------------------
@app.route("/produits")
def produits():
    rows = query(
        """SELECT p.id_produit, p.designation, p.prix_vente, c.libelle AS categorie,
             COALESCE((SELECT SUM(quantite) FROM APPROVISIONNEMENT a WHERE a.id_produit=p.id_produit),0)
           - COALESCE((SELECT SUM(quantite) FROM VENTE v WHERE v.id_produit=p.id_produit),0) AS stock
           FROM PRODUIT p JOIN CATEGORIE_PRODUIT c ON c.id_categorie = p.id_categorie
           ORDER BY c.libelle, p.designation""")
    return render_template("produits.html", produits=rows)


@app.route("/produits/ajouter", methods=["GET", "POST"])
@app.route("/produits/<int:id>/modifier", methods=["GET", "POST"])
def produit_form(id=None):
    cats = query("SELECT * FROM CATEGORIE_PRODUIT ORDER BY libelle")
    prod = query("SELECT * FROM PRODUIT WHERE id_produit=%s", (id,), one=True) if id else None
    if id and not prod:
        flash("Produit introuvable.", "danger")
        return redirect(url_for("produits"))
    if not cats:
        flash("Créez d'abord une catégorie.", "warning")
        return redirect(url_for("categorie_form"))
    if request.method == "POST":
        try:
            data = (lire_texte("designation"), lire_nombre("prix_vente"),
                    int(request.form["id_categorie"]))
            if id:
                execute("""UPDATE PRODUIT SET designation=%s, prix_vente=%s, id_categorie=%s
                           WHERE id_produit=%s""", data + (id,))
                flash("Produit modifié.", "success")
            else:
                execute("""INSERT INTO PRODUIT (designation, prix_vente, id_categorie)
                           VALUES (%s,%s,%s)""", data)
                flash("Produit ajouté.", "success")
            return redirect(url_for("produits"))
        except (ValueError, KeyError) as e:
            flash(str(e) if isinstance(e, ValueError) else "Choisissez une catégorie.", "danger")
        except IntegrityError:
            flash("Catégorie invalide.", "danger")
        prod = request.form
    return render_template("produit_form.html", prod=prod, cats=cats, id=id)


@app.route("/produits/<int:id>/supprimer", methods=["POST"])
def produit_supprimer(id):
    try:
        execute("DELETE FROM PRODUIT WHERE id_produit=%s", (id,))
        flash("Produit supprimé.", "success")
    except IntegrityError:
        flash("Impossible : ce produit a des ventes ou des approvisionnements.", "danger")
    return redirect(url_for("produits"))


# ---------------------------------------------------------------------------
# Module 2 : approvisionnements
# ---------------------------------------------------------------------------
@app.route("/approvisionnements")
def appros():
    rows = query(
        """SELECT a.*, p.designation, a.quantite*a.prix_achat AS montant
           FROM APPROVISIONNEMENT a JOIN PRODUIT p ON p.id_produit = a.id_produit
           ORDER BY a.date_appro DESC, a.id_appro DESC""")
    return render_template("appros.html", appros=rows,
                           total=sum(float(r["montant"]) for r in rows))


@app.route("/approvisionnements/ajouter", methods=["GET", "POST"])
@app.route("/approvisionnements/<int:id>/modifier", methods=["GET", "POST"])
def appro_form(id=None):
    prods = liste_produits()
    appro = query("SELECT * FROM APPROVISIONNEMENT WHERE id_appro=%s", (id,), one=True) if id else None
    if id and not appro:
        flash("Approvisionnement introuvable.", "danger")
        return redirect(url_for("appros"))
    if not prods:
        flash("Créez d'abord un produit.", "warning")
        return redirect(url_for("produit_form"))
    if request.method == "POST":
        try:
            id_produit = int(request.form["id_produit"])
            quantite = lire_nombre("quantite", entier=True, strict=True)
            if id:  # une modification ne doit pas rendre le stock négatif
                ancien = appro["quantite"] if appro["id_produit"] == id_produit else 0
                if id_produit != appro["id_produit"] and stock_produit(appro["id_produit"]) - appro["quantite"] < 0:
                    raise ValueError("Changement impossible : le stock de l'ancien produit deviendrait négatif.")
                if stock_produit(id_produit) - ancien + quantite < 0:
                    raise ValueError("Quantité trop faible : des ventes ont déjà été faites sur ce stock.")
            data = (lire_date("date_appro"), id_produit, quantite, lire_nombre("prix_achat"))
            if id:
                execute("""UPDATE APPROVISIONNEMENT SET date_appro=%s, id_produit=%s, quantite=%s,
                           prix_achat=%s WHERE id_appro=%s""", data + (id,))
                flash("Approvisionnement modifié.", "success")
            else:
                execute("""INSERT INTO APPROVISIONNEMENT (date_appro, id_produit, quantite, prix_achat)
                           VALUES (%s,%s,%s,%s)""", data)
                flash("Approvisionnement enregistré.", "success")
            return redirect(url_for("appros"))
        except (ValueError, KeyError) as e:
            flash(str(e) if isinstance(e, ValueError) else "Choisissez un produit.", "danger")
        appro = request.form
    return render_template("appro_form.html", appro=appro, prods=prods, id=id,
                           today=date.today().isoformat())


@app.route("/approvisionnements/<int:id>/supprimer", methods=["POST"])
def appro_supprimer(id):
    appro = query("SELECT * FROM APPROVISIONNEMENT WHERE id_appro=%s", (id,), one=True)
    if appro and stock_produit(appro["id_produit"]) - appro["quantite"] < 0:
        flash("Impossible : ce stock a déjà été en partie vendu.", "danger")
    else:
        execute("DELETE FROM APPROVISIONNEMENT WHERE id_appro=%s", (id,))
        flash("Approvisionnement supprimé.", "success")
    return redirect(url_for("appros"))


# ---------------------------------------------------------------------------
# Module 3 : ventes
# ---------------------------------------------------------------------------
@app.route("/ventes")
def ventes():
    rows = query(
        """SELECT v.*, p.designation, v.quantite*v.prix_unitaire AS montant
           FROM VENTE v JOIN PRODUIT p ON p.id_produit = v.id_produit
           ORDER BY v.date_vente DESC, v.id_vente DESC""")
    return render_template("ventes.html", ventes=rows,
                           total=sum(float(r["montant"]) for r in rows))


@app.route("/ventes/ajouter", methods=["GET", "POST"])
@app.route("/ventes/<int:id>/modifier", methods=["GET", "POST"])
def vente_form(id=None):
    prods = liste_produits()
    for p in prods:
        p["stock"] = stock_produit(p["id_produit"])
    vente = query("SELECT * FROM VENTE WHERE id_vente=%s", (id,), one=True) if id else None
    if id and not vente:
        flash("Vente introuvable.", "danger")
        return redirect(url_for("ventes"))
    if not prods:
        flash("Créez d'abord un produit.", "warning")
        return redirect(url_for("produit_form"))
    if request.method == "POST":
        try:
            id_produit = int(request.form["id_produit"])
            quantite = lire_nombre("quantite", entier=True, strict=True)
            dispo = stock_produit(id_produit)
            if id and vente["id_produit"] == id_produit:
                dispo += vente["quantite"]  # on « rend » l'ancienne quantité
            if quantite > dispo:
                raise ValueError(f"Stock insuffisant : {dispo} unité(s) disponible(s).")
            data = (lire_date("date_vente"), id_produit, quantite, lire_nombre("prix_unitaire"))
            if id:
                execute("""UPDATE VENTE SET date_vente=%s, id_produit=%s, quantite=%s,
                           prix_unitaire=%s WHERE id_vente=%s""", data + (id,))
                flash("Vente modifiée.", "success")
            else:
                execute("""INSERT INTO VENTE (date_vente, id_produit, quantite, prix_unitaire)
                           VALUES (%s,%s,%s,%s)""", data)
                flash("Vente enregistrée.", "success")
            return redirect(url_for("ventes"))
        except (ValueError, KeyError) as e:
            flash(str(e) if isinstance(e, ValueError) else "Choisissez un produit.", "danger")
        vente = request.form
    return render_template("vente_form.html", vente=vente, prods=prods, id=id,
                           today=date.today().isoformat())


@app.route("/ventes/<int:id>/supprimer", methods=["POST"])
def vente_supprimer(id):
    execute("DELETE FROM VENTE WHERE id_vente=%s", (id,))
    flash("Vente supprimée.", "success")
    return redirect(url_for("ventes"))


# ---------------------------------------------------------------------------
# Module 4 : dépenses
# ---------------------------------------------------------------------------
@app.route("/depenses")
def depenses():
    rows = query("SELECT * FROM DEPENSE ORDER BY date_depense DESC, id_depense DESC")
    return render_template("depenses.html", depenses=rows,
                           total=sum(float(r["montant"]) for r in rows))


@app.route("/depenses/ajouter", methods=["GET", "POST"])
@app.route("/depenses/<int:id>/modifier", methods=["GET", "POST"])
def depense_form(id=None):
    dep = query("SELECT * FROM DEPENSE WHERE id_depense=%s", (id,), one=True) if id else None
    if id and not dep:
        flash("Dépense introuvable.", "danger")
        return redirect(url_for("depenses"))
    if request.method == "POST":
        try:
            data = (lire_date("date_depense"), lire_texte("libelle"), lire_nombre("montant"))
            if id:
                execute("""UPDATE DEPENSE SET date_depense=%s, libelle=%s, montant=%s
                           WHERE id_depense=%s""", data + (id,))
                flash("Dépense modifiée.", "success")
            else:
                execute("INSERT INTO DEPENSE (date_depense, libelle, montant) VALUES (%s,%s,%s)", data)
                flash("Dépense enregistrée.", "success")
            return redirect(url_for("depenses"))
        except ValueError as e:
            flash(str(e), "danger")
        dep = request.form
    return render_template("depense_form.html", dep=dep, id=id, today=date.today().isoformat())


@app.route("/depenses/<int:id>/supprimer", methods=["POST"])
def depense_supprimer(id):
    execute("DELETE FROM DEPENSE WHERE id_depense=%s", (id,))
    flash("Dépense supprimée.", "success")
    return redirect(url_for("depenses"))


# ---------------------------------------------------------------------------
@app.errorhandler(500)
def erreur_serveur(e):
    return render_template("erreur.html", message=str(getattr(e, "original_exception", e))), 500


if __name__ == "__main__":
    app.run(debug=True)
