"""
Modèle LoginLog pour le suivi des connexions
"""
from datetime import datetime
from app import db


class LoginLog(db.Model):
    """Modèle de journal des connexions"""
    __tablename__ = 'login_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80))
    success = db.Column(db.Boolean, default=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('login_logs', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'success': self.success,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f'<LoginLog {self.username} success={self.success}>'
