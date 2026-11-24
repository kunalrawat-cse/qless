"""
reports.py - Post-Rush Demand & Food-Waste Analytics Engine (Phase 7).

Uses MySQL + Pandas + NumPy to compute:
  - 4 Post-Rush Executive KPIs (Revenue, Portions Sold, Portions/Kg Wasted, Waste Rate %, Avg Rating)
  - All 8 Post-Rush Operational Charts for Chart.js:
      1. Orders by 15-Minute Pickup Slot
      2. Top-Selling Dishes (Portions & Revenue)
      3. Prepared vs. Sold by Item (from daily_batches / menu_items vs. order_items)
      4. Daily Waste Trend (Portions & Kg over date range)
      5. Waste by Dish
      6. Waste Reason Breakdown (Overproduction, Spoilage, Uncollected)
      7. Slot Utilization Heatmap (Load % across 15-minute windows)
      8. Category Revenue vs. Waste Comparison
  - Historical Orders & Student Feedback table
  - CSV exports (Orders CSV & Waste Logs CSV via Pandas)
  - Static 2x2 PNG Sustainability & Operations Report chart via Matplotlib (headless Agg backend)
"""

import io
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")  # Headless mode so Matplotlib never opens a desktop GUI window in Flask
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import Config
from db import fetch_all
from routes.order_logic import calculate_slot_load, format_clock


def resolve_date_window(days_param):
    """Turn ?days=1|7|14|30 into (start_date, end_date, days_int)."""
    try:
        days = int(days_param)
    except (TypeError, ValueError):
        days = 14

    if days not in (1, 7, 14, 30):
        days = 14

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date, days


