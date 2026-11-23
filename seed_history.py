"""
seed_history.py - Fills the database with realistic sample activity.

Run it AFTER schema.sql and seed.sql:
    python seed_history.py

It creates:
  - Pickup slots (15 minutes each) for the last 28 days and for today
  - Past orders with a lunch rush, plus cancellations and uncollected orders
  - Prepared batch quantities, waste logs and student feedback
  - A "live" queue for today (only if you run it during canteen hours)

The waste rate gradually improves over the weeks so the
Sustainability Trend chart tells a believable story.
Running it again clears the old history and rebuilds it.
"""

import random
import secrets
from datetime import date, datetime, time, timedelta

from config import Config
from db import get_connection

# ---------- Numbers you can safely edit ----------
HISTORY_DAYS = 28               # How many past days to generate
ORDERS_PER_DAY = 100            # Average orders on a normal day
STARTING_WASTE_RATE = 0.22      # Surplus food, 4 weeks ago (22% of sold)
ENDING_WASTE_RATE = 0.08        # Surplus food, yesterday (8% of sold)
WASTE_KG_PER_PORTION = 0.35     # Rough weight of one wasted portion

# Same random numbers every run, so your demo looks the same each time.
# Delete this line if you want different data on every run.
random.seed(42)

# How busy each hour is. Lunch (12 and 13) is the rush.
HOUR_DEMAND = {9: 2, 10: 3, 11: 3, 12: 9, 13: 8, 14: 4, 15: 3, 16: 3}

# Day-of-week busyness (Monday = 0). The canteen is closed on Sundays.
DAY_BUSYNESS = {0: 1.0, 1: 1.1, 2: 1.15, 3: 1.2, 4: 1.3, 5: 0.7}

# How popular each dish is. Higher number = ordered more often.
POPULARITY = {
    "Veg Thali": 9, "Chicken Biryani": 8, "Masala Dosa": 7, "Samosa": 9,
    "Masala Chai": 10, "Veg Biryani": 6, "Chole Bhature": 6, "Pav Bhaji": 5,
    "Idli Sambar": 6, "Veg Sandwich": 5, "Cold Coffee": 5, "Chicken Roll": 5,
    "Paneer Rice Bowl": 4, "Egg Roll": 4, "Veg Maggi": 4, "Poha": 4,
    "Fresh Lime Soda": 4, "Rajma Chawal": 3, "Egg Fried Rice": 3,
    "Aloo Paratha": 3, "Paneer Wrap": 3, "Egg Bhurji Pav": 2, "Fruit Salad": 2,
}

# Some dishes are over-prepared more often than others.
WASTE_BIAS = {
    "Pav Bhaji": 1.6, "Veg Biryani": 1.5, "Fruit Salad": 1.8,
    "Idli Sambar": 1.3, "Rajma Chawal": 1.4, "Aloo Paratha": 1.3,
}

FEEDBACK_COMMENTS = [
    "Hot and fresh!", "Quick pickup, loved it.", "Portion was great.",
    "Slightly cold today.", "Best biryani on campus.", "Needs more chutney.",
    "Queue was much shorter with Qless.", "Tasty and good value.",
]


# =========================================================
# Small helper functions
# =========================================================

def build_slot_times(day):
    # Return a list of (start, end) datetimes covering opening to closing time
    slots = []
    # Midnight + hours (not time(hour)), so a close hour of 24 is allowed
    midnight = datetime.combine(day, time.min)
    current = midnight + timedelta(hours=Config.CANTEEN_OPEN_HOUR)
    closing = midnight + timedelta(hours=Config.CANTEEN_CLOSE_HOUR)
    slot_length = timedelta(minutes=Config.SLOT_LENGTH_MINUTES)

    while current < closing:
        slots.append((current, current + slot_length))
        current += slot_length

    return slots


def create_slots_for_day(cursor, day):
    # Insert every pickup slot for one day and remember each slot's id
    slots = []

    for start, end in build_slot_times(day):
        cursor.execute(
            """
            INSERT INTO pickup_slots (slot_date, start_time, end_time, capacity)
            VALUES (%s, %s, %s, %s)
            """,
            (day, start.time(), end.time(), Config.DEFAULT_SLOT_CAPACITY),
        )
        slots.append({"id": cursor.lastrowid, "start": start, "orders": 0})

    return slots


