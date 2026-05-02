from datetime import datetime
from app import db

class LoungeBooking(db.Model):
    __tablename__ = "lounge_bookings"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    number_of_people = db.Column(db.Integer, nullable=False)
    purpose = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default="booked")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
