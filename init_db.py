"""
Script d'initialisation de la base de données
"""
from app import create_app, db
from app.models.user import User
from app.models.produit import Produit
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    # Créer toutes les tables
    db.create_all()
    print("Tables créées avec succès!")
    
    # Vérifier si un utilisateur admin existe
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        # Créer l'utilisateur admin par défaut
        admin = User(
            username='admin',
            email='admin@motostock.local',
            first_name='Administrateur',
            last_name='Principal',
            role='admin',
            is_active=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Utilisateur admin créé avec succès!")
        print("Username: admin")
        print("Password: admin123")
    else:
        print("L'utilisateur admin existe déjà")
    
    print("Initialisation de la base de données terminée!")
