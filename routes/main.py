"""
main.py - Account & Profile settings for students, kitchen staff and managers.

Allows any logged-in user to view their profile, update their dietary
preference (students), or change their password securely.
"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, fetch_one
from routes.access import home_url_for_role, login_required, role_required
from routes.auth import VALID_DIETARY_CHOICES, check_password_strength

main_bp = Blueprint("main", __name__)


@main_bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        action = request.form.get("action", "profile").strip()

        if action == "profile":
            full_name = request.form.get("full_name", "").strip()
            dietary_preference = request.form.get("dietary_preference", g.user["dietary_preference"])

            if not full_name or len(full_name) > 100:
                flash("Please enter your full name (up to 100 characters).", "error")
                return redirect(url_for("main.account"))

            if dietary_preference not in VALID_DIETARY_CHOICES:
                dietary_preference = "any"

            execute(
                "UPDATE users SET full_name = %s, dietary_preference = %s WHERE id = %s",
                (full_name, dietary_preference, g.user["id"]),
            )
            flash("Your profile preferences have been saved.", "success")
            return redirect(url_for("main.account"))

        if action == "password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            user_row = fetch_one(
                "SELECT password_hash FROM users WHERE id = %s",
                (g.user["id"],),
            )

            if not user_row or not check_password_hash(user_row["password_hash"], current_password):
                flash("Your current password was not correct.", "error")
                return redirect(url_for("main.account"))

            pw_problem = check_password_strength(new_password)
            if pw_problem:
                flash(pw_problem, "error")
                return redirect(url_for("main.account"))

            if new_password != confirm_password:
                flash("The two new passwords do not match.", "error")
                return redirect(url_for("main.account"))

            execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (generate_password_hash(new_password), g.user["id"]),
            )
            flash("Your password has been updated.", "success")
            return redirect(url_for("main.account"))

    return render_template(
        "temp/account.html",
        home_url=home_url_for_role(g.user["role"]),
    )


@main_bp.route("/staff/dashboard")
@role_required("staff", "manager")
def staff_dashboard():
    return redirect(url_for("canteen.dashboard"))


@main_bp.route("/manager/settings")
@role_required("manager")
def manager_settings():
    return redirect(url_for("canteen.settings"))
