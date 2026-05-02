from flask import Blueprint, request, jsonify, render_template
from datetime import datetime, timedelta
from app import db
from app.models import BoardroomBooking, CustomerSession, SpaceType
from app.utils.auth import login_required

lounge_bp = Blueprint("lounge_routes", __name__)


# ----------------------------------
# LOUNGE BOOKING PAGE
# ----------------------------------
@lounge_bp.route("/lounge-booking")
@login_required
def lounge_booking_page():
    return render_template("lounge_booking.html")


def _boardroom_space():
    return SpaceType.query.filter_by(name="Boardroom").first()


def _serialize_booking(booking):
    now = datetime.utcnow()
    start_text = booking.start_time.strftime("%H:%M")
    end_text = booking.end_time.strftime("%H:%M")
    started_now = booking.status == "active"
    can_start = booking.status == "booked" and str(booking.date) == now.date().isoformat()
    overdue = bool(booking.expected_end_at and booking.status == "active" and now >= booking.expected_end_at)
    return {
        "id": booking.id,
        "customer_name": booking.customer_name,
        "date": str(booking.date),
        "start_time": start_text,
        "end_time": end_text,
        "number_of_people": booking.number_of_people,
        "course": booking.course or "N/A",
        "purpose": booking.purpose or "N/A",
        "status": booking.status,
        "session_id": booking.session_id,
        "started_at": booking.started_at.isoformat() if booking.started_at else None,
        "expected_end_at": booking.expected_end_at.isoformat() if booking.expected_end_at else None,
        "extended_minutes": booking.extended_minutes or 0,
        "can_start": can_start,
        "is_active": started_now,
        "is_overdue": overdue,
    }


# ----------------------------------
# CREATE BOOKING
# ----------------------------------
@lounge_bp.route("/api/book-lounge", methods=["POST"])
@login_required
def book_lounge():
    data = request.get_json()

    customer_name    = data.get("customer_name")
    date_str         = data.get("date")
    start_time_str   = data.get("start_time")
    end_time_str     = data.get("end_time")
    number_of_people = data.get("number_of_people")
    course           = data.get("course")
    purpose          = data.get("purpose")

    if not all([customer_name, date_str, start_time_str, end_time_str, number_of_people]):
        return jsonify({"error": "Missing required fields"}), 400

    date       = datetime.strptime(date_str, "%Y-%m-%d").date()
    start_time = datetime.strptime(start_time_str, "%H:%M").time()
    end_time   = datetime.strptime(end_time_str, "%H:%M").time()

    if end_time <= start_time:
        return jsonify({"error": "End time must be after start time"}), 400

    # Conflict check against still-active or booked boardroom reservations.
    existing = BoardroomBooking.query.filter(
        BoardroomBooking.date == date,
        BoardroomBooking.status.in_(["booked", "active"])
    ).all()
    for b in existing:
        if start_time < b.end_time and end_time > b.start_time:
            return jsonify({"error": f"Slot conflicts with existing booking ({b.start_time.strftime('%H:%M')}–{b.end_time.strftime('%H:%M')})"}), 400

    new_booking = BoardroomBooking(
        customer_name=customer_name,
        date=date,
        start_time=start_time,
        end_time=end_time,
        number_of_people=int(number_of_people),
        course=(course or "").strip() or None,
        purpose=purpose,
        status="booked",
        expected_end_at=datetime.combine(date, end_time)
    )
    db.session.add(new_booking)
    db.session.commit()
    return jsonify({"message": "Boardroom booked successfully"})


# ----------------------------------
# GET BOOKINGS (optionally by date)
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings")
@login_required
def get_lounge_bookings():
    date_str = request.args.get("date", "").strip()
    status_filter = request.args.get("status", "").strip().lower()
    query = BoardroomBooking.query

    if status_filter == "active":
        query = query.filter_by(status="active")
    elif status_filter == "booked":
        query = query.filter_by(status="booked")
    elif status_filter == "open":
        query = query.filter(BoardroomBooking.status.in_(["booked", "active"]))

    if date_str:
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            query = query.filter_by(date=date)
        except ValueError:
            pass

    bookings = query.order_by(BoardroomBooking.date, BoardroomBooking.start_time).all()
    return jsonify([_serialize_booking(b) for b in bookings])