def build_analytics_payload(days_param=14):
    """Run SQL queries and aggregate with Pandas & NumPy into a JSON-ready dictionary."""
    start_date, end_date, days = resolve_date_window(days_param)

    # ---- 1. Fetch raw rows from MySQL for the selected date range ----
    order_rows = fetch_all(
        """
        SELECT o.id AS order_id, o.status, o.payment_method, o.payment_status,
               o.total_amount, o.pickup_otp, o.uncollected_flag, o.created_at,
               s.id AS slot_id, s.slot_date, s.start_time, s.end_time, s.capacity,
               u.full_name AS student_name, u.campus_id,
               f.rating, f.comment
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN users u ON u.id = o.student_id
        LEFT JOIN feedback f ON f.order_id = o.id
        WHERE s.slot_date BETWEEN %s AND %s
        ORDER BY s.slot_date DESC, s.start_time DESC, o.id DESC
        """,
        (start_date, end_date),
    )

    item_sales_rows = fetch_all(
        """
        SELECT oi.order_id, oi.menu_item_id, oi.quantity, oi.unit_price,
               m.name AS dish_name, m.category, m.food_type,
               s.slot_date, o.status
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN menu_items m ON m.id = oi.menu_item_id
        WHERE s.slot_date BETWEEN %s AND %s
          AND o.status <> 'cancelled'
        """,
        (start_date, end_date),
    )

    batch_rows = fetch_all(
        """
        SELECT m.id AS menu_item_id, m.name AS dish_name, m.category,
               m.prepared_batch_qty AS today_batch_qty,
               COALESCE(SUM(db.prepared_qty), 0) AS history_prepared_qty
        FROM menu_items m
        LEFT JOIN daily_batches db
               ON db.menu_item_id = m.id
              AND db.batch_date BETWEEN %s AND %s
        WHERE m.is_active = 1
        GROUP BY m.id, m.name, m.category, m.prepared_batch_qty
        ORDER BY m.name ASC
        """,
        (start_date, end_date),
    )

    waste_rows = fetch_all(
        """
        SELECT w.id, w.menu_item_id, w.waste_date, w.quantity_wasted,
               COALESCE(w.weight_kg, 0) AS weight_kg, w.reason, w.notes,
               m.name AS dish_name, m.category
        FROM waste_logs w
        JOIN menu_items m ON m.id = w.menu_item_id
        WHERE w.waste_date BETWEEN %s AND %s
        ORDER BY w.waste_date ASC, w.id ASC
        """,
        (start_date, end_date),
    )

    slot_rows = fetch_all(
        """
        SELECT s.id, s.slot_date, s.start_time, s.end_time, s.capacity,
               COUNT(o.id) AS booked
        FROM pickup_slots s
        LEFT JOIN orders o ON o.slot_id = s.id AND o.status <> 'cancelled'
        WHERE s.slot_date BETWEEN %s AND %s
        GROUP BY s.id, s.slot_date, s.start_time, s.end_time, s.capacity
        ORDER BY s.start_time ASC
        """,
        (start_date, end_date),
    )

    # ---- 2. Convert to Pandas DataFrames for fast aggregation ----
    df_orders = pd.DataFrame(order_rows) if order_rows else pd.DataFrame()
    df_sales = pd.DataFrame(item_sales_rows) if item_sales_rows else pd.DataFrame()
    df_waste = pd.DataFrame(waste_rows) if waste_rows else pd.DataFrame()
    df_slots = pd.DataFrame(slot_rows) if slot_rows else pd.DataFrame()

    # ---- 3. Compute Post-Rush Executive KPIs ----
    if not df_orders.empty:
        valid_orders = df_orders[df_orders["status"] != "cancelled"]
        total_revenue = float(valid_orders["total_amount"].astype(float).sum())
        total_orders = int(len(valid_orders))
        collected_orders = int((valid_orders["status"] == "collected").sum())
        ratings = valid_orders["rating"].dropna().astype(float)
        avg_rating = round(float(ratings.mean()), 2) if not ratings.empty else 0.0
        rating_count = int(len(ratings))
    else:
        total_revenue = 0.0
        total_orders = 0
        collected_orders = 0
        avg_rating = 0.0
        rating_count = 0

    total_portions_sold = int(df_sales["quantity"].astype(int).sum()) if not df_sales.empty else 0
    total_portions_wasted = int(df_waste["quantity_wasted"].astype(int).sum()) if not df_waste.empty else 0
    total_waste_kg = round(float(df_waste["weight_kg"].astype(float).sum()), 2) if not df_waste.empty else 0.0

    total_prepared_est = total_portions_sold + total_portions_wasted
    waste_rate_percent = (
        round(total_portions_wasted * 100.0 / total_prepared_est, 1)
        if total_prepared_est > 0
        else 0.0
    )

    # ---- Chart 1 & Chart 7: Orders by 15-Minute Pickup Slot + Slot Utilization Heatmap ----
    slot_labels = []
    slot_order_counts = []
    slot_heatmap_cells = []

    if not df_slots.empty:
        df_slots["slot_label"] = df_slots.apply(
            lambda r: f"{format_clock(r['start_time'])} - {format_clock(r['end_time'])}",
            axis=1,
        )
        df_slots["booked"] = df_slots["booked"].astype(int)
        df_slots["capacity"] = df_slots["capacity"].astype(int)

        grouped_slots = (
            df_slots.groupby(["start_time", "slot_label"], as_index=False)
            .agg(total_booked=("booked", "sum"), total_capacity=("capacity", "sum"), days_count=("id", "count"))
            .sort_values("start_time")
        )

        active_slots = grouped_slots[grouped_slots["total_booked"] > 0]
        if active_slots.empty:
            active_slots = grouped_slots.head(12)

        for _, s_row in active_slots.iterrows():
            booked_sum = int(s_row["total_booked"])
            cap_sum = max(1, int(s_row["total_capacity"]))
            avg_load = calculate_slot_load(booked_sum, cap_sum)

            slot_labels.append(s_row["slot_label"])
            slot_order_counts.append(booked_sum)

            tone = "low"
            if avg_load >= 80:
                tone = "peak"
            elif avg_load >= 45:
                tone = "medium"

            slot_heatmap_cells.append({
                "slot_label": s_row["slot_label"],
                "booked": booked_sum,
                "capacity": cap_sum,
                "load_percent": avg_load,
                "tone": tone,
            })

    # ---- Chart 2: Top-Selling Dishes ----
    top_dishes_labels = []
    top_dishes_portions = []
    top_dishes_revenue = []

    if not df_sales.empty:
        df_sales["quantity"] = df_sales["quantity"].astype(int)
        df_sales["line_revenue"] = df_sales["quantity"] * df_sales["unit_price"].astype(float)
        grouped_dishes = (
            df_sales.groupby("dish_name", as_index=False)
            .agg(portions=("quantity", "sum"), revenue=("line_revenue", "sum"))
            .sort_values(["portions", "revenue"], ascending=[False, False])
            .head(8)
        )
        top_dishes_labels = grouped_dishes["dish_name"].tolist()
        top_dishes_portions = [int(x) for x in grouped_dishes["portions"].tolist()]
        top_dishes_revenue = [round(float(x), 2) for x in grouped_dishes["revenue"].tolist()]

    # ---- Chart 3: Prepared vs. Sold by Item ----
    sold_by_item = {}
    if not df_sales.empty:
        for item_id, group in df_sales.groupby("menu_item_id"):
            sold_by_item[int(item_id)] = int(group["quantity"].sum())

    wasted_by_item = {}
    if not df_waste.empty:
        for item_id, group in df_waste.groupby("menu_item_id"):
            wasted_by_item[int(item_id)] = int(group["quantity_wasted"].astype(int).sum())

    prep_vs_sold_rows = []
    for b_row in batch_rows:
        item_id = int(b_row["menu_item_id"])
        sold_qty = sold_by_item.get(item_id, 0)
        wasted_qty = wasted_by_item.get(item_id, 0)
        hist_prep = int(b_row["history_prepared_qty"] or 0)
        today_prep = int(b_row["today_batch_qty"] or 0)

        prepared_qty = max(hist_prep, today_prep if days == 1 else 0, sold_qty + wasted_qty)
        if prepared_qty > 0 or sold_qty > 0:
            prep_vs_sold_rows.append({
                "dish_name": b_row["dish_name"],
                "prepared": prepared_qty,
                "sold": sold_qty,
                "wasted": wasted_qty,
            })

    prep_vs_sold_rows.sort(key=lambda r: (-r["prepared"], -r["sold"], r["dish_name"]))
    prep_vs_sold_top = prep_vs_sold_rows[:8]

    # ---- Chart 4: Daily Waste Trend (Portions & Kg across every day in window) ----
    date_index = [start_date + timedelta(days=i) for i in range(days)]
    waste_by_day_portions = {d: 0 for d in date_index}
    waste_by_day_kg = {d: 0.0 for d in date_index}

    if not df_waste.empty:
        for _, w_row in df_waste.iterrows():
            w_date = w_row["waste_date"]
            if isinstance(w_date, datetime):
                w_date = w_date.date()
            if w_date in waste_by_day_portions:
                waste_by_day_portions[w_date] += int(w_row["quantity_wasted"])
                waste_by_day_kg[w_date] = round(
                    waste_by_day_kg[w_date] + float(w_row["weight_kg"] or 0), 2
                )

    daily_waste_labels = [d.strftime("%d %b") for d in date_index]
    daily_waste_portions = [waste_by_day_portions[d] for d in date_index]
    daily_waste_kg = [waste_by_day_kg[d] for d in date_index]

    # ---- Chart 5: Waste by Dish ----
    waste_dish_labels = []
    waste_dish_portions = []

    if not df_waste.empty:
        grouped_waste_dish = (
            df_waste.groupby("dish_name", as_index=False)
            .agg(portions=("quantity_wasted", "sum"))
            .sort_values("portions", ascending=False)
            .head(8)
        )
        waste_dish_labels = grouped_waste_dish["dish_name"].tolist()
        waste_dish_portions = [int(x) for x in grouped_waste_dish["portions"].tolist()]

    # ---- Chart 6: Waste Reason Breakdown (Overproduction, Spoilage, Uncollected) ----
    reason_totals = {"overproduction": 0, "spoilage": 0, "uncollected": 0}
    if not df_waste.empty:
        for _, w_row in df_waste.iterrows():
            r_key = str(w_row["reason"]).lower()
            if r_key in reason_totals:
                reason_totals[r_key] += int(w_row["quantity_wasted"])

    # ---- Chart 8: Category Performance (Portions Sold vs. Portions Wasted by Category) ----
    categories = list(Config.MENU_CATEGORY_ORDER)
    cat_sold = {c: 0 for c in categories}
    cat_wasted = {c: 0 for c in categories}

    if not df_sales.empty:
        for cat_name, grp in df_sales.groupby("category"):
            if cat_name not in cat_sold:
                cat_sold[cat_name] = 0
                cat_wasted[cat_name] = 0
            cat_sold[cat_name] += int(grp["quantity"].sum())

    if not df_waste.empty:
        for cat_name, grp in df_waste.groupby("category"):
            if cat_name not in cat_wasted:
                cat_sold[cat_name] = 0
                cat_wasted[cat_name] = 0
            cat_wasted[cat_name] += int(grp["quantity_wasted"].astype(int).sum())

    category_labels = list(cat_sold.keys())
    category_sold_values = [cat_sold[c] for c in category_labels]
    category_waste_values = [cat_wasted.get(c, 0) for c in category_labels]

    # ---- Historical Orders & Feedback Table (up to 40 most recent orders in window) ----
    historical_orders = []
    for row in order_rows[:40]:
        slot_date_val = row["slot_date"]
        date_str = (
            slot_date_val.strftime("%d %b %Y")
            if hasattr(slot_date_val, "strftime")
            else str(slot_date_val)
        )
        historical_orders.append({
            "id": row["order_id"],
            "student_name": row["student_name"],
            "campus_id": row["campus_id"] or "—",
            "date_label": date_str,
            "slot_label": f"{format_clock(row['start_time'])} - {format_clock(row['end_time'])}",
            "status": row["status"],
            "payment_method_label": "UPI Paid" if row["payment_method"] == "mock_upi" else "Counter Pay",
            "total_amount": float(row["total_amount"]),
            "pickup_otp": row["pickup_otp"],
            "rating": int(row["rating"]) if row.get("rating") is not None else None,
            "comment": row.get("comment") or "",
        })

    return {
        "days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "window_label": f"{start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}",
        "kpis": {
            "total_revenue": round(total_revenue, 2),
            "total_orders": total_orders,
            "collected_orders": collected_orders,
            "total_portions_sold": total_portions_sold,
            "total_portions_wasted": total_portions_wasted,
            "total_waste_kg": total_waste_kg,
            "waste_rate_percent": waste_rate_percent,
            "avg_rating": avg_rating,
            "rating_count": rating_count,
        },
        "charts": {
            "orders_by_slot": {
                "labels": slot_labels,
                "orders": slot_order_counts,
            },
            "top_dishes": {
                "labels": top_dishes_labels,
                "portions": top_dishes_portions,
                "revenue": top_dishes_revenue,
            },
            "prepared_vs_sold": {
                "labels": [r["dish_name"] for r in prep_vs_sold_top],
                "prepared": [r["prepared"] for r in prep_vs_sold_top],
                "sold": [r["sold"] for r in prep_vs_sold_top],
                "wasted": [r["wasted"] for r in prep_vs_sold_top],
            },
            "daily_waste_trend": {
                "labels": daily_waste_labels,
                "portions": daily_waste_portions,
                "weight_kg": daily_waste_kg,
            },
            "waste_by_dish": {
                "labels": waste_dish_labels,
                "portions": waste_dish_portions,
            },
            "waste_reasons": {
                "labels": ["Overproduction", "Spoilage", "Uncollected"],
                "portions": [
                    reason_totals["overproduction"],
                    reason_totals["spoilage"],
                    reason_totals["uncollected"],
                ],
            },
            "slot_heatmap": slot_heatmap_cells,
            "category_performance": {
                "labels": category_labels,
                "sold": category_sold_values,
                "wasted": category_waste_values,
            },
        },
        "historical_orders": historical_orders,
    }


