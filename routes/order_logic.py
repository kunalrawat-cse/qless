"""
order_logic.py - The business rules for pickup slots and orders.

Routes (student.py) stay short because the real work happens here:

    get_pickup_slots_for_today()   -> today's 15-minute slots with how full each one is
    place_order(...)               -> checks everything, saves the order, reduces stock
    cancel_order(...)              -> cancels an order and puts the stock back
    build_order_payload(...)       -> everything the order tracker page needs

Placing and cancelling use ONE database transaction each. Either every
change is saved, or none of them are. "SELECT ... FOR UPDATE" locks the rows
we are about to change, so two students can never grab the last portion
or the last place in a slot at the same moment.
"""

import secrets
from datetime import datetime, time, timedelta

from config import Config
from db import fetch_all, fetch_one, get_connection


class OrderError(Exception):
    """A problem we can safely explain to the student (full slot, out of stock...)."""

    def __init__(self, message, slot_problem=False):
        super().__init__(message)
        self.message = message
        # True when the slot is the problem, so the page can suggest another slot
        self.slot_problem = slot_problem


# =========================================================
# Small time helpers
# =========================================================

def to_time(value):
    # MySQL TIME columns arrive from PyMySQL as a timedelta, so convert to a real time
    if isinstance(value, timedelta):
        total_minutes = int(value.total_seconds()) // 60
        return time(total_minutes // 60, total_minutes % 60)
    return value


def format_clock(value):
    # 13:05 -> "1:05 PM"
    return to_time(value).strftime("%I:%M %p").lstrip("0")


def build_slot_start(slot_date, start_time):
    # Combine a date and a TIME column into one datetime we can compare with now()
    return datetime.combine(slot_date, to_time(start_time))


def format_order_time(slot_date, start_time):
    # "Today, 12:30 PM" or "18 Nov, 12:30 PM"
    clock = format_clock(start_time)
    if slot_date == datetime.now().date():
        return f"Today, {clock}"
    return f"{slot_date.day} {slot_date.strftime('%b')}, {clock}"


# =========================================================
# Pickup slots
# =========================================================

def create_slots_if_missing(day):
    # The canteen opens a new day with no slots yet, so we build them on first use
    existing = fetch_one("SELECT COUNT(*) AS total FROM pickup_slots WHERE slot_date = %s", (day,))
    if existing["total"] > 0:
        return

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            midnight = datetime.combine(day, time.min)
            current = midnight + timedelta(hours=Config.CANTEEN_OPEN_HOUR)
            closing = midnight + timedelta(hours=Config.CANTEEN_CLOSE_HOUR)

            while current < closing:
                slot_end = current + timedelta(minutes=Config.SLOT_LENGTH_MINUTES)
                # INSERT IGNORE: if two students arrive together, the second insert is skipped
                cursor.execute(
                    """
                    INSERT IGNORE INTO pickup_slots (slot_date, start_time, end_time, capacity)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (day, current.time(), slot_end.time(), Config.DEFAULT_SLOT_CAPACITY),
                )
                current = slot_end
        connection.commit()
    finally:
        connection.close()


def calculate_slot_load(booked, capacity):
    # Returns the percentage of a slot that is already booked (0 to 100)
    if capacity <= 0:
        return 100
    return min(100, round(booked * 100 / capacity))


def get_pickup_slots_for_today():
    """Today's bookable slots, each with how full it is."""
    now = datetime.now()
    today = now.date()
    earliest_start = now + timedelta(minutes=Config.SLOT_LEAD_MINUTES)

    # Too close to midnight: nothing left to book today
    if earliest_start.date() != today:
        return {"slots": [], "next_open_slot_id": None}

    create_slots_if_missing(today)

    rows = fetch_all(
        """
        SELECT s.id, s.start_time, s.end_time, s.capacity, COUNT(o.id) AS booked
        FROM pickup_slots s
        LEFT JOIN orders o ON o.slot_id = s.id AND o.status <> 'cancelled'
        WHERE s.slot_date = %s AND s.start_time >= %s
        GROUP BY s.id, s.start_time, s.end_time, s.capacity
        ORDER BY s.start_time
        """,
        (today, earliest_start.strftime("%H:%M:%S")),
    )

    slots = []
    next_open_slot_id = None

    for row in rows:
        load_percent = calculate_slot_load(row["booked"], row["capacity"])
        is_full = row["booked"] >= row["capacity"]

        slots.append({
            "id": row["id"],
            "start_label": format_clock(row["start_time"]),
            "end_label": format_clock(row["end_time"]),
            "booked": row["booked"],
            "capacity": row["capacity"],
            "spots_left": max(0, row["capacity"] - row["booked"]),
            "load_percent": load_percent,
            "is_full": is_full,
            "is_busy": (not is_full) and load_percent >= Config.BUSY_SLOT_PERCENT,
        })

        # The first slot that still has room is the "Next Available Slot"
        if next_open_slot_id is None and not is_full:
            next_open_slot_id = row["id"]

    return {"slots": slots, "next_open_slot_id": next_open_slot_id}


# =========================================================
# Placing an order
# =========================================================

def clean_cart_lines(raw_lines):
    # Turn whatever the browser sent into {menu_item_id: quantity}, or explain what is wrong
    if not isinstance(raw_lines, list) or len(raw_lines) == 0:
        raise OrderError("Your cart is empty.")

    quantities = {}

    for line in raw_lines:
        try:
            item_id = int(line.get("item_id"))
            quantity = int(line.get("quantity"))
        except (AttributeError, TypeError, ValueError):
            raise OrderError("Your cart has an item we could not read. Please refresh the page.")

        quantities[item_id] = quantities.get(item_id, 0) + quantity

    if len(quantities) > Config.MAX_DIFFERENT_ITEMS:
        raise OrderError(f"You can order up to {Config.MAX_DIFFERENT_ITEMS} different dishes at a time.")

    for quantity in quantities.values():
        if quantity < 1 or quantity > Config.MAX_QTY_PER_ITEM:
            raise OrderError(f"You can order 1 to {Config.MAX_QTY_PER_ITEM} portions of each dish.")

    return quantities


def make_pickup_otp():
    # A 4-digit code from 1000 to 9999 (never starts with 0, so it is easy to read out)
    return str(secrets.randbelow(9000) + 1000)


def place_order(student_id, raw_lines, slot_id, payment_method):
    """Validate everything, save the order and take the dishes out of stock.
    Returns the new order's id. Raises OrderError with a friendly message."""

    quantities = clean_cart_lines(raw_lines)

    if payment_method not in ("mock_upi", "counter"):
        raise OrderError("Please choose how you will pay.")

    try:
        slot_id = int(slot_id)
    except (TypeError, ValueError):
        raise OrderError("Please choose a pickup slot.", slot_problem=True)

    now = datetime.now()
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            # ---- 1. Lock and check the pickup slot ----
            cursor.execute(
                "SELECT id, slot_date, start_time, capacity FROM pickup_slots WHERE id = %s FOR UPDATE",
                (slot_id,),
            )
            slot = cursor.fetchone()

            if slot is None:
                raise OrderError("That pickup slot does not exist.", slot_problem=True)

            slot_start = build_slot_start(slot["slot_date"], slot["start_time"])
            if slot_start < now + timedelta(minutes=Config.SLOT_LEAD_MINUTES):
                raise OrderError("That pickup slot is too soon. Please choose a later one.", slot_problem=True)

            cursor.execute(
                "SELECT COUNT(*) AS booked FROM orders WHERE slot_id = %s AND status <> 'cancelled'",
                (slot_id,),
            )
            # Prevent ordering if the slot is at 100% capacity
            if cursor.fetchone()["booked"] >= slot["capacity"]:
                raise OrderError("That pickup slot just filled up.", slot_problem=True)

            # ---- 2. Lock and check every dish in the cart ----
            item_ids = list(quantities.keys())
            placeholders = ", ".join(["%s"] * len(item_ids))   # "%s, %s, %s" - values stay separate (safe)
            cursor.execute(
                f"""
                SELECT id, name, price, stock_qty, is_sold_out, is_active
                FROM menu_items
                WHERE id IN ({placeholders})
                FOR UPDATE
                """,
                item_ids,
            )
            menu_rows = {row["id"]: row for row in cursor.fetchall()}

            problems = []
            for item_id, quantity in quantities.items():
                item = menu_rows.get(item_id)

                if item is None or not item["is_active"]:
                    problems.append("One of the dishes in your cart is no longer on the menu.")
                elif item["is_sold_out"] or item["stock_qty"] <= 0:
                    problems.append(f"{item['name']} is sold out.")
                elif item["stock_qty"] < quantity:
                    problems.append(f"Only {item['stock_qty']} {item['name']} left.")

            if problems:
                raise OrderError(" ".join(problems))

            # ---- 3. Save the order (prices come from the database, never from the browser) ----
            total_amount = sum(menu_rows[item_id]["price"] * quantity for item_id, quantity in quantities.items())
            payment_status = "paid" if payment_method == "mock_upi" else "pending"

            cursor.execute(
                """
                INSERT INTO orders
                    (student_id, slot_id, status, payment_method, payment_status,
                     total_amount, pickup_otp, qr_token)
                VALUES (%s, %s, 'confirmed', %s, %s, %s, %s, %s)
                """,
                (student_id, slot_id, payment_method, payment_status,
                 total_amount, make_pickup_otp(), secrets.token_hex(8)),
            )
            order_id = cursor.lastrowid

            # ---- 4. Save each dish and reduce its stock ----
            for item_id, quantity in quantities.items():
                item = menu_rows[item_id]

                cursor.execute(
                    "INSERT INTO order_items (order_id, menu_item_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
                    (order_id, item_id, quantity, item["price"]),
                )

                new_stock = item["stock_qty"] - quantity
                # Auto-disable the dish when stock hits 0
                cursor.execute(
                    "UPDATE menu_items SET stock_qty = %s, is_sold_out = %s WHERE id = %s",
                    (new_stock, 1 if new_stock == 0 else 0, item_id),
                )

        connection.commit()
        return order_id

    except Exception:
        # Undo everything if any step failed, so we never keep a half-finished order
        connection.rollback()
        raise
    finally:
        connection.close()


# =========================================================
# Cancelling an order
# =========================================================

def can_student_cancel(status, slot_start):
    # Allowed until 10 minutes before pickup, and only before the kitchen starts preparing
    if status != "confirmed":
        return False
    return datetime.now() <= slot_start - timedelta(minutes=Config.CANCEL_BEFORE_SLOT_MINUTES)


def cancel_order(order_id, student_id):
    """Cancel one of the student's own orders and put its dishes back in stock."""
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.id, o.status, o.payment_status, s.slot_date, s.start_time
                FROM orders o
                JOIN pickup_slots s ON s.id = o.slot_id
                WHERE o.id = %s AND o.student_id = %s
                FOR UPDATE
                """,
                (order_id, student_id),
            )
            order = cursor.fetchone()

            if order is None:
                raise OrderError("We could not find that order.")

            if order["status"] == "cancelled":
                raise OrderError("This order is already cancelled.")

            if order["status"] != "confirmed":
                raise OrderError("The kitchen has already started this order, so it can no longer be cancelled.")

            slot_start = build_slot_start(order["slot_date"], order["start_time"])
            if not can_student_cancel(order["status"], slot_start):
                raise OrderError(
                    f"Orders can only be cancelled up to {Config.CANCEL_BEFORE_SLOT_MINUTES} minutes before pickup."
                )

            # Put every dish back on the shelf
            cursor.execute("SELECT menu_item_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
            for line in cursor.fetchall():
                # is_sold_out is set BEFORE stock_qty on purpose: MySQL reads these left to right,
                # so it still sees the old stock. A dish that had 0 left becomes available again.
                cursor.execute(
                    """
                    UPDATE menu_items
                    SET is_sold_out = IF(stock_qty = 0, 0, is_sold_out),
                        stock_qty = stock_qty + %s
                    WHERE id = %s
                    """,
                    (line["quantity"], line["menu_item_id"]),
                )

            new_payment_status = "refunded" if order["payment_status"] == "paid" else order["payment_status"]
            cursor.execute(
                "UPDATE orders SET status = 'cancelled', cancelled_at = %s, payment_status = %s WHERE id = %s",
                (datetime.now(), new_payment_status, order_id),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# =========================================================
# Reading one order (for the tracker page)
# =========================================================

# The 4 tracker steps from the blueprint
STATUS_STEPS = {"confirmed": 1, "preparing": 2, "ready": 3, "collected": 4}


def build_order_payload(order_id, student_id):
    """Everything the order tracker needs, as plain values ready for JSON.
    Returns None if the order does not exist or belongs to someone else."""

    order = fetch_one(
        """
        SELECT o.id, o.status, o.payment_method, o.payment_status, o.total_amount,
               o.pickup_otp, o.qr_token, o.uncollected_flag, o.created_at,
               s.slot_date, s.start_time, s.end_time
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        WHERE o.id = %s AND o.student_id = %s
        """,
        (order_id, student_id),
    )

    if order is None:
        return None

    items = fetch_all(
        """
        SELECT m.name, m.food_type, oi.quantity, oi.unit_price
        FROM order_items oi
        JOIN menu_items m ON m.id = oi.menu_item_id
        WHERE oi.order_id = %s
        ORDER BY m.name
        """,
        (order_id,),
    )

    slot_start = build_slot_start(order["slot_date"], order["start_time"])
    minutes_to_pickup = round((slot_start - datetime.now()).total_seconds() / 60)

    return {
        "id": order["id"],
        "status": order["status"],
        "step": STATUS_STEPS.get(order["status"], 0),      # 0 means cancelled
        "payment_method": order["payment_method"],
        "payment_status": order["payment_status"],
        "total_amount": float(order["total_amount"]),
        "pickup_otp": order["pickup_otp"],
        "qr_token": order["qr_token"],
        "is_uncollected": bool(order["uncollected_flag"]),
        "slot_label": f"{format_clock(order['start_time'])} - {format_clock(order['end_time'])}",
        "slot_when": format_order_time(order["slot_date"], order["start_time"]),
        "minutes_to_pickup": minutes_to_pickup,
        "can_cancel": can_student_cancel(order["status"], slot_start),
        "items": [
            {
                "name": item["name"],
                "food_type": item["food_type"],
                "quantity": item["quantity"],
                "unit_price": float(item["unit_price"]),
            }
            for item in items
        ],
    }