# ----------------------------------
# CANCEL BOOKING
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/<int:booking_id>", methods=["DELETE"])
@login_required
def cancel_lounge_booking(booking_id):
    b = BoardroomBooking.query.get(booking_id)
    if not b:
        return jsonify({"error": "Booking not found"}), 404
    if b.status == "active":
        return jsonify({"error": "Active session cannot be cancelled. Checkout first."}), 400
    b.status = "cancelled"
    db.session.commit()
    return jsonify({"message": "Booking cancelled"})


# ----------------------------------
# START BOARDROOM SESSION FROM BOOKING
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/<int:booking_id>/start", methods=["POST"])
@login_required
def start_booking_session(booking_id):
    booking = BoardroomBooking.query.get(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    if booking.status != "booked":
        return jsonify({"error": "Only booked reservations can be started."}), 400

    boardroom = _boardroom_space()
    if not boardroom:
        return jsonify({"error": "Boardroom space is missing. Please seed spaces first."}), 500

    active_in_boardroom = CustomerSession.query.filter_by(
        space_type_id=boardroom.id,
        status="active"
    ).all()
    occupied = sum(s.number_of_people or 1 for s in active_in_boardroom)
    requested = booking.number_of_people or 1
    if boardroom.capacity and (occupied + requested) > boardroom.capacity:
        seats_left = max(int(boardroom.capacity) - int(occupied), 0)
        return jsonify({"error": f"Boardroom has only {seats_left} seat(s) left."}), 409

    now = datetime.utcnow()
    customer_session = CustomerSession(
        customer_name=booking.customer_name,
        school="Boardroom Booking",
        course=booking.course or "N/A",
        number_of_people=booking.number_of_people or 1,
        space_type_id=boardroom.id,
        time_in=now,
        status="active"
    )

    booking.status = "active"
    booking.started_at = now
    booking.expected_end_at = datetime.combine(booking.date, booking.end_time)

    db.session.add(customer_session)
    db.session.flush()
    booking.session_id = customer_session.id
    db.session.commit()

    return jsonify({
        "message": "Boardroom session started.",
        "session_id": customer_session.id
    })


# ----------------------------------
# EXTEND ACTIVE BOOKING
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/<int:booking_id>/extend", methods=["POST"])
@login_required
def extend_booking(booking_id):
    booking = BoardroomBooking.query.get(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    if booking.status != "active":
        return jsonify({"error": "Only active bookings can be extended."}), 400

    data = request.get_json(silent=True) or {}
    minutes = int(data.get("minutes", 0))
    if minutes <= 0:
        return jsonify({"error": "Extension minutes must be greater than 0."}), 400

    current_end = booking.expected_end_at or datetime.combine(booking.date, booking.end_time)
    new_end = current_end + timedelta(minutes=minutes)

    booking.expected_end_at = new_end
    booking.end_time = new_end.time()
    booking.extended_minutes = (booking.extended_minutes or 0) + minutes
    db.session.commit()

    return jsonify({
        "message": "Booking extended.",
        "end_time": booking.end_time.strftime("%H:%M"),
        "expected_end_at": booking.expected_end_at.isoformat(),
        "extended_minutes": booking.extended_minutes
    })


# ----------------------------------
# OVERDUE ALERTS (GLOBAL POLL)
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/overdue-alerts")
@login_required
def overdue_alerts():
    now = datetime.utcnow()
    active = BoardroomBooking.query.filter_by(status="active").all()
    overdue = [b for b in active if b.expected_end_at and now >= b.expected_end_at]

    return jsonify([{
        "booking_id": b.id,
        "customer_name": b.customer_name,
        "expected_end_at": b.expected_end_at.isoformat() if b.expected_end_at else None,
        "session_id": b.session_id
    } for b in overdue])
