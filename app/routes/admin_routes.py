# Add these routes to your auth_routes.py or a new admin_routes.py

from flask import Blueprint, render_template, request, jsonify, session, redirect
from app.models import User, CustomerSession, StaffAttendance
from app import db
from app.utils.auth import login_required
from functools import wraps
from sqlalchemy import func


# ── Blueprint ─────────────────────────────────────────────────────────────────

admin_bp = Blueprint("admin", __name__)


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 403
            return redirect("/dashboard")
        return view_func(*args, **kwargs)
    return wrapper


# ── Registration page (GET) ───────────────────────────────────────────────────

@admin_bp.route("/register")
def register_page():
    return render_template("register.html")


# ── Register API (POST) ───────────────────────────────────────────────────────
# Used by both the public register page AND the admin "Add User" modal

@admin_bp.route("/api/register", methods=["POST"])
def register_api():

    data = request.get_json()

    full_name = data.get("full_name", "").strip()
    username  = data.get("username", "").strip()
    role      = "staff"
    job_role  = data.get("job_role", "general").strip().lower()
    password  = data.get("password", "")
    valid_job_roles = {"general", "cashier", "cook", "server"}

    if not full_name or not username or not password:
        return jsonify({"error": "All fields are required."}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    if job_role not in valid_job_roles:
        return jsonify({"error": "Invalid job role."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists."}), 409

    new_user = User(
        full_name=full_name,
        username=username,
        role=role,
        job_role=job_role
    )
    new_user.set_password(password)   # uses your existing set_password method

    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "Staff created successfully."}), 201


# ── Admin page (GET) ──────────────────────────────────────────────────────────

@admin_bp.route("/admin")
@login_required
@admin_required
def admin_page():
    return render_template("admin.html")


# ── List all users (GET) ──────────────────────────────────────────────────────

@admin_bp.route("/api/admin/users", methods=["GET"])
@login_required
@admin_required
def get_all_users():

    users = User.query.filter_by(role="staff").order_by(User.created_at.desc()).all()
    online_user_ids = {
        row.user_id for row in StaffAttendance.query.filter(StaffAttendance.time_out.is_(None)).all()
    }

    return jsonify([
        {
            "id":         u.id,
            "name":       u.full_name,
            "username":   u.username,
            "role":       u.role,
            "job_role":   u.job_role if u.job_role else "general",
            "is_online":  u.id in online_user_ids,
            "created_at": str(u.created_at)[:10] if u.created_at else None
        }
        for u in users
    ])


# ── Edit user (PUT) ───────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@login_required
@admin_required
def edit_user(user_id):

    user = User.query.filter_by(id=user_id, role="staff").first()
    if not user:
        return jsonify({"error": "Staff not found."}), 404

    data = request.get_json()

    if "full_name" in data:
        user.full_name = data["full_name"].strip()

    if "username" in data:
        existing = User.query.filter_by(username=data["username"]).first()
        if existing and existing.id != user_id:
            return jsonify({"error": "Username already taken."}), 409
        user.username = data["username"].strip()

    if "job_role" in data:
        valid_job_roles = {"general", "cashier", "cook", "server"}
        jr = data["job_role"].strip().lower()
        if jr in valid_job_roles:
            user.job_role = jr

    # Preserve role; otherwise editing any user would incorrectly downgrade admins to staff.

    if "password" in data and data["password"]:
        user.set_password(data["password"])

    db.session.commit()
    return jsonify({"message": "Staff updated."})


# ── Delete user (DELETE) ──────────────────────────────────────────────────────

@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_user(user_id):

    # Prevent admin from deleting themselves
    if session.get("user_id") == user_id:
        return jsonify({"error": "You cannot delete your own account."}), 400

    user = User.query.filter_by(id=user_id, role="staff").first()
    if not user:
        return jsonify({"error": "Staff not found."}), 404

    # Delete related attendance records first
    from app.models import StaffAttendance
    StaffAttendance.query.filter_by(user_id=user_id).delete()
    
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Staff deleted."})


@admin_bp.route("/api/admin/customer-records", methods=["GET"])
@login_required
@admin_required
def get_customer_records():
    sessions = CustomerSession.query.order_by(CustomerSession.time_in.desc()).all()
    records = []

    for s in sessions:
        ordered_items = []
        for order in s.orders:
            for item in order.items:
                ordered_items.append(f"{item.menu_item.name} x{item.quantity}")

        records.append({
            "id": s.id,
            "name": s.customer_name,
            "orders": ", ".join(ordered_items) if ordered_items else "No orders",
            "room": s.space_type.name if s.space_type else "N/A",
            "time_in": s.time_in.strftime("%Y-%m-%d %I:%M %p") if s.time_in else "N/A",
            "time_out": s.time_out.strftime("%Y-%m-%d %I:%M %p") if s.time_out else "Active"
        })

    return jsonify(records)


@admin_bp.route("/api/admin/staff-attendance", methods=["GET"])
@login_required
@admin_required
def get_staff_attendance():
    logs = StaffAttendance.query.order_by(StaffAttendance.time_in.desc()).all()
    records = []

    for log in logs:
        if log.user and log.user.role == "staff":
            records.append({
                "id": log.id,
                "name": log.user.full_name,
                "time_in": log.time_in.strftime("%Y-%m-%d %I:%M %p") if log.time_in else "N/A",
                "time_out": log.time_out.strftime("%Y-%m-%d %I:%M %p") if log.time_out else "Active"
            })

    return jsonify(records)


# ── Space Capacity ──────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/space-capacity", methods=["GET"])
@login_required
@admin_required
def get_space_capacities():
    from app.models import SpaceType
    spaces = SpaceType.query.all()
    result = []
    for s in spaces:
        occupied_seats = (
            db.session.query(func.coalesce(func.sum(CustomerSession.number_of_people), 0))
            .filter_by(space_type_id=s.id, status="active")
            .scalar()
        ) or 0
        capacity = int(s.capacity) if s.capacity is not None else None
        result.append({
            "id":           s.id,
            "name":         s.name,
            "capacity":     capacity,
            "occupied_seats": int(occupied_seats),
            "seats_left": (max(capacity - int(occupied_seats), 0) if capacity is not None else None)
        })
    return jsonify(result)


@admin_bp.route("/api/admin/space-capacity/<int:space_id>", methods=["PUT"])
@login_required
@admin_required
def set_space_capacity(space_id):
    from app.models import SpaceType
    space = SpaceType.query.get(space_id)
    if not space:
        return jsonify({"error": "Space not found."}), 404
    data = request.get_json()
    cap = data.get("capacity")
    space.capacity = int(cap) if cap not in (None, "", 0) else None
    db.session.commit()
    return jsonify({"message": "Capacity updated.", "capacity": space.capacity})


# ── Staff Analytics ──────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/staff-analytics", methods=["GET"])
@login_required
@admin_required
def staff_analytics():
    from app.models import Order
    from sqlalchemy import func

    rows = (
        db.session.query(
            User.id,
            User.full_name,
            User.job_role,
            func.count(Order.id).label("orders_count"),
            func.count(func.distinct(Order.customer_session_id)).label("customers_count"),
        )
        .outerjoin(Order, Order.handled_by == User.id)
        .filter(User.role == "staff")
        .group_by(User.id, User.full_name, User.job_role)
        .all()
    )
    result = [{
        "id":              r.id,
        "name":            r.full_name,
        "job_role":        r.job_role or "general",
        "orders_count":    int(r.orders_count or 0),
        "customers_count": int(r.customers_count or 0),
    } for r in rows]

    result.sort(key=lambda r: (r["customers_count"], r["orders_count"]), reverse=True)
    return jsonify(result)