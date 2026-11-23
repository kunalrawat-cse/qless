"""
access.py - Who is allowed where.

@login_required        -> must be logged in (any role)
@role_required("x")    -> must be logged in AND have one of the listed roles

Roles in the database: "student", "staff" (kitchen/counter), "manager".
"""

from functools import wraps

from flask import flash, g, jsonify, redirect, request, url_for


def home_url_for_role(role):
    # The page each role lands on after login. Change it here, nowhere else.
    if role == "student":
        return url_for("student.menu")
    if role in ("staff", "manager"):
        return url_for("canteen.dashboard")
    return url_for("main.account")


def send_to_login():
    # fetch() calls under /api/ get a JSON error instead of a login page
    if request.path.startswith("/api/"):
        return jsonify({"error": "Please log in first."}), 401

    flash("Please log in to continue.", "info")

    # Remember the page they wanted, so we can return them there after login
    next_url = request.full_path.rstrip("?") if request.method == "GET" else None
    return redirect(url_for("auth.login", next=next_url))


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return send_to_login()
        return view_function(*args, **kwargs)

    return wrapped_view


def role_required(*allowed_roles):
    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            if g.user is None:
                return send_to_login()

            # Logged in, but the wrong kind of account
            if g.user["role"] not in allowed_roles:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "You do not have permission."}), 403
                return render_forbidden_page()

            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


def render_forbidden_page():
    # Imported here to keep this file free of circular imports
    from flask import abort
    abort(403)