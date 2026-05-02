from functools import wraps
from flask import session, redirect, jsonify, flash, request

def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            # For API endpoints, return JSON
            # For normal pages, redirect to the login page.
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401

            flash("Please log in first!", "danger")
            return redirect("/login")

        return view_func(*args, **kwargs)

    return wrapper

