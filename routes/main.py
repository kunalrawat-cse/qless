"""
main.py - Temporary role pages for Phase 3.

They exist only to prove that login and role protection work.
Phase 5 (student) and Phase 6 (staff) replace them with the real screens.
"""

from flask import Blueprint, g, redirect, render_template

from db import fetch_all, fetch_one
from routes.access import home_url_for_role, login_required, role_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    # Logged-in users go to their own home, everyone else goes to login.
    # Phase 4 replaces this with the public Home page.
    if g.user:
        return redirect(home_url_for_role(g.user["role"]))
    return redirect("/login")


@main_bp.route("/account")
@login_required
def account():
    # Any logged-in user can open this page
    return render_template("temp/account.html")


@main_bp.route("/menu")
@role_required("student")
def student_menu():
    # Students only
    menu_items = fetch_all(
        """
        SELECT name, category, price, food_type, stock_qty, is_sold_out
        FROM menu_items
        WHERE is_active = 1
        ORDER BY category, name
        """
    )
    return render_template("temp/student_home.html", menu_items=menu_items)


@main_bp.route("/staff/dashboard")
@role_required("staff", "manager")
def staff_dashboard():
    # Staff and managers (managers can do everything staff can)
    orders_today = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM orders
        JOIN pickup_slots ON pickup_slots.id = orders.slot_id
        WHERE pickup_slots.slot_date = CURDATE()
        """
    )
    return render_template("temp/staff_home.html", orders_today=orders_today["total"])


@main_bp.route("/manager/settings")
@role_required("manager")
def manager_settings():
    # Canteen managers only
    return render_template("temp/manager_only.html")