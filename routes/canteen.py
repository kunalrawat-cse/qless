"""
canteen.py - Everything kitchen/counter staff and canteen managers do.

HTML Pages (strictly split into Rush-Hour Ops vs. Post-Rush & Admin):
  /canteen/dashboard    Layout A (Split Command) live operational overview
  /canteen/orders       Live Orders & Kitchen Queue grouped by 15-min slot
  /canteen/pickup       Pickup Queue / QR token & 4-digit OTP handover check
  /canteen/menu         Menu & Item Availability + Today's Prepared Batch Qty
  /canteen/waste        Shift / End-of-Day Waste Entry
  /canteen/analytics    Phase 7 Demand & Waste Analytics placeholder
  /canteen/settings     15-min slot capacities, dish CRUD, staff accounts (Manager only)

JSON API (under /api/canteen/... so access.py returns JSON 401/403 on fetch()):
  GET  /api/canteen/dashboard              15s live snapshot for Split Command dashboard
  GET  /api/canteen/orders                 15s live slot-grouped order queue
  POST /api/canteen/orders/<id>/status     1-tap Confirmed -> Preparing -> Ready -> Collected
  POST /api/canteen/pickup/verify          Lookup or mark Collected by 4-digit OTP / QR token
  POST /api/canteen/menu/<id>/stock        1-tap Sold Out toggle, stock_qty & prepared_batch_qty
  POST /api/canteen/waste                  Log shift waste (overproduction, spoilage, uncollected)
  POST /api/canteen/menu/save              Create or edit a menu dish (Manager only)
  POST /api/canteen/settings/slots         Update 15-minute slot capacities (Manager only)
  POST /api/canteen/settings/staff         Create a staff/manager account (Manager only)
"""

from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, render_template, render_template_string, request
from jinja2 import TemplateNotFound
from pymysql.err import IntegrityError
from werkzeug.security import generate_password_hash

from config import Config
from db import execute, fetch_all, fetch_one, get_connection
from routes.access import role_required
from routes.auth import check_password_strength, is_valid_email
from routes.order_logic import (
    build_slot_start,
    calculate_slot_load,
    create_slots_if_missing,
    format_clock,
    to_time,
)

canteen_bp = Blueprint("canteen", __name__)

VALID_WASTE_REASONS = ("overproduction", "spoilage", "uncollected")
VALID_FOOD_TYPES = ("veg", "non_veg", "egg")
NEXT_STATUS_MAP = {
    "confirmed": "preparing",
    "preparing": "ready",
    "ready": "collected",
}

# Used for Phase 7 Analytics (and any Phase 6B screen before its template file is added)
PLACEHOLDER_TEMPLATE = """
{% extends "canteen_base.html" %}
{% block title %}{{ page_title }} - Qless Canteen{% endblock %}
{% block canteen_content %}
  <section class="canteen-card canteen-placeholder">
    <div class="canteen-placeholder__icon">
      <i data-lucide="bar-chart-3"></i>
    </div>
    <span class="canteen-badge canteen-badge--mint">{{ phase_label }}</span>
    <h1 class="canteen-placeholder__title">{{ page_title }}</h1>
    <p class="canteen-placeholder__text">{{ page_note }}</p>
    <div class="canteen-placeholder__actions">
      <a class="canteen-btn canteen-btn--primary" href="{{ url_for('canteen.dashboard') }}">
        <i data-lucide="layout-dashboard"></i>
        <span>Back to Rush-Hour Dashboard</span>
      </a>
      <a class="canteen-btn canteen-btn--outline" href="{{ url_for('canteen.waste_entry') }}">
        <i data-lucide="trash-2"></i>
        <span>Open Waste Entry</span>
      </a>
    </div>
  </section>
{% endblock %}
"""


# =========================================================
# Small helpers
# =========================================================

def json_error(message, status_code=400):
    return jsonify({"error": message}), status_code


def render_canteen_page(template_name, page_title, page_note, phase_label="Phase 6B / Phase 7", **context):
    # Renders the real template file when present, or a clean canteen layout fallback
    try:
        return render_template(template_name, **context)
    except TemplateNotFound:
        return render_template_string(
            PLACEHOLDER_TEMPLATE,
            page_title=page_title,
            page_note=page_note,
            phase_label=phase_label,
            **context,
        )


def flag_overdue_uncollected_orders():
    """Orders sitting in 'ready' for over 30 minutes get uncollected_flag = 1
    so counter staff see an orange warning to follow up or log waste."""
    cutoff = datetime.now() - timedelta(minutes=Config.UNCOLLECTED_AFTER_MINUTES)
    execute(
        """
        UPDATE orders
        SET uncollected_flag = 1
        WHERE status = 'ready'
          AND uncollected_flag = 0
          AND COALESCE(ready_at, created_at) <= %s
        """,
        (cutoff,),
    )


def get_active_or_next_slot(today_slots, now_time):
    """Pick the 15-minute slot currently in progress, or the next upcoming one today."""
    for slot in today_slots:
        end_t = to_time(slot["end_time"])
        if end_t >= now_time:
            return slot
    if today_slots:
        return today_slots[-1]
    return None


def attach_items_to_orders(order_rows):
    """Fetch all order_items for a list of order dicts in ONE query instead of N queries."""
    if not order_rows:
        return {}

    order_ids = [row["id"] for row in order_rows]
    placeholders = ", ".join(["%s"] * len(order_ids))
    lines = fetch_all(
        f"""
        SELECT oi.order_id, oi.menu_item_id, oi.quantity, oi.unit_price,
               m.name, m.food_type
        FROM order_items oi
        JOIN menu_items m ON m.id = oi.menu_item_id
        WHERE oi.order_id IN ({placeholders})
        ORDER BY m.name
        """,
        order_ids,
    )

    items_by_order = {order_id: [] for order_id in order_ids}
    for line in lines:
        items_by_order[line["order_id"]].append({
            "menu_item_id": line["menu_item_id"],
            "name": line["name"],
            "food_type": line["food_type"],
            "quantity": int(line["quantity"]),
            "unit_price": float(line["unit_price"]),
        })
    return items_by_order


