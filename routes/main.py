"""
main.py - Shared account page and redirects from early placeholder URLs.

Students use routes/student.py and Canteen Staff/Managers use routes/canteen.py.
"""

from flask import Blueprint, redirect, render_template, url_for

from routes.access import login_required, role_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/account")
@login_required
def account():
    # Any logged-in user can open their profile summary
    return render_template("temp/account.html")


@main_bp.route("/staff/dashboard")
@role_required("staff", "manager")
def staff_dashboard():
    # Redirect legacy URL to the real Phase 6 Canteen Dashboard
    return redirect(url_for("canteen.dashboard"))


@main_bp.route("/manager/settings")
@role_required("manager")
def manager_settings():
    # Redirect legacy URL to the real Phase 6 Manager Settings screen
    return redirect(url_for("canteen.settings"))