# =========================================================
# CSV & Matplotlib PNG Report Exports
# =========================================================

def export_orders_csv(days_param=14):
    """Export historical orders in the date window as a clean UTF-8 CSV string using Pandas."""
    start_date, end_date, _ = resolve_date_window(days_param)
    rows = fetch_all(
        """
        SELECT o.id AS order_id, s.slot_date, s.start_time, s.end_time,
               u.full_name AS student_name, u.campus_id,
               o.status, o.payment_method, o.payment_status,
               o.total_amount, o.pickup_otp,
               GROUP_CONCAT(CONCAT(oi.quantity, 'x ', m.name) ORDER BY m.name SEPARATOR '; ') AS items_ordered,
               f.rating AS feedback_rating, f.comment AS feedback_comment,
               o.created_at
        FROM orders o
        JOIN pickup_slots s ON s.id = o.slot_id
        JOIN users u ON u.id = o.student_id
        LEFT JOIN order_items oi ON oi.order_id = o.id
        LEFT JOIN menu_items m ON m.id = oi.menu_item_id
        LEFT JOIN feedback f ON f.order_id = o.id
        WHERE s.slot_date BETWEEN %s AND %s
        GROUP BY o.id, s.slot_date, s.start_time, s.end_time,
                 u.full_name, u.campus_id, o.status, o.payment_method,
                 o.payment_status, o.total_amount, o.pickup_otp,
                 f.rating, f.comment, o.created_at
        ORDER BY s.slot_date DESC, s.start_time DESC, o.id DESC
        """,
        (start_date, end_date),
    )

    if not rows:
        df = pd.DataFrame(columns=[
            "order_id", "slot_date", "pickup_slot", "student_name", "campus_id",
            "status", "payment_method", "payment_status", "total_amount_inr",
            "pickup_otp", "items_ordered", "feedback_rating", "feedback_comment",
        ])
    else:
        for r in rows:
            r["pickup_slot"] = f"{format_clock(r.pop('start_time'))} - {format_clock(r.pop('end_time'))}"
            r["total_amount_inr"] = float(r.pop("total_amount"))
        df = pd.DataFrame(rows)

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()


