"""
main.py - Temporary role pages.

They exist only to prove that login and role protection work.
Phase 6 (staff) replaces them with the real screens. Students now use routes/student.py.
(The public Home page at "/" now lives in routes/public.py.)
"""

from flask import Blueprint, render_template

from db import fetch_one
from routes.access import login_required, role_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/account")
@login_required
def account():
    # Any logged-in user can open this page
    return render_template("temp/account.html")


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