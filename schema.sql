-- =====================================================================
--  Application de gestion commerciale - secteur informel
--  Script de création des tables (MySQL 8 / FreeDB)
-- =====================================================================
--  Sur FreeDB, la base est déjà créée depuis le tableau de bord
--  (nom du type freedb_xxxx) : on ne fait donc PAS de CREATE DATABASE.
--  En local uniquement, décommenter les deux lignes suivantes :
-- CREATE DATABASE IF NOT EXISTS gestion_commerciale CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE gestion_commerciale;

-- Suppression dans l'ordre inverse des dépendances (réexécution possible)
DROP TABLE IF EXISTS VENTE;
DROP TABLE IF EXISTS APPROVISIONNEMENT;
DROP TABLE IF EXISTS DEPENSE;
DROP TABLE IF EXISTS PRODUIT;
DROP TABLE IF EXISTS CATEGORIE_PRODUIT;

-- ---------------------------------------------------------------------
-- Phase 1 : catégories et produits
-- ---------------------------------------------------------------------
CREATE TABLE CATEGORIE_PRODUIT (
    id_categorie INT AUTO_INCREMENT PRIMARY KEY,
    libelle      VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE PRODUIT (
    id_produit   INT AUTO_INCREMENT PRIMARY KEY,
    designation  VARCHAR(150) NOT NULL,
    prix_vente   DECIMAL(12,2) NOT NULL CHECK (prix_vente >= 0),
    id_categorie INT NOT NULL,
    CONSTRAINT fk_produit_categorie
        FOREIGN KEY (id_categorie) REFERENCES CATEGORIE_PRODUIT(id_categorie)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Extension : approvisionnements, ventes, dépenses
-- ---------------------------------------------------------------------
CREATE TABLE APPROVISIONNEMENT (
    id_appro    INT AUTO_INCREMENT PRIMARY KEY,
    date_appro  DATE NOT NULL,
    id_produit  INT NOT NULL,
    quantite    INT NOT NULL CHECK (quantite > 0),
    prix_achat  DECIMAL(12,2) NOT NULL CHECK (prix_achat >= 0),
    CONSTRAINT fk_appro_produit
        FOREIGN KEY (id_produit) REFERENCES PRODUIT(id_produit)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE VENTE (
    id_vente      INT AUTO_INCREMENT PRIMARY KEY,
    date_vente    DATE NOT NULL,
    id_produit    INT NOT NULL,
    quantite      INT NOT NULL CHECK (quantite > 0),
    prix_unitaire DECIMAL(12,2) NOT NULL CHECK (prix_unitaire >= 0),
    CONSTRAINT fk_vente_produit
        FOREIGN KEY (id_produit) REFERENCES PRODUIT(id_produit)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE DEPENSE (
    id_depense   INT AUTO_INCREMENT PRIMARY KEY,
    date_depense DATE NOT NULL,
    libelle      VARCHAR(150) NOT NULL,
    montant      DECIMAL(12,2) NOT NULL CHECK (montant >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Données d'exemple (facultatif)
-- ---------------------------------------------------------------------
INSERT INTO CATEGORIE_PRODUIT (libelle) VALUES
    ('Alimentation'), ('Boissons'), ('Hygiène');

INSERT INTO PRODUIT (designation, prix_vente, id_categorie) VALUES
    ('Riz brisé 1 kg', 500, 1),
    ('Huile 1 L', 1300, 1),
    ('Sucre 1 kg', 700, 1),
    ('Eau minérale 1,5 L', 300, 2),
    ('Savon de Marseille', 250, 3);
