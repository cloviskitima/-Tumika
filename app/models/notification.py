"""
Modèle Notification pour le système de notifications
"""
from datetime import datetime
from app import db


class Notification(db.Model):
    """Modèle de notification"""
    __tablename__ = 'notification'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')  # info, success, warning, error
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    # Relation avec l'utilisateur
    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic', cascade='all, delete-orphan'))
    
    def mark_as_read(self):
        """Marque la notification comme lue"""
        if not self.read:
            self.read = True
            self.read_at = datetime.utcnow()
            db.session.commit()
    
    def to_dict(self):
        """Convertit la notification en dictionnaire"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'read': self.read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None
        }
    
    @staticmethod
    def create_notification(user_id, title, message, type='info'):
        """Crée une nouvelle notification"""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=type
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    
    def __repr__(self):
        return f'<Notification {self.title} - User {self.user_id}>'
