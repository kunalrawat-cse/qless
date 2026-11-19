"""
auth.py - Signup, login, logout and password recovery.

Passwords are never stored. We store a one-way "hash" and compare hashes
when someone logs in, so even we cannot read a password.
"""

import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from pymysql.err import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from db import execute, fetch_one
from routes.access import home_url_for_role

auth_bp = Blueprint("auth", __name__)

VALID_DIETARY_CHOICES = ("any", "veg", "non_veg", "egg")


# =========================================================
# Small helper functions
# =========================================================

def is_valid_email(email):
    # Simple shape check: something@something.something
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def check_password_strength(password):
    # Returns an error message, or None if the password is fine
    if len(password) < Config.MIN_PASSWORD_LENGTH:
        return f"Password must be at least {Config.MIN_PASSWORD_LENGTH} characters long."

    if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        return "Password must contain at least one letter and one number."

    return None


def get_safe_next_url():
    # After login we may send the user back to the page they wanted.
    # Only allow paths inside our own site, never other websites.
    next_url = request.args.get("next", "")

    is_local_path = next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url
    return next_url if is_local_path else None


def validate_signup_form(full_name, email, campus_id, dietary_preference, password, confirm_password):
    # Collect every problem so the student can fix them all at once
    errors = []

    if not full_name or len(full_name) > 100:
        errors.append("Please enter your full name (up to 100 characters).")

    if not is_valid_email(email) or len(email) > 120:
        errors.append("Please enter a valid email address.")

    if not campus_id or len(campus_id) > 30:
        errors.append("Please enter your campus ID (up to 30 characters).")

    if dietary_preference not in VALID_DIETARY_CHOICES:
        errors.append("Please choose a valid dietary preference.")

    password_problem = check_password_strength(password)
    if password_problem:
        errors.append(password_problem)

    if password != confirm_password:
        errors.append("The two passwords do not match.")

    return errors


# =========================================================
# Signup
# =========================================================

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user:
        return redirect(home_url_for_role(g.user["role"]))

    if request.method == "GET":
        return render_template("auth/signup.html", form={})

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    campus_id = request.form.get("campus_id", "").strip().upper()
    dietary_preference = request.form.get("dietary_preference", "any")
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    errors = validate_signup_form(
        full_name, email, campus_id, dietary_preference, password, confirm_password
    )

    # Only check the database if the form itself looks fine
    if not errors:
        if fetch_one("SELECT id FROM users WHERE email = %s", (email,)):
            errors.append("An account with that email already exists.")
        if fetch_one("SELECT id FROM users WHERE campus_id = %s", (campus_id,)):
            errors.append("An account with that campus ID already exists.")

    if errors:
        for error_message in errors:
            flash(error_message, "error")
        return render_template("auth/signup.html", form=request.form)

    try:
        # Public signup can only ever create STUDENT accounts.
        # Staff accounts are created by the canteen manager later.
        execute(
            """
            INSERT INTO users (full_name, email, campus_id, password_hash, role, dietary_preference)
            VALUES (%s, %s, %s, %s, 'student', %s)
            """,
            (full_name, email, campus_id, generate_password_hash(password), dietary_preference),
        )
    except IntegrityError:
        # Two people signing up at the same moment could slip past the checks above
        flash("An account with that email or campus ID already exists.", "error")
        return render_template("auth/signup.html", form=request.form)

    flash("Account created. Please log in.", "success")
    return redirect(url_for("auth.login"))


# =========================================================
# Login and logout
# =========================================================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(home_url_for_role(g.user["role"]))

    if request.method == "GET":
        return render_template("auth/login.html", email="")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = fetch_one(
        "SELECT id, role, password_hash FROM users WHERE email = %s",
        (email,),
    )

    # Same message for "no such email" and "wrong password",
    # so nobody can use the form to discover which emails are registered
    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Incorrect email or password.", "error")
        return render_template("auth/login.html", email=email)

    # Start a fresh session on login (blocks "session fixation" attacks)
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True

    return redirect(get_safe_next_url() or home_url_for_role(user["role"]))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # POST only, so another website cannot log people out with a simple link
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


# =========================================================
# Password recovery (6-digit code)
# =========================================================

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html")

    email = request.form.get("email", "").strip().lower()
    user = fetch_one("SELECT id FROM users WHERE email = %s", (email,))

    if user:
        otp_code = f"{secrets.randbelow(1000000):06d}"
        expires_at = datetime.now() + timedelta(minutes=Config.RESET_OTP_MINUTES)

        # Cancel any older unused codes, then save the new one
        execute(
            "UPDATE password_resets SET is_used = 1 WHERE user_id = %s AND is_used = 0",
            (user["id"],),
        )
        execute(
            "INSERT INTO password_resets (user_id, otp_code, expires_at) VALUES (%s, %s, %s)",
            (user["id"], otp_code, expires_at),
        )

        # No email server in the MVP, so the code goes to the terminal.
        # A real email (SMTP) sender is a Phase 2 upgrade.
        print(f"[PASSWORD RESET] Code for {email}: {otp_code}")

        if Config.SHOW_RESET_OTP_ON_SCREEN:
            flash(f"Demo mode: your reset code is {otp_code}", "info")

    # Same reply whether or not the email exists
    session["reset_email"] = email
    flash("If that email is registered, a 6-digit code has been sent.", "success")
    return redirect(url_for("auth.reset_password"))


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    email = session.get("reset_email")

    if not email:
        flash("Please enter your email first.", "info")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "GET":
        return render_template("auth/reset_password.html", email=email)

    otp_code = request.form.get("otp_code", "").strip()
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    password_problem = check_password_strength(new_password)
    if password_problem:
        flash(password_problem, "error")
        return render_template("auth/reset_password.html", email=email)

    if new_password != confirm_password:
        flash("The two passwords do not match.", "error")
        return render_template("auth/reset_password.html", email=email)

    user = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
    reset_row = None

    if user:
        reset_row = fetch_one(
            """
            SELECT id, otp_code, expires_at FROM password_resets
            WHERE user_id = %s AND is_used = 0
            ORDER BY id DESC LIMIT 1
            """,
            (user["id"],),
        )

    code_is_valid = (
        reset_row is not None
        and reset_row["expires_at"] > datetime.now()
        and secrets.compare_digest(reset_row["otp_code"], otp_code)
    )

    if not code_is_valid:
        flash("That code is invalid or has expired.", "error")
        return render_template("auth/reset_password.html", email=email)

    execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (generate_password_hash(new_password), user["id"]),
    )
    execute("UPDATE password_resets SET is_used = 1 WHERE id = %s", (reset_row["id"],))

    session.pop("reset_email", None)
    flash("Password changed. Please log in with your new password.", "success")
    return redirect(url_for("auth.login"))