def item_is_served_at(category, hour):
    # Breakfast ends before 11:00, and meals are served from 11:00 to 16:00
    if category == "Breakfast":
        return hour < 11
    if category == "Meals":
        return 11 <= hour < 16
    return True


def pick_items_for_order(menu_items, hour):
    # Choose 1 to 3 dishes that are actually served at this hour
    served_items = [item for item in menu_items if item_is_served_at(item["category"], hour)]
    weights = [POPULARITY.get(item["name"], 3) for item in served_items]
    how_many_picks = random.choices([1, 2, 3], weights=[60, 30, 10])[0]
    picked_items = random.choices(served_items, weights=weights, k=how_many_picks)

    # Merge repeats, so two picks of Samosa become one line with quantity 2
    lines = {}
    for item in picked_items:
        if item["id"] not in lines:
            lines[item["id"]] = {"item_id": item["id"], "quantity": 0, "price": item["price"]}
        lines[item["id"]]["quantity"] += 1

    return list(lines.values())


def pick_slot(slots):
    # Busy hours get more orders, but never choose a slot that is already full
    open_slots = [slot for slot in slots if slot["orders"] < Config.DEFAULT_SLOT_CAPACITY]
    weights = [HOUR_DEMAND.get(slot["start"].hour, 1) for slot in open_slots]
    return random.choices(open_slots, weights=weights, k=1)[0]


def make_created_at(slot_start):
    # Students usually order 15 to 120 minutes before their pickup time
    created_at = slot_start - timedelta(minutes=random.randint(15, 120))
    earliest = slot_start.replace(hour=8, minute=0)

    if created_at < earliest:
        created_at = earliest + timedelta(minutes=random.randint(0, 20))

    return created_at


def decide_payment_status(payment_method, order_status):
    # Mock UPI is paid immediately; counter payment is paid at pickup
    if order_status == "cancelled":
        return "refunded" if payment_method == "mock_upi" else "pending"
    if payment_method == "mock_upi":
        return "paid"
    return "paid" if order_status == "collected" else "pending"


# =========================================================
# Database insert helpers
# =========================================================

