from extensions import db

class Branch(db.Model):
    __tablename__ = "branches"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    logo = db.Column(db.String(255), nullable=True)

    users = db.relationship("User", backref="branch", lazy=True)