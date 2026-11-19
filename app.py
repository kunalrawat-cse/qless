"""
app.py - Entry point. Run this file to start the Qless web server.

What happens on every request:
  1. load_logged_in_user  -> finds out who is logged in (g.user)
  2. verify_csrf_token    -> rejects forged form submissions
  3. the page's own function runs
  4. stop_caching...      -> logged-in pages are never cached by the browser
"""

from flask import Flask, g, jsonify, render_template, request, session

from config import Config
from db import fetch_one
from routes.access import role_required
from routes.auth import auth_bp
from routes.main import main_bp
from routes.public import public_bp
from routes.security import check_csrf_token, csrf_token
from routes.student import student_bp

# Create the Flask app and load all settings from config.py
app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(public_bp)
app.register_blueprint(student_bp)


@app.before_request
def load_logged_in_user():
    # g.user is the current user's row from the database, or None
    g.user = None

    # Images, CSS and JS files do not need a database lookup
    if request.endpoint == "static":
        return

    user_id = session.get("user_id")
    if user_id is None:
        return

    user = fetch_one(
        "SELECT id, full_name, email, role, dietary_preference FROM users WHERE id = %s",
        (user_id,),
    )

    # The account was deleted while logged in, so end the session
    if user is None:
        session.clear()
        return

    g.user = user


@app.before_request
def verify_csrf_token():
    check_csrf_token()


@app.context_processor
def make_helpers_available_in_templates():
    # Lets every template use {{ current_user }} and {{ csrf_token() }}
    return {"current_user": g.get("user"), "csrf_token": csrf_token}


@app.after_request
def stop_caching_logged_in_pages(response):
    # After logout, the Back button must not show a cached private page
    if g.get("user") is not None:
        response.headers["Cache-Control"] = "no-store"
    return response


# ---------- Friendly error pages ----------

ERROR_MESSAGES = {
    400: ("Request could not be verified", "Your session may have expired. Go back, refresh the page and try again."),
    403: ("Access denied", "Your account does not have permission to open this page."),
    404: ("Page not found", "We could not find the page you were looking for."),
    405: ("Method not allowed", "That action is not allowed on this page."),
    500: ("Something went wrong", "Please try again. If it keeps happening, tell the canteen manager."),
}


def show_error_page(error):
    code = getattr(error, "code", 500)
    title, message = ERROR_MESSAGES.get(code, ERROR_MESSAGES[500])
    return render_template("errors/error.html", code=code, title=title, message=message), code


for error_code in ERROR_MESSAGES:
    app.register_error_handler(error_code, show_error_page)


# ---------- Utility pages ----------

@app.route("/health")
def health_check():
    # A simple page to confirm the server is running
    return "Qless is running. Less Waiting. Less Waste. Better Campus."


@app.route("/db-check")
@role_required("manager")
def database_check():
    # Shows how many rows each table has. Managers only.
    # (We will remove this page before the final demo.)
    table_names = [
        "users", "menu_items", "pickup_slots", "orders", "order_items",
        "daily_batches", "waste_logs", "feedback",
    ]
    row_counts = {}

    try:
        for table_name in table_names:
            row = fetch_one(f"SELECT COUNT(*) AS total FROM {table_name}")
            row_counts[table_name] = row["total"]
    except Exception as error:
        return jsonify({"error": str(error)}), 500

    return jsonify(row_counts)


if __name__ == "__main__":
    app.run(debug=Config.DEBUG)