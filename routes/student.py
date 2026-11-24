"""
student.py - Everything a student can do in the app.

Pages (they return HTML):
  /menu               Menu, search, categories, cart
  /orders             The student's order list
  /orders/<id>        One order: live tracker + QR/OTP pickup card

JSON API (called by the JavaScript with fetch()):
  GET  /api/menu                  all dishes with live stock
  GET  /api/slots                 today's pickup slots and how full they are
  POST /api/orders                place an order
  GET  /api/orders/<id>           the order's current status (polled every ~15 s)
  POST /api/orders/<id>/cancel    cancel an order

Every route is for students only. A student can only ever see their own orders.
"""

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request

from config import Config
from db import fetch_all
from menu_images import resolve_image_url
from routes.access import role_required
from routes.order_logic import (
    OrderError,
    build_order_payload,
    cancel_order,
    format_order_time,
    get_pickup_slots_for_today,
    place_order,
)

student_bp = Blueprint("student", __name__)


# =========================================================
# Small helpers
# =========================================================

def sort_categories(category_names):
    # Use the order from config.py; any new category the manager adds goes at the end
    preferred = Config.MENU_CATEGORY_ORDER
    return sorted(
        category_names,
        key=lambda name: (preferred.index(name) if name in preferred else len(preferred), name),
    )


def load_average_ratings():
    # Average 1-tap rating of every order that contained each dish
    rows = fetch_all(
        """
        SELECT oi.menu_item_id, ROUND(AVG(f.rating), 1) AS average_rating, COUNT(f.id) AS rating_count
        FROM order_items oi
        JOIN feedback f ON f.order_id = oi.order_id
        GROUP BY oi.menu_item_id
        """
    )
    return {row["menu_item_id"]: row for row in rows}


def build_menu_item(row, ratings):
    # Turn a database row into the plain dictionary the browser needs
    is_available = (not row["is_sold_out"]) and row["stock_qty"] > 0
    rating = ratings.get(row["id"])

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "price": float(row["price"]),
        "food_type": row["food_type"],
        "allergens": [name.strip() for name in row["allergens"].split(",") if name.strip()],
        "prep_time_minutes": row["prep_time_minutes"],
        "image_url": resolve_image_url(row["name"], row["image_url"]),
        "stock_qty": row["stock_qty"],
        "is_featured": bool(row["is_featured"]),
        "available": is_available,
        # Low-stock badge appears only at 5 or fewer left (limit lives in config.py)
        "low_stock": is_available and row["stock_qty"] <= Config.LOW_STOCK_LIMIT,
        "average_rating": float(rating["average_rating"]) if rating else None,
        "rating_count": rating["rating_count"] if rating else 0,
    }


def json_error(message, status_code, **extra_fields):
    response = {"error": message}
    response.update(extra_fields)
    return jsonify(response), status_code


# =========================================================
# Pages
# =========================================================

@student_bp.route("/menu")
@role_required("student")
def menu():
    return render_template("student/menu.html")


@student_bp.route("/orders")
@role_required("student")
def orders():
    order_rows = fetch_all(
        """
        SELECT o.id, o.status, o.total_amount, o.created_at, s.slot_date, s.start_time,
               GROUP_CONCAT(CONCAT(oi.quantity, ' x ', m.name) ORDER BY m.name SEPARATOR ', ') AS items_summary
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN order_items oi ON oi.order_id = o.id
        JOIN menu_items m ON m.id = oi.menu_item_id
        WHERE o.student_id = %s
        GROUP BY o.id, o.status, o.total_amount, o.created_at, s.slot_date, s.start_time
        ORDER BY o.created_at DESC
        LIMIT 40
        """,
        (g.user["id"],),
    )

    for row in order_rows:
        row["pickup_label"] = format_order_time(row["slot_date"], row["start_time"])

    # Orders that are still in progress are shown first, in their own section
    active_orders = [row for row in order_rows if row["status"] in ("confirmed", "preparing", "ready")]
    past_orders = [row for row in order_rows if row["status"] not in ("confirmed", "preparing", "ready")]

    return render_template("student/orders.html", active_orders=active_orders, past_orders=past_orders)


@student_bp.route("/orders/<int:order_id>")
@role_required("student")
def order_detail(order_id):
    # The page itself is mostly empty: order.js fills it from /api/orders/<id>.
    # We only check here that the order really belongs to this student.
    if build_order_payload(order_id, g.user["id"]) is None:
        abort(404)

    return render_template("student/order.html", order_id=order_id)


# =========================================================
# JSON API
# =========================================================

@student_bp.route("/api/menu")
@role_required("student")
def api_menu():
    rows = fetch_all(
        """
        SELECT id, name, description, category, price, food_type, allergens,
               prep_time_minutes, image_url, stock_qty, is_sold_out, is_featured
        FROM menu_items
        WHERE is_active = 1
        ORDER BY name
        """
    )
    ratings = load_average_ratings()
    items = [build_menu_item(row, ratings) for row in rows]

    return jsonify({
        "items": items,
        "categories": sort_categories({item["category"] for item in items}),
        "dietary_preference": g.user["dietary_preference"],
        "max_qty_per_item": Config.MAX_QTY_PER_ITEM,
    })


@student_bp.route("/api/slots")
@role_required("student")
def api_slots():
    return jsonify(get_pickup_slots_for_today())


@student_bp.route("/api/orders", methods=["POST"])
@role_required("student")
def api_place_order():
    data = request.get_json(silent=True) or {}

    try:
        order_id = place_order(
            student_id=g.user["id"],
            raw_lines=data.get("items"),
            slot_id=data.get("slot_id"),
            payment_method=data.get("payment_method"),
        )
    except OrderError as error:
        if error.slot_problem:
            # Auto-suggest the next open slot when the chosen one is full or gone
            suggestion = get_pickup_slots_for_today()["next_open_slot_id"]
            return json_error(error.message, 409, suggested_slot_id=suggestion)
        return json_error(error.message, 400)
    except Exception:
        current_app.logger.exception("Placing an order failed")
        return json_error("We could not place your order. Please try again.", 500)

    return jsonify({"order_id": order_id, "order_url": f"/orders/{order_id}"}), 201


@student_bp.route("/api/orders/<int:order_id>")
@role_required("student")
def api_order_status(order_id):
    payload = build_order_payload(order_id, g.user["id"])

    if payload is None:
        return json_error("We could not find that order.", 404)

    return jsonify(payload)


@student_bp.route("/api/orders/<int:order_id>/cancel", methods=["POST"])
@role_required("student")
def api_cancel_order(order_id):
    try:
        cancel_order(order_id, g.user["id"])
    except OrderError as error:
        return json_error(error.message, 400)
    except Exception:
        current_app.logger.exception("Cancelling an order failed")
        return json_error("We could not cancel your order. Please try again.", 500)

    return jsonify(build_order_payload(order_id, g.user["id"]))
