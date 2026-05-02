from app import db

class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Numeric(10,2))
    category = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default="active")