def insert_order(cursor, student_id, slot, status, lines, created_at, times, uncollected_flag=0):
    payment_method = random.choices(["mock_upi", "counter"], weights=[60, 40])[0]
    payment_status = decide_payment_status(payment_method, status)
    total_amount = sum(line["price"] * line["quantity"] for line in lines)

    cursor.execute(
        """
        INSERT INTO orders
            (student_id, slot_id, status, payment_method, payment_status,
             total_amount, pickup_otp, qr_token, uncollected_flag,
             created_at, preparing_at, ready_at, collected_at, cancelled_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            student_id, slot["id"], status, payment_method, payment_status,
            total_amount, str(random.randint(1000, 9999)), secrets.token_hex(8),
            uncollected_flag, created_at,
            times.get("preparing_at"), times.get("ready_at"),
            times.get("collected_at"), times.get("cancelled_at"),
        ),
    )
    order_id = cursor.lastrowid

    for line in lines:
        cursor.execute(
            """
            INSERT INTO order_items (order_id, menu_item_id, quantity, unit_price)
            VALUES (%s, %s, %s, %s)
            """,
            (order_id, line["item_id"], line["quantity"], line["price"]),
        )

    return order_id


def insert_feedback(cursor, order_id, student_id, collected_at):
    # Ratings lean positive, like real campus feedback
    rating = random.choices([5, 4, 3, 2, 1], weights=[40, 35, 15, 7, 3])[0]
    comment = random.choice(FEEDBACK_COMMENTS) if random.random() < 0.5 else None

    cursor.execute(
        """
        INSERT INTO feedback (order_id, student_id, rating, comment, created_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (order_id, student_id, rating, comment, collected_at + timedelta(minutes=20)),
    )


def insert_daily_batch(cursor, item_id, day, prepared_qty):
    cursor.execute(
        """
        INSERT INTO daily_batches (menu_item_id, batch_date, prepared_qty)
        VALUES (%s, %s, %s)
        """,
        (item_id, day, prepared_qty),
    )


def insert_waste(cursor, item_id, day, quantity, reason, staff_id):
    cursor.execute(
        """
        INSERT INTO waste_logs
            (menu_item_id, waste_date, quantity_wasted, weight_kg, reason, logged_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            item_id, day, quantity, round(quantity * WASTE_KG_PER_PORTION, 2),
            reason, staff_id, datetime.combine(day, time(17, 15)),
        ),
    )


# =========================================================
# Building one day of history
# =========================================================

def seed_past_day(cursor, day, students, menu_items, staff_id, waste_rate):
    slots = create_slots_for_day(cursor, day)
    busyness = DAY_BUSYNESS.get(day.weekday(), 1.0)
    total_orders = int(ORDERS_PER_DAY * busyness * random.uniform(0.9, 1.1))

    sold_by_item = {}           # Portions sold per dish today (cancelled excluded)
    uncollected_by_item = {}    # Portions that were never picked up

    for _ in range(total_orders):
        slot = pick_slot(slots)
        start = slot["start"]
        lines = pick_items_for_order(menu_items, start.hour)
        student_id = random.choice(students)["id"]
        created_at = make_created_at(start)

        # About 4% are cancelled, 2% are never collected, the rest are collected
        roll = random.random()
        times = {}
        uncollected_flag = 0

        if roll < 0.04:
            status = "cancelled"
            times["cancelled_at"] = created_at + timedelta(minutes=random.randint(2, 8))
        elif roll < 0.06:
            status = "ready"
            uncollected_flag = 1
            times["preparing_at"] = start - timedelta(minutes=12)
            times["ready_at"] = start - timedelta(minutes=3)
        else:
            status = "collected"
            times["preparing_at"] = start - timedelta(minutes=12)
            times["ready_at"] = start - timedelta(minutes=3)
            times["collected_at"] = start + timedelta(minutes=random.randint(0, 10))

        if status != "cancelled":
            slot["orders"] += 1
            for line in lines:
                item_id = line["item_id"]
                sold_by_item[item_id] = sold_by_item.get(item_id, 0) + line["quantity"]
                if uncollected_flag:
                    uncollected_by_item[item_id] = uncollected_by_item.get(item_id, 0) + line["quantity"]

        order_id = insert_order(cursor, student_id, slot, status, lines, created_at, times, uncollected_flag)

        # Roughly 45% of collected orders get a 1-tap rating
        if status == "collected" and random.random() < 0.45:
            insert_feedback(cursor, order_id, student_id, times["collected_at"])

    # Kitchen prepared batch = sold + surplus. The surplus becomes waste.
    for item in menu_items:
        sold = sold_by_item.get(item["id"], 0)
        if sold == 0:
            continue

        bias = WASTE_BIAS.get(item["name"], 1.0)
        # Adding random() before int() rounds up or down fairly, so small numbers still vary
        surplus = int(sold * waste_rate * bias * random.uniform(0.5, 1.5) + random.random())

        insert_daily_batch(cursor, item["id"], day, sold + surplus)

        uncollected_qty = uncollected_by_item.get(item["id"], 0)
        if uncollected_qty > 0:
            insert_waste(cursor, item["id"], day, uncollected_qty, "uncollected", staff_id)

        if surplus > 0:
            reason = random.choices(["overproduction", "spoilage"], weights=[75, 25])[0]
            insert_waste(cursor, item["id"], day, surplus, reason, staff_id)


# =========================================================
# Today: slots, batch quantities and a live queue
# =========================================================

def get_live_status_and_times(slot_start, now):
    # Decide an order's status based on how close its pickup slot is to "now"
    minutes_to_pickup = (slot_start - now).total_seconds() / 60
    times = {}

    if minutes_to_pickup < -10:
        status = "collected"
        times["preparing_at"] = slot_start - timedelta(minutes=12)
        times["ready_at"] = slot_start - timedelta(minutes=3)
        times["collected_at"] = slot_start + timedelta(minutes=random.randint(0, 8))
    elif minutes_to_pickup < 0:
        status = "ready"
        times["preparing_at"] = slot_start - timedelta(minutes=12)
        times["ready_at"] = slot_start - timedelta(minutes=3)
    elif minutes_to_pickup < 15:
        status = "preparing"
        times["preparing_at"] = min(slot_start - timedelta(minutes=12), now - timedelta(minutes=1))
    else:
        status = "confirmed"

    return status, times


def seed_today(cursor, students, menu_items):
    today = date.today()
    now = datetime.now()
    slots = create_slots_for_day(cursor, today)

    # Today's prepared batch quantities come from the menu table
    for item in menu_items:
        insert_daily_batch(cursor, item["id"], today, item["prepared_batch_qty"])

    # Only create live orders for slots from 30 minutes ago to 2 hours ahead
    window_start = now - timedelta(minutes=30)
    window_end = now + timedelta(minutes=120)
    live_slots = [slot for slot in slots if window_start <= slot["start"] <= window_end]

    if not live_slots:
        print("   The canteen is closed right now, so no live orders were created for today.")
        print("   Run this script again between 09:00 and 17:00 to get a live queue.")
        return 0

    live_orders = 0

    for slot in live_slots:
        # Lunch slots are busy, other slots are quiet
        if slot["start"].hour in (12, 13):
            how_many_orders = random.randint(9, 11)
        else:
            how_many_orders = random.randint(2, 5)

        for _ in range(how_many_orders):
            lines = pick_items_for_order(menu_items, slot["start"].hour)
            student_id = random.choice(students)["id"]
            status, times = get_live_status_and_times(slot["start"], now)

            # An order cannot be placed in the future
            created_at = min(
                make_created_at(slot["start"]),
                now - timedelta(minutes=random.randint(1, 15)),
            )

            insert_order(cursor, student_id, slot, status, lines, created_at, times)
            live_orders += 1

    return live_orders


# =========================================================
# Main program
# =========================================================

def clear_old_history(cursor):
    # Children first, so foreign keys do not complain
    for table_name in ["feedback", "order_items", "orders", "waste_logs",
                       "daily_batches", "pickup_slots", "notifications"]:
        cursor.execute(f"DELETE FROM {table_name}")


def print_summary(cursor):
    print("\nRows in each table now:")
    for table_name in ["users", "menu_items", "pickup_slots", "orders", "order_items",
                       "daily_batches", "waste_logs", "feedback"]:
        cursor.execute(f"SELECT COUNT(*) AS total FROM {table_name}")
        print(f"   {table_name:<15} {cursor.fetchone()['total']}")


def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE role = 'student'")
            students = cursor.fetchall()

            cursor.execute("SELECT id FROM users WHERE role = 'staff' LIMIT 1")
            staff = cursor.fetchone()

            cursor.execute(
                """
                SELECT id, name, category, price, prepared_batch_qty
                FROM menu_items WHERE is_active = 1
                """
            )
            menu_items = cursor.fetchall()

            if not students or not staff or not menu_items:
                print("No users or menu items found. Run sql/seed.sql first.")
                return

            print("Clearing old history...")
            clear_old_history(cursor)

            today = date.today()
            print(f"Creating {HISTORY_DAYS} days of history (this takes a few seconds)...")

            for days_ago in range(HISTORY_DAYS, 0, -1):
                day = today - timedelta(days=days_ago)

                # Canteen is closed on Sundays
                if day.weekday() == 6:
                    continue

                # Waste rate falls smoothly from the starting rate to the ending rate
                position = HISTORY_DAYS - days_ago
                waste_rate = STARTING_WASTE_RATE - (
                    (STARTING_WASTE_RATE - ENDING_WASTE_RATE) * position / (HISTORY_DAYS - 1)
                )

                seed_past_day(cursor, day, students, menu_items, staff["id"], waste_rate)
                connection.commit()

            print("Creating today's slots and live queue...")
            live_orders = seed_today(cursor, students, menu_items)
            connection.commit()

            print(f"   Live orders created for today: {live_orders}")
            print_summary(cursor)

        print("\nDone. History seeded successfully.")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()