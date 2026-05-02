from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func
from app.utils.auth import login_required

from app import db, socketio
from app.models import CustomerSession, SpaceType, Order, Transaction, BoardroomBooking


# Blueprint groups related routes together
session_bp = Blueprint("session_routes", __name__)


# -----------------------------
# CHECK-IN CUSTOMER
# -----------------------------
@session_bp.route("/api/checkin", methods=["POST"])
#@login_required
def checkin():

    data = request.get_json()

    customer_name = data.get("customer_name")
    school = data.get("school")
    course = data.get("course")
    space_type_id = data.get("space_type_id")
    number_of_people = int(data.get("number_of_people", 1) or 1)
    if number_of_people <= 0:
        return jsonify({"error": "Number of people must be at least 1."}), 400

    new_session = CustomerSession(
    customer_name=customer_name,
    school=school,
    course=course,
    number_of_people=number_of_people,
    space_type_id=space_type_id,
    time_in=datetime.utcnow(),
    status="active"
)

    # Capacity check: only applies when a limit is set
    if space_type_id:
        space = SpaceType.query.get(space_type_id)
        if space and space.capacity:
            occupied = (
                db.session.query(func.coalesce(func.sum(CustomerSession.number_of_people), 0))
                .filter_by(space_type_id=space_type_id, status="active")
                .scalar()
            ) or 0
            if occupied + number_of_people > space.capacity:
                seats_left = max(space.capacity - int(occupied), 0)
                return jsonify({
                    "error": (
                        f"{space.name} has only {seats_left} seat(s) left. "
                        f"Requested seats: {number_of_people}."
                    ),
                    "full": True
                }), 409

    db.session.add(new_session)
    db.session.commit()

    return jsonify({
        "message": "Customer checked in successfully",
        "session_id": new_session.id
    })


