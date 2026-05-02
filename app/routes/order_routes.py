from flask import Blueprint, jsonify, request, render_template, session as flask_session
from decimal import Decimal
from datetime import timedelta
from app.utils.auth import login_required

from app import db
from app.models import Order, OrderItem, MenuItem, CustomerSession
from sqlalchemy import func


# Blueprint for order related routes
order_bp = Blueprint("order_routes", __name__)


# ----------------------------------
# GET MENU ITEMS
# ----------------------------------
@order_bp.route("/api/menu")
@login_required
def get_menu():

    items = MenuItem.query.all()

    result = []

    for item in items:
        result.append({
            "id": item.id,
            "name": item.name,
            "price": float(item.price),
            "category": item.category
        })

    return jsonify(result)


# ----------------------------------
# ADD ORDER
# ----------------------------------
@order_bp.route("/api/add-order", methods=["POST"])
@login_required
def add_order():

    data = request.get_json()

    session_id = data.get("session_id")
    items = data.get("items")

    if not session_id or not items:
        return jsonify({"error": "session_id and items are required"}), 400

    session = CustomerSession.query.get(session_id)

    if not session:
        return jsonify({"error": "Session not found"}), 404

    # create order — capture who placed it
    handled_by = flask_session.get("user_id")
    new_order = Order(customer_session_id=session_id, status="preparing", handled_by=handled_by)

    db.session.add(new_order)
    db.session.commit()

    # add items
    for item in items:

        menu_item = MenuItem.query.get(item["menu_item_id"])

        if not menu_item:
            continue

        order_item = OrderItem(
            order_id=new_order.id,
            menu_item_id=menu_item.id,
            quantity=item.get("quantity", 1),
            price=menu_item.price
        )

        db.session.add(order_item)

    db.session.commit()

    return jsonify({
        "message": "Order added successfully",
        "order_id": new_order.id
    })


