import sqlite3

conn = sqlite3.connect('instance/motostock.db')
cursor = conn.cursor()

try:
    cursor.execute('ALTER TABLE produit ADD COLUMN devise VARCHAR(10) DEFAULT "XAF"')
    conn.commit()
    print('Colonne devise ajoutée avec succès')
except sqlite3.OperationalError as e:
    if 'duplicate column name' in str(e):
        print('La colonne devise existe déjà')
    else:
        print(f'Erreur: {e}')
finally:
    conn.close()
