"""
Script de migration pour mettre à jour la base de données
Ajoute les colonnes image_url_1, image_url_2 et stock_min à la table produit
Crée la table users pour l'authentification
"""
import sqlite3
import os
from werkzeug.security import generate_password_hash

# Chemin vers la base de données
DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'motostock.db')

def migrate_produit_table():
    """Migration de la table produit"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Vérifier si les colonnes existent déjà
        cursor.execute("PRAGMA table_info(produit)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Ajouter image_url_1 si elle n'existe pas
        if 'image_url_1' not in columns:
            print("Ajout de la colonne image_url_1...")
            cursor.execute("ALTER TABLE produit ADD COLUMN image_url_1 VARCHAR(512)")
        else:
            print("La colonne image_url_1 existe déjà")
        
        # Ajouter image_url_2 si elle n'existe pas
        if 'image_url_2' not in columns:
            print("Ajout de la colonne image_url_2...")
            cursor.execute("ALTER TABLE produit ADD COLUMN image_url_2 VARCHAR(512)")
        else:
            print("La colonne image_url_2 existe déjà")
        
        # Ajouter stock_min si elle n'existe pas
        if 'stock_min' not in columns:
            print("Ajout de la colonne stock_min...")
            cursor.execute("ALTER TABLE produit ADD COLUMN stock_min INTEGER DEFAULT 5")
        else:
            print("La colonne stock_min existe déjà")
        
        conn.commit()
        conn.close()
        
        print("Migration de la table produit terminée!")
        return True
        
    except Exception as e:
        print(f"Erreur lors de la migration de la table produit: {e}")
        return False

def migrate_ventes_table():
    """Migration de la table ventes"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(ventes)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'date_echeance' not in columns:
            print("Ajout de la colonne date_echeance à ventes...")
            cursor.execute("ALTER TABLE ventes ADD COLUMN date_echeance DATETIME")
        else:
            print("La colonne date_echeance existe déjà dans ventes")

        if 'devise' not in columns:
            print("Ajout de la colonne devise à ventes...")
            cursor.execute("ALTER TABLE ventes ADD COLUMN devise VARCHAR(10) DEFAULT 'XAF'")
        else:
            print("La colonne devise existe déjà dans ventes")

        if 'taux_change' not in columns:
            print("Ajout de la colonne taux_change à ventes...")
            cursor.execute("ALTER TABLE ventes ADD COLUMN taux_change FLOAT")
        else:
            print("La colonne taux_change existe déjà dans ventes")

        conn.commit()
        conn.close()
        print("Migration de la table ventes terminée!")
        return True
    except Exception as e:
        print(f"Erreur lors de la migration de la table ventes: {e}")
        return False


def migrate_taux_change_table():
    """Migration de la table taux_change"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(taux_change)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'effective_date' not in columns:
            print("Ajout de la colonne effective_date à taux_change...")
            cursor.execute("ALTER TABLE taux_change ADD COLUMN effective_date DATE")
            cursor.execute("UPDATE taux_change SET effective_date = DATE('now') WHERE effective_date IS NULL")
        else:
            print("La colonne effective_date existe déjà dans taux_change")

        conn.commit()
        conn.close()
        print("Migration de la table taux_change terminée!")
        return True
    except Exception as e:
        print(f"Erreur lors de la migration de la table taux_change: {e}")
        return False


def migrate_caisse_table():
    """Migration de la table caisse_mouvements"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(caisse_mouvements)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'devise' not in columns:
            print("Ajout de la colonne devise à caisse_mouvements...")
            cursor.execute("ALTER TABLE caisse_mouvements ADD COLUMN devise VARCHAR(10) DEFAULT 'XAF'")
        else:
            print("La colonne devise existe déjà dans caisse_mouvements")

        if 'taux_change' not in columns:
            print("Ajout de la colonne taux_change à caisse_mouvements...")
            cursor.execute("ALTER TABLE caisse_mouvements ADD COLUMN taux_change FLOAT")
        else:
            print("La colonne taux_change existe déjà dans caisse_mouvements")

        conn.commit()
        conn.close()
        print("Migration de la table caisse_mouvements terminée!")
        return True
    except Exception as e:
        print(f"Erreur lors de la migration de la table caisse_mouvements: {e}")
        return False


def create_users_table():
    """Création de la table users"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Vérifier si la table existe déjà
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        if cursor.fetchone():
            print("La table user existe déjà")
            conn.close()
            return True
        
        # Créer la table users
        print("Création de la table user...")
        cursor.execute("""
            CREATE TABLE user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(80) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                first_name VARCHAR(50),
                last_name VARCHAR(50),
                role VARCHAR(20) DEFAULT 'user',
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME
            )
        """)
        
        # Créer des index
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_username ON user(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_email ON user(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_role ON user(role)")
        
        conn.commit()
        conn.close()
        
        print("Table user créée avec succès!")
        return True
        
    except Exception as e:
        print(f"Erreur lors de la création de la table user: {e}")
        return False

def add_default_user():
    """Ajouter un utilisateur par défaut"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Vérifier si un utilisateur existe déjà
        cursor.execute("SELECT COUNT(*) FROM user")
        if cursor.fetchone()[0] > 0:
            print("Un utilisateur existe déjà dans la base de données")
            conn.close()
            return True
        
        # Créer l'utilisateur par défaut (admin/admin123)
        print("Création de l'utilisateur par défaut...")
        password_hash = generate_password_hash('admin123')
        
        cursor.execute("""
            INSERT INTO user (username, email, password_hash, first_name, last_name, role, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('admin', 'admin@motostock.local', password_hash, 'Administrateur', 'Principal', 'admin', 1))
        
        conn.commit()
        conn.close()
        
        print("Utilisateur par défaut créé avec succès!")
        print("Username: admin")
        print("Password: admin123")
        return True
        
    except Exception as e:
        print(f"Erreur lors de la création de l'utilisateur par défaut: {e}")
        return False

def migrate_database():
    """Exécute toutes les migrations"""
    if not os.path.exists(DB_PATH):
        print(f"Base de données non trouvée: {DB_PATH}")
        return False
    
    print("Début de la migration...")
    print("-" * 50)
    
    success = True
    
    # Migration de la table produit
    if not migrate_produit_table():
        success = False

    # Migration de la table ventes
    if not migrate_ventes_table():
        success = False

    # Migration de la table taux_change
    if not migrate_taux_change_table():
        success = False

    # Migration de la table caisse_mouvements
    if not migrate_caisse_table():
        success = False
    
    # Création de la table users
    if not create_users_table():
        success = False
    
    # Ajout de l'utilisateur par défaut
    if not add_default_user():
        success = False
    
    print("-" * 50)
    if success:
        print("Migration terminée avec succès!")
    else:
        print("Migration terminée avec des erreurs")
    
    return success

if __name__ == "__main__":
    migrate_database()
