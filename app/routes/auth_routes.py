from flask import Blueprint, render_template, request, jsonify, session, redirect
from app.models import User, StaffAttendance
from app import db
from datetime import datetime

bp = Blueprint("auth", __name__)


def get_redirect_by_role(role):
    if role == "admin":
        return "/admin"
    return "/dashboard"


@bp.route("/login")
def login_page():

    if "user_id" in session:
        return redirect(get_redirect_by_role(session.get("role")))

    return render_template("login.html")


@bp.route("/api/login", methods=["POST"])
def login_api():

    data = request.get_json()

    user = User.query.filter_by(username=data["username"]).first()

    if user and user.check_password(data["password"]):

        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role

        attendance = StaffAttendance(user_id=user.id, time_in=datetime.utcnow())
        db.session.add(attendance)
        db.session.commit()
        session["attendance_id"] = attendance.id

        return jsonify({
            "message": "Login successful",
            "redirect": get_redirect_by_role(user.role)
        })

    return jsonify({"error": "Invalid credentials"}), 401


@bp.route("/logout")
def logout():
    attendance_id = session.get("attendance_id")
    if attendance_id:
        attendance = StaffAttendance.query.get(attendance_id)
        if attendance and attendance.time_out is None:
            attendance.time_out = datetime.utcnow()
            db.session.commit()
    session.clear()
    return redirect("/login")