def export_waste_csv(days_param=14):
    """Export food waste logs in the date window as a clean UTF-8 CSV string using Pandas."""
    start_date, end_date, _ = resolve_date_window(days_param)
    rows = fetch_all(
        """
        SELECT w.id AS waste_log_id, w.waste_date, m.name AS dish_name,
               m.category, m.food_type, w.quantity_wasted AS portions_wasted,
               w.weight_kg, w.reason, w.notes,
               u.full_name AS logged_by_staff, w.created_at
        FROM waste_logs w
        JOIN menu_items m ON m.id = w.menu_item_id
        LEFT JOIN users u ON u.id = w.logged_by
        WHERE w.waste_date BETWEEN %s AND %s
        ORDER BY w.waste_date DESC, w.id DESC
        """,
        (start_date, end_date),
    )

    if not rows:
        df = pd.DataFrame(columns=[
            "waste_log_id", "waste_date", "dish_name", "category", "food_type",
            "portions_wasted", "weight_kg", "reason", "notes", "logged_by_staff",
        ])
    else:
        df = pd.DataFrame(rows)

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()


def generate_matplotlib_report_png(days_param=14):
    """Render a 2x2 Fresh Harvest Tech executive report figure using Matplotlib + NumPy
    and return the PNG bytes ready for browser download."""
    payload = build_analytics_payload(days_param)
    charts = payload["charts"]
    kpis = payload["kpis"]

    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), dpi=130)
    fig.patch.set_facecolor("#FAFDFB")

    fig.suptitle(
        f"Qless Campus Canteen — Demand & Food-Waste Report ({payload['window_label']})",
        fontsize=15,
        fontweight="bold",
        color="#064E3B",
        y=0.97,
    )
    fig.text(
        0.5,
        0.925,
        (
            f"Revenue: INR {kpis['total_revenue']:,.0f}   |   "
            f"Orders: {kpis['total_orders']}   |   "
            f"Portions Sold: {kpis['total_portions_sold']}   |   "
            f"Waste: {kpis['total_portions_wasted']} portions ({kpis['total_waste_kg']:.2f} kg, {kpis['waste_rate_percent']}%)"
        ),
        ha="center",
        fontsize=10.5,
        color="#4B5563",
    )

    # Panel 1 (Top-Left): Orders by 15-Minute Pickup Slot
    ax1 = axes[0, 0]
    ax1.set_facecolor("#FFFFFF")
    slot_labels = charts["orders_by_slot"]["labels"][:10]
    slot_vals = charts["orders_by_slot"]["orders"][:10]
    if slot_labels:
        x_pos = np.arange(len(slot_labels))
        ax1.bar(x_pos, slot_vals, color="#064E3B", edgecolor="#16A34A", width=0.6)
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels([lbl.split(" - ")[0] for lbl in slot_labels], rotation=35, ha="right", fontsize=8)
    else:
        ax1.text(0.5, 0.5, "No slot orders in window", ha="center", va="center", color="#4B5563")
    ax1.set_title("1. Orders by 15-Minute Pickup Slot", fontsize=11, fontweight="bold", color="#064E3B")
    ax1.set_ylabel("Orders", fontsize=9, color="#4B5563")
    ax1.grid(axis="y", linestyle="--", alpha=0.35)

    # Panel 2 (Top-Right): Prepared vs. Sold by Item
    ax2 = axes[0, 1]
    ax2.set_facecolor("#FFFFFF")
    pvs = charts["prepared_vs_sold"]
    pvs_labels = pvs["labels"][:6]
    if pvs_labels:
        x_pos = np.arange(len(pvs_labels))
        width = 0.36
        ax2.bar(x_pos - width / 2, pvs["prepared"][:6], width=width, label="Prepared", color="#D97706")
        ax2.bar(x_pos + width / 2, pvs["sold"][:6], width=width, label="Sold", color="#16A34A")
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels([name[:14] for name in pvs_labels], rotation=25, ha="right", fontsize=8)
        ax2.legend(frameon=False, fontsize=8.5)
    else:
        ax2.text(0.5, 0.5, "No batch/sales data in window", ha="center", va="center", color="#4B5563")
    ax2.set_title("2. Prepared vs. Sold by Dish (Portions)", fontsize=11, fontweight="bold", color="#064E3B")
    ax2.set_ylabel("Portions", fontsize=9, color="#4B5563")
    ax2.grid(axis="y", linestyle="--", alpha=0.35)

    # Panel 3 (Bottom-Left): Daily Waste Trend
    ax3 = axes[1, 0]
    ax3.set_facecolor("#FFFFFF")
    trend_labels = charts["daily_waste_trend"]["labels"]
    trend_portions = charts["daily_waste_trend"]["portions"]
    if trend_labels:
        x_pos = np.arange(len(trend_labels))
        ax3.plot(x_pos, trend_portions, marker="o", color="#F97316", linewidth=2.2, label="Portions Wasted")
        ax3.fill_between(x_pos, trend_portions, color="#FEF3C7", alpha=0.55)
        step = max(1, len(trend_labels) // 8)
        ax3.set_xticks(x_pos[::step])
        ax3.set_xticklabels(trend_labels[::step], rotation=25, ha="right", fontsize=8)
    else:
        ax3.text(0.5, 0.5, "No daily waste logged", ha="center", va="center", color="#4B5563")
    ax3.set_title("3. Daily Food-Waste Trend (Portions)", fontsize=11, fontweight="bold", color="#064E3B")
    ax3.set_ylabel("Portions Wasted", fontsize=9, color="#4B5563")
    ax3.grid(axis="y", linestyle="--", alpha=0.35)

    # Panel 4 (Bottom-Right): Waste Reason Breakdown
    ax4 = axes[1, 1]
    ax4.set_facecolor("#FFFFFF")
    r_labels = charts["waste_reasons"]["labels"]
    r_vals = charts["waste_reasons"]["portions"]
    if sum(r_vals) > 0:
        colors = ["#D97706", "#DC2626", "#F97316"]
        ax4.pie(
            r_vals,
            labels=r_labels,
            autopct="%1.0f%%",
            startangle=135,
            colors=colors,
            textprops={"fontsize": 9, "color": "#111827"},
        )
    else:
        ax4.text(0.5, 0.5, "Zero food waste logged in window", ha="center", va="center", color="#15803D")
    ax4.set_title("4. Waste Reason Breakdown", fontsize=11, fontweight="bold", color="#064E3B")

    plt.tight_layout(rect=[0.02, 0.02, 0.98, 0.90])

    png_buffer = io.BytesIO()
    fig.savefig(png_buffer, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    png_buffer.seek(0)
    return png_buffer.getvalue()