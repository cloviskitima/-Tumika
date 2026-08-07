-- Migration pour ajouter la colonne devise à la table produit
ALTER TABLE produit ADD COLUMN devise VARCHAR(10) DEFAULT 'XAF';
