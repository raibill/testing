from flask import Blueprint, jsonify, request, session
from datetime import datetime, timedelta
from decimal import Decimal
from app.utils.auth import login_required

from app.models import Transaction


# Blueprint for sales routes
sales_bp = Blueprint("sales_routes", __name__)


def admin_only_json():
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403
    return None


# ----------------------------------
# DAILY SALES SUMMARY
# ----------------------------------
@sales_bp.route("/api/daily-sales")
@login_required
def daily_sales():
    guard = admin_only_json()
    if guard:
        return guard

    today = datetime.utcnow().date()

    transactions = Transaction.query.all()

    total_revenue = Decimal("0.00")
    total_food = Decimal("0.00")
    total_space = Decimal("0.00")

    transaction_count = 0

    for t in transactions:

        if t.created_at.date() == today:

            total_revenue += t.total_bill
            total_food += t.food_bill
            total_space += t.time_bill
            transaction_count += 1

    return jsonify({
        "date": str(today),
        "transactions": transaction_count,
        "total_revenue": float(total_revenue),
        "space_revenue": float(total_space),
        "food_revenue": float(total_food)
    })


def summarize_sales(start_date, end_date):
    transactions = Transaction.query.all()
    total_revenue = Decimal("0.00")
    total_food = Decimal("0.00")
    total_space = Decimal("0.00")
    transaction_count = 0

    for t in transactions:
        tx_date = t.created_at.date()
        if start_date <= tx_date <= end_date:
            total_revenue += t.total_bill
            total_food += t.food_bill
            total_space += t.time_bill
            transaction_count += 1

    return {
        "transactions": transaction_count,
        "total_revenue": float(total_revenue),
        "space_revenue": float(total_space),
        "food_revenue": float(total_food)
    }


@sales_bp.route("/api/sales-summary")
@login_required
def sales_summary():
    guard = admin_only_json()
    if guard:
        return guard

    period = request.args.get("period", "today")
    today = datetime.utcnow().date()

    if period == "yesterday":
        start_date = today - timedelta(days=1)
        end_date = start_date
    elif period == "7days":
        start_date = today - timedelta(days=6)
        end_date = today
    elif period == "1month":
        start_date = today - timedelta(days=29)
        end_date = today
    else:
        start_date = today
        end_date = today

    return jsonify({
        "period": period,
        "start_date": str(start_date),
        "end_date": str(end_date),
        **summarize_sales(start_date, end_date)
    })


@sales_bp.route("/api/sales-compare")
@login_required
def sales_compare():
    guard = admin_only_json()
    if guard:
        return guard

    today = datetime.utcnow().date()

    today_summary = summarize_sales(today, today)
    yesterday = today - timedelta(days=1)
    yesterday_summary = summarize_sales(yesterday, yesterday)
    week_summary = summarize_sales(today - timedelta(days=6), today)
    month_summary = summarize_sales(today - timedelta(days=29), today)

    return jsonify({
        "today": today_summary,
        "yesterday": yesterday_summary,
        "last_7_days": week_summary,
        "last_30_days": month_summary
    })