# ----------------------------------
# UPDATE ORDER STATUS (preparing -> serving)
# ----------------------------------
@order_bp.route("/api/order-status/<int:order_id>", methods=["PUT"])
@login_required
def update_order_status(order_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")

    # Backward compatible: older orders may still store "preparin".
    if new_status not in {"preparin", "preparing", "serving", "done"}:
        return jsonify({"error": "Invalid status"}), 400

    order = Order.query.get(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    sess = CustomerSession.query.get(order.customer_session_id)
    if not sess or sess.status != "active":
        return jsonify({"error": "Cannot update inactive session orders"}), 400

    # Only allow the requested flow:
    # - preparing (or legacy "preparin") -> serving
    # - serving -> done
    if new_status == "serving":
        if order.status not in {"preparin", "preparing"}:
            return jsonify({"error": "Order must be in preparing before serving"}), 400
    elif new_status == "done":
        if order.status != "serving":
            return jsonify({"error": "Order must be in serving before done"}), 400
    else:
        return jsonify({"error": "This action is not supported"}), 400

    order.status = new_status
    db.session.commit()

    return jsonify({"message": "Order status updated", "order_id": order_id, "status": order.status})


# ----------------------------------
# GET SESSION ORDERS
# ----------------------------------
@order_bp.route("/api/session-orders/<int:session_id>")
@login_required
def get_session_orders(session_id):
    # By default, hide completed orders ("done") from the customer orders page.
    # The dashboard receipt needs them, so it can call with `?include_done=1`.
    include_done = request.args.get("include_done", "0").lower() in {"1", "true", "yes"}

    session = CustomerSession.query.get(session_id)
    if not session or session.status != "active":
        return jsonify({
            "session_id": session_id,
            "customer_name": session.customer_name if session else None,
            "space_type": session.space_type.name if session and session.space_type else None,
            "time_in": (session.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p") if session and session.time_in else None,
            "orders": [],
            "food_total": 0.0
        })

    orders_query = Order.query.filter_by(customer_session_id=session_id)
    if not include_done:
        orders_query = orders_query.filter(Order.status != "done")
    orders = orders_query.all()

    order_list = []
    food_total = Decimal("0.00")

    for order in orders:

        for item in order.items:

            total_price = item.quantity * item.price
            food_total += total_price

            order_list.append({
                "id": item.id,
                "order_id": order.id,
                "order_status": order.status,
                "item_status": item.status if item.status else "preparing",
                "handled_by_name": order.handler.full_name if order.handler else "N/A",
                "item_name": item.menu_item.name,
                "quantity": item.quantity,
                "price": float(item.price),
                "total": float(total_price)
            })

    return jsonify({
        "session_id": session_id,
        "customer_name": session.customer_name if session else None,
        "space_type": session.space_type.name if session and session.space_type else None,
        "time_in": (session.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p") if session and session.time_in else None,
        "orders": order_list,
        "food_total": float(food_total)
    })


@order_bp.route("/order/<int:session_id>")
@login_required
def order_page(session_id):
    return render_template("order.html", session_id=session_id)


# ----------------------------------
# ORDERS (VIEW ONLY)
# ----------------------------------
@order_bp.route("/orders")
@login_required
def orders_list_page():
    return render_template("orders_list.html")


@order_bp.route("/api/orders-list")
@login_required
def orders_list_api():
    sessions = CustomerSession.query.filter_by(status="active").order_by(CustomerSession.time_in.desc()).all()
    result = []

    for sess in sessions:
        # Hide completed orders.
        orders = Order.query.filter_by(customer_session_id=sess.id).filter(Order.status != "done").all()
        if not orders:
            continue

        item_count = 0
        food_total = Decimal("0.00")

        for order in orders:
            for item in order.items:
                food_total += item.quantity * item.price
                item_count += 1

        latest_order = (
            Order.query
            .filter_by(customer_session_id=sess.id)
            .filter(Order.status != "done")
            .order_by(Order.id.desc())
            .first()
        )
        latest_status = latest_order.status if latest_order else "preparing"
        if latest_status == "preparin":
            latest_status = "preparing"

        time_in_text = (sess.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p") if sess.time_in else "N/A"

        result.append({
            "session_id": sess.id,
            "customer_name": sess.customer_name,
            "space_type": sess.space_type.name if sess.space_type else "N/A",
            "time_in": time_in_text,
            "orders_count": item_count,
            "food_total": float(food_total),
            "active_order_status": latest_status
        })

    return jsonify(result)


@order_bp.route("/api/orders/pending-count")
@login_required
def orders_pending_count():
    """
    Used by the navbar badge to indicate there are active (non-done) orders.
    We count distinct active sessions with at least one order item that isn't done.
    """
    pending_sessions = (
        db.session.query(func.count(func.distinct(Order.customer_session_id)))
        .join(CustomerSession, CustomerSession.id == Order.customer_session_id)
        .filter(CustomerSession.status == "active")
        .filter(Order.status != "done")
        .scalar()
    ) or 0

    pending_items = (
        db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0))
        .select_from(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .join(CustomerSession, CustomerSession.id == Order.customer_session_id)
        .filter(CustomerSession.status == "active")
        .filter(Order.status != "done")
        .scalar()
    ) or 0

    return jsonify({
        "pending_sessions": int(pending_sessions),
        "pending_items": int(pending_items)
    })


@order_bp.route("/orders/<int:session_id>")
@login_required
def orders_view_page(session_id):
    return render_template("orders_view.html", session_id=session_id)


@order_bp.route("/api/void-item/<int:item_id>", methods=["DELETE"])
@login_required
def void_item(item_id):

    item = OrderItem.query.get(item_id)

    if not item:
        return jsonify({"error": "Item not found"}), 404

    if item.quantity > 1:
        item.quantity -= 1
    else:
        db.session.delete(item)
    db.session.commit()

    return jsonify({"message": "One item voided successfully"})


# ----------------------------------
# TOGGLE ORDER ITEM STATUS (preparing <-> done)
# ----------------------------------
@order_bp.route("/api/order-item-status/<int:item_id>", methods=["PUT"])
@login_required
def toggle_order_item_status(item_id):
    item = OrderItem.query.get(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    # Toggle between preparing and done
    if item.status in {"preparing", "preparin", None}:
        item.status = "done"
    else:
        item.status = "preparing"

    db.session.commit()
    return jsonify({"message": "Item status updated", "item_id": item_id, "status": item.status})


# ----------------------------------
# MARK ALL SESSION ORDERS AS SERVED
# ----------------------------------
@order_bp.route("/api/session-served/<int:session_id>", methods=["POST"])
@login_required
def session_served(session_id):
    sess = CustomerSession.query.get(session_id)
    if not sess:
        return jsonify({"error": "Session not found"}), 404

    if sess.status != "active":
        return jsonify({"error": "Session is not active"}), 400

    orders = Order.query.filter_by(customer_session_id=session_id).filter(Order.status != "done").all()
    for order in orders:
        order.status = "done"
        for item in order.items:
            item.status = "done"

    db.session.commit()
    return jsonify({"message": "Session marked as served", "session_id": session_id})