def serialize_order_row(row, items, now):
    """Turn a database order row into plain JSON-friendly values for templates and fetch()."""
    slot_start = build_slot_start(row["slot_date"], row["start_time"])
    slot_end = build_slot_start(row["slot_date"], row["end_time"])
    reference_time = row.get("ready_at") or row.get("created_at") or now
    minutes_waiting = max(0, int((now - reference_time).total_seconds() // 60))
    minutes_since_ready = (
        max(0, int((now - row["ready_at"]).total_seconds() // 60))
        if row.get("ready_at")
        else minutes_waiting
    )

    next_status = NEXT_STATUS_MAP.get(row["status"])
    action_label = None
    if row["status"] == "confirmed":
        action_label = "Start Prep"
    elif row["status"] == "preparing":
        action_label = "Mark Ready"
    elif row["status"] == "ready":
        action_label = "Mark Collected"

    return {
        "id": row["id"],
        "student_name": row["student_name"],
        "campus_id": row["campus_id"] or "—",
        "slot_id": row["slot_id"],
        "slot_label": f"{format_clock(row['start_time'])} - {format_clock(row['end_time'])}",
        "slot_start_label": format_clock(row["start_time"]),
        "status": row["status"],
        "next_status": next_status,
        "action_label": action_label,
        "payment_method": row["payment_method"],
        "payment_method_label": "UPI Paid" if row["payment_method"] == "mock_upi" else "Counter Pay",
        "payment_status": row["payment_status"],
        "total_amount": float(row["total_amount"]),
        "pickup_otp": row["pickup_otp"],
        "qr_token": row["qr_token"],
        "is_uncollected": bool(row["uncollected_flag"]),
        "minutes_waiting": minutes_waiting,
        "minutes_since_ready": minutes_since_ready,
        "is_slot_past": now > slot_end,
        "is_slot_now": slot_start <= now <= slot_end,
        "created_label": row["created_at"].strftime("%I:%M %p").lstrip("0") if row.get("created_at") else "",
        "items": items,
        "total_portions": sum(item["quantity"] for item in items),
    }


# =========================================================
# Dashboard payload builder (used by HTML + 15s JSON poll)
# =========================================================

def build_dashboard_payload():
    """Assemble every metric, queue group, batch count, stock row and alert
    needed by Layout A (Split Command) in one consistent snapshot."""
    now = datetime.now()
    today = now.date()

    create_slots_if_missing(today)
    flag_overdue_uncollected_orders()

    # ---- 1. Today's 15-minute slots and booking counts ----
    today_slots = fetch_all(
        """
        SELECT s.id, s.slot_date, s.start_time, s.end_time, s.capacity,
               COUNT(o.id) AS booked
        FROM pickup_slots s
        LEFT JOIN orders o ON o.slot_id = s.id AND o.status <> 'cancelled'
        WHERE s.slot_date = %s
        GROUP BY s.id, s.slot_date, s.start_time, s.end_time, s.capacity
        ORDER BY s.start_time
        """,
        (today,),
    )
    slots_by_id = {slot["id"]: slot for slot in today_slots}
    focus_slot = get_active_or_next_slot(today_slots, now.time())

    # ---- 2. Active orders today (confirmed, preparing, ready) ----
    active_order_rows = fetch_all(
        """
        SELECT o.id, o.student_id, o.slot_id, o.status, o.payment_method,
               o.payment_status, o.total_amount, o.pickup_otp, o.qr_token,
               o.uncollected_flag, o.created_at, o.preparing_at, o.ready_at,
               s.slot_date, s.start_time, s.end_time,
               u.full_name AS student_name, u.campus_id
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN users u ON u.id = o.student_id
        WHERE s.slot_date = %s
          AND o.status IN ('confirmed', 'preparing', 'ready')
        ORDER BY s.start_time ASC,
                 FIELD(o.status, 'confirmed', 'preparing', 'ready'),
                 o.created_at ASC
        """,
        (today,),
    )
    items_by_order = attach_items_to_orders(active_order_rows)

    # ---- 3. Group active orders by 15-minute pickup slot for the Left 65% panel ----
    slot_groups_map = {}
    orders_next_15m = 0
    window_end = now + timedelta(minutes=Config.SLOT_LENGTH_MINUTES)

    for row in active_order_rows:
        serialized = serialize_order_row(row, items_by_order.get(row["id"], []), now)
        slot_start = build_slot_start(row["slot_date"], row["start_time"])
        slot_end = build_slot_start(row["slot_date"], row["end_time"])

        # Count orders belonging to the current or next 15-minute pickup window
        if (slot_start <= now <= slot_end) or (now <= slot_start <= window_end):
            orders_next_15m += 1

        slot_id = row["slot_id"]
        if slot_id not in slot_groups_map:
            slot_info = slots_by_id.get(slot_id, row)
            booked = int(slot_info.get("booked", 1))
            capacity = int(slot_info.get("capacity", Config.DEFAULT_SLOT_CAPACITY))
            load_pct = calculate_slot_load(booked, capacity)
            slot_groups_map[slot_id] = {
                "slot_id": slot_id,
                "slot_label": f"{format_clock(row['start_time'])} - {format_clock(row['end_time'])}",
                "start_label": format_clock(row["start_time"]),
                "end_label": format_clock(row["end_time"]),
                "booked": booked,
                "capacity": capacity,
                "load_percent": load_pct,
                "is_busy": load_pct >= Config.BUSY_SLOT_PERCENT,
                "is_current_slot": slot_start <= now <= slot_end,
                "orders": [],
            }
        slot_groups_map[slot_id]["orders"].append(serialized)

    prep_queue_slots = list(slot_groups_map.values())

    # If no order sits inside the immediate 15-minute clock window, show the next active slot's count
    if orders_next_15m == 0 and prep_queue_slots:
        orders_next_15m = len(prep_queue_slots[0]["orders"])

    # ---- 4. Next-15-Min Item Batching (Right 35% top card) ----
    # Aggregate un-finished dishes (confirmed + preparing) in the immediate/next active slot(s)
    target_slot_ids = []
    for group in prep_queue_slots:
        has_kitchen_work = any(o["status"] in ("confirmed", "preparing") for o in group["orders"])
        if has_kitchen_work:
            target_slot_ids.append(group["slot_id"])
        if len(target_slot_ids) >= 2:
            break

    batch_totals = {}
    batch_window_label = "Next 15-Min Window"
    if target_slot_ids:
        matching_labels = [
            g_slot["start_label"]
            for g_slot in prep_queue_slots
            if g_slot["slot_id"] in target_slot_ids
        ]
        batch_window_label = " & ".join(matching_labels)

    for group in prep_queue_slots:
        if group["slot_id"] not in target_slot_ids:
            continue
        for order in group["orders"]:
            if order["status"] not in ("confirmed", "preparing"):
                continue
            for item in order["items"]:
                item_id = item["menu_item_id"]
                if item_id not in batch_totals:
                    batch_totals[item_id] = {
                        "menu_item_id": item_id,
                        "name": item["name"],
                        "food_type": item["food_type"],
                        "total_portions": 0,
                        "order_count": 0,
                    }
                batch_totals[item_id]["total_portions"] += item["quantity"]
                batch_totals[item_id]["order_count"] += 1

    next_15m_batches = sorted(
        batch_totals.values(),
        key=lambda b: (-b["total_portions"], b["name"]),
    )

    # ---- 5. Menu stock status & Quick Stock Toggles (Right 35% middle card) ----
    menu_rows = fetch_all(
        """
        SELECT id, name, category, price, food_type, stock_qty,
               prepared_batch_qty, is_sold_out, is_featured
        FROM menu_items
        WHERE is_active = 1
        ORDER BY is_sold_out DESC, stock_qty ASC, name ASC
        """
    )

    quick_stock_items = []
    low_stock_alerts_count = 0

    for item in menu_rows:
        is_sold_out = bool(item["is_sold_out"]) or item["stock_qty"] <= 0
        is_low_stock = (not is_sold_out) and item["stock_qty"] <= Config.LOW_STOCK_LIMIT
        if is_sold_out or is_low_stock:
            low_stock_alerts_count += 1

        quick_stock_items.append({
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "price": float(item["price"]),
            "food_type": item["food_type"],
            "stock_qty": int(item["stock_qty"]),
            "prepared_batch_qty": int(item["prepared_batch_qty"]),
            "is_sold_out": is_sold_out,
            "is_low_stock": is_low_stock,
        })

    # ---- 6. Operational Alerts (Right 35% bottom card) ----
    operational_alerts = []

    # Alert priority 1: Uncollected orders > 30 mins
    for row in active_order_rows:
        if row["status"] == "ready" and row["uncollected_flag"]:
            ready_time = row.get("ready_at") or row.get("created_at") or now
            mins_overdue = max(
                Config.UNCOLLECTED_AFTER_MINUTES,
                int((now - ready_time).total_seconds() // 60),
            )
            operational_alerts.append({
                "key": f"uncollected-{row['id']}",
                "level": "urgent",
                "type": "uncollected",
                "title": f"Order #{row['id']} (OTP {row['pickup_otp']}) uncollected for {mins_overdue}m",
                "detail": f"{row['student_name']} • Slot {format_clock(row['start_time'])} — follow up or log waste.",
                "order_id": row["id"],
            })

    # Alert priority 2: Sold-out dishes
    for item in quick_stock_items:
        if item["is_sold_out"]:
            operational_alerts.append({
                "key": f"soldout-{item['id']}",
                "level": "error",
                "type": "sold_out",
                "title": f"{item['name']} is Sold Out",
                "detail": f"{item['category']} • 0 portions left for student ordering.",
                "item_id": item["id"],
            })
        elif item["is_low_stock"]:
            operational_alerts.append({
                "key": f"lowstock-{item['id']}",
                "level": "warning",
                "type": "low_stock",
                "title": f"Low stock: {item['name']} ({item['stock_qty']} left)",
                "detail": f"{item['category']} • Consider cooking a fresh batch or marking Sold Out.",
                "item_id": item["id"],
            })

    # Alert priority 3: High-load pickup slots (>= 80%)
    for group in prep_queue_slots:
        if group["is_busy"]:
            operational_alerts.append({
                "key": f"slotbusy-{group['slot_id']}",
                "level": "warning",
                "type": "slot_busy",
                "title": f"Slot {group['slot_label']} at {group['load_percent']}% capacity",
                "detail": f"{group['booked']} of {group['capacity']} orders booked in this 15-min window.",
                "slot_id": group["slot_id"],
            })

    # ---- 7. Pickup-Slot Load KPI calculation ----
    # Prefer the busiest active queue slot or the current clock slot
    kpi_slot = None
    if prep_queue_slots:
        kpi_slot = max(prep_queue_slots, key=lambda s: s["load_percent"])
    elif focus_slot is not None:
        booked = int(focus_slot["booked"])
        capacity = int(focus_slot["capacity"])
        kpi_slot = {
            "slot_label": f"{format_clock(focus_slot['start_time'])} - {format_clock(focus_slot['end_time'])}",
            "booked": booked,
            "capacity": capacity,
            "load_percent": calculate_slot_load(booked, capacity),
        }
    else:
        kpi_slot = {
            "slot_label": "No active slot",
            "booked": 0,
            "capacity": Config.DEFAULT_SLOT_CAPACITY,
            "load_percent": 0,
        }

    # ---- 8. Bottom Compact Strip: Sales Today & Waste Logged Today ----
    sales_row = fetch_one(
        """
        SELECT COALESCE(SUM(o.total_amount), 0) AS total_revenue,
               COUNT(o.id) AS total_orders,
               SUM(CASE WHEN o.status = 'collected' THEN 1 ELSE 0 END) AS collected_orders
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        WHERE s.slot_date = %s
          AND o.status <> 'cancelled'
        """,
        (today,),
    )

    waste_row = fetch_one(
        """
        SELECT COALESCE(SUM(quantity_wasted), 0) AS total_portions,
               COALESCE(SUM(weight_kg), 0) AS total_kg,
               COUNT(id) AS total_entries
        FROM waste_logs
        WHERE waste_date = %s
        """,
        (today,),
    )

    status_counts = {"confirmed": 0, "preparing": 0, "ready": 0}
    for row in active_order_rows:
        if row["status"] in status_counts:
            status_counts[row["status"]] += 1

    return {
        "server_time": now.strftime("%I:%M:%S %p").lstrip("0"),
        "today_label": today.strftime("%A, %d %b %Y"),
        "kpis": {
            "orders_right_now": len(active_order_rows),
            "confirmed_count": status_counts["confirmed"],
            "preparing_count": status_counts["preparing"],
            "ready_count": status_counts["ready"],
            "orders_next_15m": orders_next_15m,
            "slot_load_percent": kpi_slot["load_percent"],
            "slot_booked": kpi_slot["booked"],
            "slot_capacity": kpi_slot["capacity"],
            "slot_label": kpi_slot["slot_label"],
            "low_stock_alerts_count": low_stock_alerts_count,
            "sold_out_count": sum(1 for item in quick_stock_items if item["is_sold_out"]),
            "low_stock_only_count": sum(1 for item in quick_stock_items if item["is_low_stock"]),
        },
        "prep_queue_slots": prep_queue_slots,
        "batch_window_label": batch_window_label,
        "next_15m_batches": next_15m_batches,
        "quick_stock_items": quick_stock_items,
        "operational_alerts": operational_alerts,
        "bottom_strip": {
            "sales_today_amount": float(sales_row["total_revenue"] or 0),
            "total_orders_today": int(sales_row["total_orders"] or 0),
            "collected_orders_today": int(sales_row["collected_orders"] or 0),
            "waste_portions_today": int(waste_row["total_portions"] or 0),
            "waste_kg_today": float(waste_row["total_kg"] or 0),
            "waste_entries_today": int(waste_row["total_entries"] or 0),
        },
    }


def build_live_orders_payload(status_filter="all"):
    """Build today's slot-grouped order list for the Live Orders screen."""
    now = datetime.now()
    today = now.date()
    create_slots_if_missing(today)
    flag_overdue_uncollected_orders()

    all_today_rows = fetch_all(
        """
        SELECT o.id, o.student_id, o.slot_id, o.status, o.payment_method,
               o.payment_status, o.total_amount, o.pickup_otp, o.qr_token,
               o.uncollected_flag, o.created_at, o.preparing_at, o.ready_at, o.collected_at,
               s.slot_date, s.start_time, s.end_time, s.capacity,
               u.full_name AS student_name, u.campus_id
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN users u ON u.id = o.student_id
        WHERE s.slot_date = %s
          AND o.status <> 'cancelled'
        ORDER BY s.start_time ASC,
                 FIELD(o.status, 'confirmed', 'preparing', 'ready', 'collected'),
                 o.created_at ASC
        """,
        (today,),
    )
    items_by_order = attach_items_to_orders(all_today_rows)

    counts = {"all": 0, "confirmed": 0, "preparing": 0, "ready": 0, "collected": 0}
    for row in all_today_rows:
        if row["status"] in counts:
            counts[row["status"]] += 1
        if row["status"] in ("confirmed", "preparing", "ready"):
            counts["all"] += 1

    slots_map = {}
    for row in all_today_rows:
        if status_filter == "all":
            if row["status"] not in ("confirmed", "preparing", "ready"):
                continue
        elif row["status"] != status_filter:
            continue

        serialized = serialize_order_row(row, items_by_order.get(row["id"], []), now)
        slot_id = row["slot_id"]
        if slot_id not in slots_map:
            slots_map[slot_id] = {
                "slot_id": slot_id,
                "slot_label": f"{format_clock(row['start_time'])} - {format_clock(row['end_time'])}",
                "capacity": int(row["capacity"]),
                "orders": [],
            }
        slots_map[slot_id]["orders"].append(serialized)

    return {
        "server_time": now.strftime("%I:%M:%S %p").lstrip("0"),
        "status_filter": status_filter,
        "counts": counts,
        "slot_groups": list(slots_map.values()),
    }


# =========================================================
# HTML Routes (Rush-Hour Ops & Post-Rush / Admin)
# =========================================================

@canteen_bp.route("/canteen")
@canteen_bp.route("/canteen/dashboard")
@role_required("staff", "manager")
def dashboard():
    data = build_dashboard_payload()
    return render_template("canteen/dashboard.html", dashboard=data)


@canteen_bp.route("/canteen/orders")
@role_required("staff", "manager")
def live_orders():
    status_filter = request.args.get("status", "all").strip().lower()
    if status_filter not in ("all", "confirmed", "preparing", "ready", "collected"):
        status_filter = "all"
    queue_data = build_live_orders_payload(status_filter)
    return render_canteen_page(
        "canteen/live_orders.html",
        page_title="Live Orders & Kitchen Queue",
        page_note="Slot-grouped live kitchen queue will be added in Phase 6B.",
        phase_label="Phase 6B",
        queue=queue_data,
    )


@canteen_bp.route("/canteen/pickup")
@role_required("staff", "manager")
def pickup_queue():
    now = datetime.now()
    today = now.date()
    flag_overdue_uncollected_orders()

    ready_rows = fetch_all(
        """
        SELECT o.id, o.student_id, o.slot_id, o.status, o.payment_method,
               o.payment_status, o.total_amount, o.pickup_otp, o.qr_token,
               o.uncollected_flag, o.created_at, o.ready_at,
               s.slot_date, s.start_time, s.end_time,
               u.full_name AS student_name, u.campus_id
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN users u ON u.id = o.student_id
        WHERE s.slot_date = %s AND o.status = 'ready'
        ORDER BY o.uncollected_flag DESC, s.start_time ASC, o.ready_at ASC
        """,
        (today,),
    )
    ready_items = attach_items_to_orders(ready_rows)
    ready_orders = [serialize_order_row(r, ready_items.get(r["id"], []), now) for r in ready_rows]

    recent_collected_rows = fetch_all(
        """
        SELECT o.id, o.student_id, o.slot_id, o.status, o.payment_method,
               o.payment_status, o.total_amount, o.pickup_otp, o.qr_token,
               o.uncollected_flag, o.created_at, o.ready_at, o.collected_at,
               s.slot_date, s.start_time, s.end_time,
               u.full_name AS student_name, u.campus_id
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN users u ON u.id = o.student_id
        WHERE s.slot_date = %s AND o.status = 'collected'
        ORDER BY o.collected_at DESC
        LIMIT 12
        """,
        (today,),
    )
    collected_items = attach_items_to_orders(recent_collected_rows)
    recent_collected = [
        serialize_order_row(r, collected_items.get(r["id"], []), now)
        for r in recent_collected_rows
    ]

    return render_canteen_page(
        "canteen/pickup_queue.html",
        page_title="Pickup Queue — QR & 4-Digit OTP Verification",
        page_note="Fast counter QR/OTP lookup and meal handover verification screen (Phase 6B).",
        phase_label="Phase 6B",
        ready_orders=ready_orders,
        recent_collected=recent_collected,
    )


@canteen_bp.route("/canteen/menu")
@role_required("staff", "manager")
def menu_availability():
    today = datetime.now().date()
    dishes = fetch_all(
        """
        SELECT m.id, m.name, m.description, m.category, m.price, m.food_type,
               m.allergens, m.prep_time_minutes, m.prepared_batch_qty, m.stock_qty,
               m.is_sold_out, m.is_featured, m.is_active,
               COALESCE(SUM(CASE WHEN o.id IS NOT NULL THEN oi.quantity ELSE 0 END), 0) AS sold_today
        FROM menu_items m
        LEFT JOIN order_items oi ON oi.menu_item_id = m.id
        LEFT JOIN orders o ON o.id = oi.order_id AND o.status <> 'cancelled'
        LEFT JOIN pickup_slots s ON s.id = o.slot_id AND s.slot_date = %s
        WHERE m.is_active = 1
        GROUP BY m.id
        ORDER BY m.category ASC, m.name ASC
        """,
        (today,),
    )

    return render_canteen_page(
        "canteen/menu_availability.html",
        page_title="Menu & Item Availability",
        page_note="Quick Sold Out toggles and Today's Prepared Batch Qty editor (Phase 6B).",
        phase_label="Phase 6B",
        dishes=dishes,
        categories=Config.MENU_CATEGORY_ORDER,
        low_stock_limit=Config.LOW_STOCK_LIMIT,
    )


@canteen_bp.route("/canteen/waste")
@role_required("staff", "manager")
def waste_entry():
    today = datetime.now().date()
    dishes = fetch_all(
        """
        SELECT id, name, category, food_type, prepared_batch_qty, stock_qty
        FROM menu_items
        WHERE is_active = 1
        ORDER BY name ASC
        """
    )
    today_logs = fetch_all(
        """
        SELECT w.id, w.menu_item_id, w.waste_date, w.quantity_wasted, w.weight_kg,
               w.reason, w.notes, w.created_at,
               m.name AS dish_name, m.category,
               u.full_name AS logged_by_name
        FROM waste_logs w
        JOIN menu_items m ON m.id = w.menu_item_id
        LEFT JOIN users u ON u.id = w.logged_by
        WHERE w.waste_date = %s
        ORDER BY w.created_at DESC
        """,
        (today,),
    )
    uncollected_orders = fetch_all(
        """
        SELECT o.id, o.pickup_otp, u.full_name AS student_name,
               s.start_time, s.end_time,
               GROUP_CONCAT(CONCAT(oi.quantity, 'x ', m.name) ORDER BY m.name SEPARATOR ', ') AS items_summary
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN users u ON u.id = o.student_id
        JOIN order_items oi ON oi.order_id = o.id
        JOIN menu_items m ON m.id = oi.menu_item_id
        WHERE s.slot_date = %s
          AND o.status = 'ready'
          AND o.uncollected_flag = 1
        GROUP BY o.id, o.pickup_otp, u.full_name, s.start_time, s.end_time
        ORDER BY s.start_time ASC
        """,
        (today,),
    )

    return render_canteen_page(
        "canteen/waste_entry.html",
        page_title="Shift & End-of-Day Waste Entry",
        page_note="Fast shift waste logging by dish, portions/weight and reason (Phase 6B).",
        phase_label="Phase 6B",
        dishes=dishes,
        today_logs=today_logs,
        uncollected_orders=uncollected_orders,
        today_iso=today.isoformat(),
    )


@canteen_bp.route("/canteen/analytics")
@role_required("staff", "manager")
def analytics():
    return render_canteen_page(
        "canteen/analytics.html",
        page_title="Demand & Waste Analytics + Reports",
        page_note=(
            "Phase 7 adds the 8 post-rush operational charts (Orders by 15-Minute Slot, "
            "Top-Selling Dishes, Prepared vs. Sold by Item, Daily Waste Trend, Waste by Dish, "
            "Waste Reason Breakdown, Slot Utilization Heatmap, and Revenue & Waste KPI Summary) "
            "plus CSV and static report exports."
        ),
        phase_label="Phase 7 — Post-Rush Analytics",
    )


@canteen_bp.route("/canteen/settings")
@role_required("manager")
def settings():
    today = datetime.now().date()
    create_slots_if_missing(today)

    slots = fetch_all(
        """
        SELECT s.id, s.start_time, s.end_time, s.capacity,
               COUNT(o.id) AS booked
        FROM pickup_slots s
        LEFT JOIN orders o ON o.slot_id = s.id AND o.status <> 'cancelled'
        WHERE s.slot_date = %s
        GROUP BY s.id, s.start_time, s.end_time, s.capacity
        ORDER BY s.start_time ASC
        """,
        (today,),
    )
    for slot in slots:
        slot["slot_label"] = f"{format_clock(slot['start_time'])} - {format_clock(slot['end_time'])}"
        slot["load_percent"] = calculate_slot_load(slot["booked"], slot["capacity"])

    all_dishes = fetch_all(
        """
        SELECT id, name, description, category, price, food_type, allergens,
               prep_time_minutes, prepared_batch_qty, stock_qty,
               is_sold_out, is_featured, is_active
        FROM menu_items
        ORDER BY is_active DESC, category ASC, name ASC
        """
    )

    staff_users = fetch_all(
        """
        SELECT id, full_name, email, campus_id, role, created_at
        FROM users
        WHERE role IN ('staff', 'manager')
        ORDER BY role DESC, full_name ASC
        """
    )

    return render_canteen_page(
        "canteen/settings.html",
        page_title="Manager Settings — Slots, Menu & Staff",
        page_note="15-minute slot capacity controls, dish creation/editing, and staff accounts (Phase 6B).",
        phase_label="Phase 6B",
        slots=slots,
        dishes=all_dishes,
        staff_users=staff_users,
        categories=Config.MENU_CATEGORY_ORDER,
        default_capacity=Config.DEFAULT_SLOT_CAPACITY,
    )


# =========================================================
# JSON API Endpoints (10-15s Polling & 1-Tap Staff Actions)
# =========================================================

@canteen_bp.route("/api/canteen/dashboard")
@role_required("staff", "manager")
def api_dashboard():
    return jsonify(build_dashboard_payload())


@canteen_bp.route("/api/canteen/orders")
@role_required("staff", "manager")
def api_orders():
    status_filter = request.args.get("status", "all").strip().lower()
    if status_filter not in ("all", "confirmed", "preparing", "ready", "collected"):
        status_filter = "all"
    return jsonify(build_live_orders_payload(status_filter))


@canteen_bp.route("/api/canteen/orders/<int:order_id>/status", methods=["POST"])
@role_required("staff", "manager")
def api_update_order_status(order_id):
    """Advance an order one step: Confirmed -> Preparing -> Ready -> Collected."""
    data = request.get_json(silent=True) or {}
    requested_status = (data.get("next_status") or "").strip().lower()

    now = datetime.now()
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, student_id, status, payment_status, pickup_otp
                FROM orders
                WHERE id = %s
                FOR UPDATE
                """,
                (order_id,),
            )
            order = cursor.fetchone()

            if order is None:
                return json_error("We could not find that order.", 404)

            current_status = order["status"]
            expected_next = NEXT_STATUS_MAP.get(current_status)

            if expected_next is None:
                return json_error(f"Order #{order_id} is already {current_status}.", 400)

            target_status = requested_status or expected_next
            if target_status != expected_next:
                return json_error(
                    f"Order #{order_id} is currently '{current_status}' and must move to '{expected_next}' next.",
                    400,
                )

            if target_status == "preparing":
                cursor.execute(
                    "UPDATE orders SET status = 'preparing', preparing_at = %s WHERE id = %s",
                    (now, order_id),
                )
            elif target_status == "ready":
                cursor.execute(
                    "UPDATE orders SET status = 'ready', ready_at = %s WHERE id = %s",
                    (now, order_id),
                )
                # Let the student's notification bell know their meal is waiting at the counter
                cursor.execute(
                    """
                    INSERT INTO notifications (user_id, message, type)
                    VALUES (%s, %s, 'order_ready')
                    """,
                    (
                        order["student_id"],
                        f"Order #{order_id} is Ready for Pickup! Show OTP {order['pickup_otp']} at the counter.",
                    ),
                )
            elif target_status == "collected":
                cursor.execute(
                    """
                    UPDATE orders
                    SET status = 'collected',
                        collected_at = %s,
                        payment_status = 'paid',
                        uncollected_flag = 0
                    WHERE id = %s
                    """,
                    (now, order_id),
                )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    status_labels = {
        "preparing": "started preparing",
        "ready": "marked Ready for Pickup",
        "collected": "marked Collected",
    }
    return jsonify({
        "ok": True,
        "order_id": order_id,
        "new_status": target_status,
        "message": f"Order #{order_id} {status_labels.get(target_status, 'updated')}.",
    })


@canteen_bp.route("/api/canteen/pickup/verify", methods=["POST"])
@role_required("staff", "manager")
def api_pickup_verify():
    """Look up an order by 4-digit OTP, QR token, or order ID, and optionally mark it Collected."""
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "lookup").strip().lower()
    raw_code = str(data.get("code") or "").strip()
    explicit_order_id = data.get("order_id")

    now = datetime.now()
    today = now.date()

    # If the staff member clicked "Verify & Hand Over" on a specific matched order card
    if explicit_order_id is not None:
        try:
            explicit_order_id = int(explicit_order_id)
        except (TypeError, ValueError):
            return json_error("Invalid order ID.", 400)

        rows = fetch_all(
            """
            SELECT o.id, o.student_id, o.slot_id, o.status, o.payment_method,
                   o.payment_status, o.total_amount, o.pickup_otp, o.qr_token,
                   o.uncollected_flag, o.created_at, o.ready_at,
                   s.slot_date, s.start_time, s.end_time,
                   u.full_name AS student_name, u.campus_id
            FROM orders o
            JOIN pickup_slots s ON s.id = o.slot_id
            JOIN users u ON u.id = o.student_id
            WHERE o.id = %s
            """,
            (explicit_order_id,),
        )
    else:
        if not raw_code:
            return json_error("Enter a 4-digit Pickup OTP or scan a QR token.", 400)

        # Allow formats like "QLESS:token", "#14", or a 4-digit OTP "4821"
        cleaned_code = raw_code.replace("QLESS:", "").lstrip("#").strip()

        rows = fetch_all(
            """
            SELECT o.id, o.student_id, o.slot_id, o.status, o.payment_method,
                   o.payment_status, o.total_amount, o.pickup_otp, o.qr_token,
                   o.uncollected_flag, o.created_at, o.ready_at,
                   s.slot_date, s.start_time, s.end_time,
                   u.full_name AS student_name, u.campus_id
            FROM orders o
            JOIN pickup_slots s ON s.id = o.slot_id
            JOIN users u ON u.id = o.student_id
            WHERE s.slot_date = %s
              AND o.status <> 'cancelled'
              AND (o.pickup_otp = %s OR o.qr_token = %s OR o.id = %s)
            ORDER BY FIELD(o.status, 'ready', 'preparing', 'confirmed', 'collected'),
                     o.created_at DESC
            """,
            (today, cleaned_code, cleaned_code, cleaned_code if cleaned_code.isdigit() else -1),
        )

    if not rows:
        return json_error("No active order today matched that OTP or QR code.", 404)

    items_by_order = attach_items_to_orders(rows)
    matches = [serialize_order_row(r, items_by_order.get(r["id"], []), now) for r in rows]

    if action == "collect":
        target = matches[0]
        if target["status"] == "collected":
            return json_error(f"Order #{target['id']} was already collected.", 400)
        if target["status"] == "cancelled":
            return json_error(f"Order #{target['id']} is cancelled.", 400)

        execute(
            """
            UPDATE orders
            SET status = 'collected',
                collected_at = %s,
                payment_status = 'paid',
                uncollected_flag = 0
            WHERE id = %s
            """,
            (now, target["id"]),
        )
        target["status"] = "collected"
        target["payment_status"] = "paid"
        target["is_uncollected"] = False
        return jsonify({
            "ok": True,
            "collected": True,
            "order": target,
            "message": f"Order #{target['id']} handed over to {target['student_name']}.",
        })

    return jsonify({
        "ok": True,
        "collected": False,
        "matches": matches,
        "order": matches[0],
    })


@canteen_bp.route("/api/canteen/menu/<int:item_id>/stock", methods=["POST"])
@role_required("staff", "manager")
def api_update_menu_stock(item_id):
    """Handle 1-tap Sold Out toggles, live stock_qty edits, and Today's Prepared Batch Qty."""
    data = request.get_json(silent=True) or {}
    item = fetch_one(
        """
        SELECT id, name, stock_qty, prepared_batch_qty, is_sold_out
        FROM menu_items
        WHERE id = %s AND is_active = 1
        """,
        (item_id,),
    )
    if item is None:
        return json_error("Dish not found.", 404)

    new_stock = int(item["stock_qty"])
    new_batch = int(item["prepared_batch_qty"])
    new_sold_out = int(item["is_sold_out"])
    batch_was_updated = False

    action = (data.get("action") or "").strip().lower()

    if action == "toggle_sold_out":
        currently_sold_out = bool(item["is_sold_out"]) or new_stock <= 0
        if currently_sold_out:
            # Restocking via 1-tap: restore a sensible default if stock was 0
            restock_default = int(data.get("restock_qty") or max(10, new_batch or 10))
            new_stock = new_stock if new_stock > 0 else restock_default
            new_sold_out = 0
        else:
            new_sold_out = 1
    else:
        if "stock_qty" in data and data["stock_qty"] is not None:
            try:
                new_stock = int(data["stock_qty"])
            except (TypeError, ValueError):
                return json_error("Stock quantity must be a whole number.", 400)
            if new_stock < 0 or new_stock > 2000:
                return json_error("Stock quantity must be between 0 and 2000.", 400)
            new_sold_out = 1 if new_stock == 0 else 0

        if "prepared_batch_qty" in data and data["prepared_batch_qty"] is not None:
            try:
                new_batch = int(data["prepared_batch_qty"])
            except (TypeError, ValueError):
                return json_error("Prepared batch quantity must be a whole number.", 400)
            if new_batch < 0 or new_batch > 2000:
                return json_error("Prepared batch quantity must be between 0 and 2000.", 400)
            batch_was_updated = True

        if "is_sold_out" in data and data["is_sold_out"] is not None:
            new_sold_out = 1 if bool(data["is_sold_out"]) else 0
            if new_sold_out == 0 and new_stock == 0:
                new_stock = max(10, new_batch or 10)

    execute(
        """
        UPDATE menu_items
        SET stock_qty = %s,
            prepared_batch_qty = %s,
            is_sold_out = %s
        WHERE id = %s
        """,
        (new_stock, new_batch, new_sold_out, item_id),
    )

    # Keep daily_batches in sync so Phase 7 Prepared vs. Sold charts have daily history
    if batch_was_updated:
        execute(
            """
            INSERT INTO daily_batches (menu_item_id, batch_date, prepared_qty)
            VALUES (%s, CURDATE(), %s)
            ON DUPLICATE KEY UPDATE prepared_qty = VALUES(prepared_qty)
            """,
            (item_id, new_batch),
        )

    is_now_sold_out = bool(new_sold_out) or new_stock <= 0
    status_word = "marked Sold Out" if is_now_sold_out else f"available ({new_stock} left)"

    return jsonify({
        "ok": True,
        "item": {
            "id": item_id,
            "name": item["name"],
            "stock_qty": new_stock,
            "prepared_batch_qty": new_batch,
            "is_sold_out": is_now_sold_out,
            "is_low_stock": (not is_now_sold_out) and new_stock <= Config.LOW_STOCK_LIMIT,
        },
        "message": f"{item['name']} is now {status_word}.",
    })


@canteen_bp.route("/api/canteen/waste", methods=["POST"])
@role_required("staff", "manager")
def api_log_waste():
    """Save a shift or end-of-day food waste entry into waste_logs."""
    data = request.get_json(silent=True) or request.form

    try:
        menu_item_id = int(data.get("menu_item_id"))
        quantity_wasted = int(data.get("quantity_wasted"))
    except (TypeError, ValueError):
        return json_error("Please choose a dish and enter a whole number of portions wasted.", 400)

    if quantity_wasted <= 0 or quantity_wasted > 1000:
        return json_error("Quantity wasted must be between 1 and 1000 portions.", 400)

    reason = (data.get("reason") or "").strip().lower()
    if reason not in VALID_WASTE_REASONS:
        return json_error("Please select a valid waste reason (Overproduction, Spoilage, or Uncollected).", 400)

    raw_weight = str(data.get("weight_kg") or "").strip()
    weight_kg = None
    if raw_weight:
        try:
            weight_kg = round(float(raw_weight), 2)
        except ValueError:
            return json_error("Weight (kg) must be a valid number.", 400)
        if weight_kg < 0 or weight_kg > 500:
            return json_error("Weight (kg) must be between 0 and 500.", 400)

    notes = (data.get("notes") or "").strip()[:255] or None
    waste_date_str = (data.get("waste_date") or "").strip()
    waste_date = datetime.now().date()
    if waste_date_str:
        try:
            waste_date = datetime.strptime(waste_date_str, "%Y-%m-%d").date()
        except ValueError:
            return json_error("Invalid waste date format.", 400)

    dish = fetch_one("SELECT id, name FROM menu_items WHERE id = %s", (menu_item_id,))
    if dish is None:
        return json_error("Selected dish does not exist.", 404)

    new_id = execute(
        """
        INSERT INTO waste_logs
            (menu_item_id, waste_date, quantity_wasted, weight_kg, reason, notes, logged_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (menu_item_id, waste_date, quantity_wasted, weight_kg, reason, notes, g.user["id"]),
    )

    return jsonify({
        "ok": True,
        "waste_log_id": new_id,
        "message": f"Logged {quantity_wasted} portion(s) of {dish['name']} ({reason.capitalize()}).",
    })


# =========================================================
# Manager-Only APIs (Dish CRUD, 15-Min Slot Capacity, Staff)
# =========================================================

@canteen_bp.route("/api/canteen/menu/save", methods=["POST"])
@role_required("manager")
def api_manager_save_dish():
    """Create a new dish or edit an existing dish (Canteen Manager only)."""
    data = request.get_json(silent=True) or request.form
    dish_id = data.get("id")

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    category = (data.get("category") or "").strip()
    food_type = (data.get("food_type") or "veg").strip().lower()
    allergens = (data.get("allergens") or "").strip()[:120]

    if not name or len(name) > 100:
        return json_error("Please enter a dish name (up to 100 characters).", 400)
    if not description or len(description) > 255:
        return json_error("Please enter a short description (up to 255 characters).", 400)
    if not category or len(category) > 40:
        return json_error("Please choose a menu category.", 400)
    if food_type not in VALID_FOOD_TYPES:
        return json_error("Food type must be veg, non_veg, or egg.", 400)

    try:
        price = round(float(data.get("price")), 2)
        prep_time_minutes = int(data.get("prep_time_minutes", 10))
        prepared_batch_qty = int(data.get("prepared_batch_qty", 0))
        stock_qty = int(data.get("stock_qty", 0))
    except (TypeError, ValueError):
        return json_error("Price, prep time, batch qty, and stock qty must be valid numbers.", 400)

    if price < 0 or prep_time_minutes <= 0 or prepared_batch_qty < 0 or stock_qty < 0:
        return json_error("Prices and quantities cannot be negative.", 400)

    is_featured = 1 if str(data.get("is_featured", "")).lower() in ("1", "true", "on", "yes") else 0
    is_active = 0 if str(data.get("is_active", "1")).lower() in ("0", "false", "off", "no") else 1
    is_sold_out = 1 if stock_qty == 0 else 0

    if dish_id:
        execute(
            """
            UPDATE menu_items
            SET name = %s, description = %s, category = %s, price = %s,
                food_type = %s, allergens = %s, prep_time_minutes = %s,
                prepared_batch_qty = %s, stock_qty = %s, is_sold_out = %s,
                is_featured = %s, is_active = %s
            WHERE id = %s
            """,
            (
                name, description, category, price, food_type, allergens,
                prep_time_minutes, prepared_batch_qty, stock_qty, is_sold_out,
                is_featured, is_active, int(dish_id),
            ),
        )
        saved_id = int(dish_id)
        action_word = "updated"
    else:
        saved_id = execute(
            """
            INSERT INTO menu_items
                (name, description, category, price, food_type, allergens,
                 prep_time_minutes, prepared_batch_qty, stock_qty, is_sold_out,
                 is_featured, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                name, description, category, price, food_type, allergens,
                prep_time_minutes, prepared_batch_qty, stock_qty, is_sold_out,
                is_featured, is_active,
            ),
        )
        action_word = "created"

    if prepared_batch_qty > 0:
        execute(
            """
            INSERT INTO daily_batches (menu_item_id, batch_date, prepared_qty)
            VALUES (%s, CURDATE(), %s)
            ON DUPLICATE KEY UPDATE prepared_qty = VALUES(prepared_qty)
            """,
            (saved_id, prepared_batch_qty),
        )

    return jsonify({
        "ok": True,
        "dish_id": saved_id,
        "message": f"Dish '{name}' {action_word}.",
    })


@canteen_bp.route("/api/canteen/settings/slots", methods=["POST"])
@role_required("manager")
def api_manager_update_slots():
    """Update 15-minute pickup slot capacity for one slot or all of today's slots."""
    data = request.get_json(silent=True) or request.form
    try:
        capacity = int(data.get("capacity"))
    except (TypeError, ValueError):
        return json_error("Slot capacity must be a whole number.", 400)

    if capacity < 1 or capacity > 200:
        return json_error("Slot capacity must be between 1 and 200 orders per 15-minute window.", 400)

    slot_id = data.get("slot_id")
    if slot_id:
        execute(
            "UPDATE pickup_slots SET capacity = %s WHERE id = %s",
            (capacity, int(slot_id)),
        )
        return jsonify({"ok": True, "message": f"Slot capacity updated to {capacity} orders."})

    execute(
        "UPDATE pickup_slots SET capacity = %s WHERE slot_date = CURDATE()",
        (capacity,),
    )
    return jsonify({
        "ok": True,
        "message": f"All of today's 15-minute slots updated to capacity {capacity}.",
    })


@canteen_bp.route("/api/canteen/settings/staff", methods=["POST"])
@role_required("manager")
def api_manager_create_staff():
    """Create a Kitchen/Counter Staff or Manager account (Canteen Manager only)."""
    data = request.get_json(silent=True) or request.form
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    campus_id = (data.get("campus_id") or "").strip().upper() or None
    role = (data.get("role") or "staff").strip().lower()
    password = data.get("password") or ""

    if not full_name or len(full_name) > 100:
        return json_error("Please enter the staff member's full name.", 400)
    if not is_valid_email(email) or len(email) > 120:
        return json_error("Please enter a valid email address.", 400)
    if role not in ("staff", "manager"):
        return json_error("Role must be 'staff' or 'manager'.", 400)

    pw_error = check_password_strength(password)
    if pw_error:
        return json_error(pw_error, 400)

    try:
        new_user_id = execute(
            """
            INSERT INTO users (full_name, email, campus_id, password_hash, role, dietary_preference)
            VALUES (%s, %s, %s, %s, %s, 'any')
            """,
            (full_name, email, campus_id, generate_password_hash(password), role),
        )
    except IntegrityError:
        return json_error("An account with that email or campus ID already exists.", 409)

    return jsonify({
        "ok": True,
        "user_id": new_user_id,
        "message": f"Created {role} account for {full_name}.",
    })