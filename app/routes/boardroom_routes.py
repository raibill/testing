from flask import Blueprint, request, jsonify
from datetime import datetime

from app import db
from app.models import BoardroomBooking

boardroom_bp = Blueprint("boardroom_routes", __name__)


# -----------------------------
# CREATE BOOKING
# -----------------------------
@boardroom_bp.route("/api/book-boardroom", methods=["POST"])
def book_boardroom():

    data = request.get_json()

    customer_name = data.get("customer_name")
    date_str = data.get("date")
    start_time_str = data.get("start_time")
    end_time_str = data.get("end_time")
    number_of_people = data.get("number_of_people")
    purpose = data.get("purpose")

    if not all([customer_name, date_str, start_time_str, end_time_str, number_of_people]):
        return jsonify({"error": "Missing required fields"}), 400

    date = datetime.strptime(date_str, "%Y-%m-%d").date()
    start_time = datetime.strptime(start_time_str, "%H:%M").time()
    end_time = datetime.strptime(end_time_str, "%H:%M").time()

    # CHECK FOR CONFLICT
    existing = BoardroomBooking.query.filter_by(date=date).all()

    for booking in existing:
        if (start_time < booking.end_time and end_time > booking.start_time):
            return jsonify({"error": "Time slot already booked"}), 400

    new_booking = BoardroomBooking(
        customer_name=customer_name,
        date=date,
        start_time=start_time,
        end_time=end_time,
        number_of_people=number_of_people,
        purpose=purpose
    )

    db.session.add(new_booking)
    db.session.commit()

    return jsonify({"message": "Boardroom booked successfully"})
    

# -----------------------------
# GET BOOKINGS
# -----------------------------
@boardroom_bp.route("/api/boardroom-bookings")
def get_bookings():

    bookings = BoardroomBooking.query.all()

    result = []

    for b in bookings:
        result.append({
            "id": b.id,
            "customer_name": b.customer_name,
            "date": str(b.date),
            "start_time": b.start_time.strftime("%H:%M"),
            "end_time": b.end_time.strftime("%H:%M"),
            "number_of_people": b.number_of_people,
            "purpose": b.purpose
        })

    return jsonify(result)

from flask import render_template

@boardroom_bp.route("/boardroom")
def boardroom_page():
    return render_template("boardroom.html")