# -----------------------------
# GET ACTIVE SESSIONS
# (LIVE RUNNING BILL)
# -----------------------------
@session_bp.route("/api/active-sessions")
@login_required
def get_active_sessions():

    sessions = CustomerSession.query.filter_by(status="active").all()
    session_ids = [s.id for s in sessions]
    boardroom_by_session = {}
    if session_ids:
        boardroom_rows = BoardroomBooking.query.filter(
            BoardroomBooking.session_id.in_(session_ids),
            BoardroomBooking.status == "active"
        ).all()
        boardroom_by_session = {b.session_id: b for b in boardroom_rows}

    result = []

    for session in sessions:

        now = datetime.utcnow()

        time_difference = now - session.time_in
        minutes_used = time_difference.total_seconds() / 60

        rate = session.space_type.rate_per_minute

        current_bill = (Decimal(str(minutes_used)) * rate).quantize(Decimal("0.01"))
        linked_boardroom = boardroom_by_session.get(session.id)
        purpose = linked_boardroom.purpose if linked_boardroom and session.space_type.name == "Boardroom" else None

        result.append({
        "session_id": session.id,
        "customer_name": session.customer_name,
        "school": session.school,
        "course": session.course,
        "number_of_people": session.number_of_people,
        "purpose": purpose,
        "space_type": session.space_type.name,
        "time_in": (session.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p"),
        "seconds_used": int(time_difference.total_seconds()),
        "current_bill": float(current_bill)
    })

    return jsonify(result)


# -----------------------------
# CHECKOUT CUSTOMER
# -----------------------------
@session_bp.route("/api/checkout/<int:session_id>", methods=["POST"])
@login_required
def checkout(session_id):

    session = CustomerSession.query.get(session_id)

    if not session:
        return jsonify({"error": "Session not found"}), 404

    if session.status == "completed":
        return jsonify({"error": "Session already checked out"}), 400

    # record time out
    # Store timestamps in UTC; UI adds +8 hours only when formatting.
    session.time_out = datetime.utcnow()

    # calculate total minutes
    time_difference = session.time_out - session.time_in
    total_minutes = time_difference.total_seconds() / 60

    rate_per_minute = session.space_type.rate_per_minute

    # calculate time bill
    time_bill = (Decimal(str(total_minutes)) * rate_per_minute).quantize(Decimal("0.01"))

    # calculate food bill
    food_total = Decimal("0.00")

    orders = Order.query.filter_by(customer_session_id=session_id).all()

    for order in orders:
        for item in order.items:
            food_total += item.quantity * item.price

    # calculate total bill
    total_bill = (time_bill + food_total).quantize(Decimal("0.01"))

    # create transaction record
    new_transaction = Transaction(
        session_id=session.id,
        time_bill=time_bill,
        food_bill=food_total,
        total_bill=total_bill
    )

    db.session.add(new_transaction)

    # mark session completed
    session.status = "completed"

    # If this active session came from a boardroom booking, close the booking too.
    linked_booking = BoardroomBooking.query.filter_by(session_id=session.id, status="active").first()
    if linked_booking:
        linked_booking.status = "completed"
        linked_booking.ended_at = session.time_out

    db.session.commit()

    socketio.emit("session_checked_out", {
        "session_id": session.id,
        "customer_name": session.customer_name,
        "space_type": session.space_type.name,
        "total_bill": float(total_bill)
    })

    return jsonify({
        "customer_name": session.customer_name,
        "minutes_used": round(total_minutes, 2),
        "rate_per_minute": float(rate_per_minute),
        "time_bill": float(time_bill),
        "food_bill": float(food_total),
        "total_bill": float(total_bill),
        "status": session.status
    })

@session_bp.route("/api/preview-checkout/<int:session_id>")
def preview_checkout(session_id):

    session = CustomerSession.query.get(session_id)

    if not session:
        return jsonify({"error": "Session not found"}), 404

    # calculate current time
    now = datetime.utcnow()
    time_difference = now - session.time_in
    total_minutes = time_difference.total_seconds() / 60

    rate_per_minute = session.space_type.rate_per_minute

    # calculate time bill
    time_bill = (Decimal(str(total_minutes)) * rate_per_minute).quantize(Decimal("0.01"))

    # calculate food bill
    food_total = Decimal("0.00")

    orders = Order.query.filter_by(customer_session_id=session_id).all()

    for order in orders:
        for item in order.items:
            food_total += item.quantity * item.price

    total_bill = (time_bill + food_total).quantize(Decimal("0.01"))

    return jsonify({
        "customer_name": session.customer_name,
        "minutes_used": total_minutes,
        "time_bill": float(time_bill),
        "food_bill": float(food_total),
        "total_bill": float(total_bill)
    })


@session_bp.route("/api/checkout-records")
@login_required
def checkout_records():

    transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()

    # Optional date-range filter (YYYY-MM-DD strings from the frontend)
    date_from_str = request.args.get("date_from", "").strip()
    date_to_str   = request.args.get("date_to",   "").strip()

    date_from = None
    date_to   = None
    try:
        if date_from_str:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        if date_to_str:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
    except ValueError:
        pass  # Ignore bad dates — return unfiltered

    result = []

    for tx in transactions:
        sess = tx.session

        # Apply date filter on created_at (UTC date is fine for grouping purposes)
        if date_from and tx.created_at.date() < date_from:
            continue
        if date_to and tx.created_at.date() > date_to:
            continue

        time_in_text = (sess.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p") if sess and sess.time_in else "N/A"
        time_out_text = (sess.time_out + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p") if sess and sess.time_out else "N/A"

        seconds_spent = int((sess.time_out - sess.time_in).total_seconds()) if sess and sess.time_in and sess.time_out else None
        minutes_spent = round(seconds_spent / 60, 2) if seconds_spent is not None else None

        result.append({
            "transaction_id": tx.id,
            "customer_name": sess.customer_name if sess else "N/A",
            "space_type": sess.space_type.name if sess and sess.space_type else "N/A",
            "time_in": time_in_text,
            "time_out": time_out_text,
            "time_bill": float(tx.time_bill),
            "food_bill": float(tx.food_bill),
            "total_bill": float(tx.total_bill),
            "seconds_spent": seconds_spent,
            "minutes_spent": minutes_spent,
            "created_date": tx.created_at.strftime("%Y-%m-%d")
        })

    return jsonify(result)


@session_bp.route("/api/space-availability")
@login_required
def space_availability():
    spaces = SpaceType.query.filter(SpaceType.name.in_(["Regular Lounge", "Premium Lounge"])).all()
    result = []
    for space in spaces:
        occupied = (
            db.session.query(func.coalesce(func.sum(CustomerSession.number_of_people), 0))
            .filter_by(space_type_id=space.id, status="active")
            .scalar()
        ) or 0
        cap = space.capacity if space.capacity is not None else 0
        left = max(int(cap) - int(occupied), 0) if cap else None
        result.append({
            "space_id": space.id,
            "space_name": space.name,
            "capacity": int(cap) if cap else 0,
            "occupied": int(occupied),
            "seats_left": left
        })
    return jsonify(result)