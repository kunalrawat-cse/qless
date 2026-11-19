"""
app.py - Entry point. Run this file to start the Qless web server.
"""

from flask import Flask, jsonify

from config import Config
from db import fetch_one

# Create the Flask app and load all settings from config.py
app = Flask(__name__)
app.config.from_object(Config)


@app.route("/health")
def health_check():
    # A simple page to confirm the server is running
    return "Qless is running. Less Waiting. Less Waste. Better Campus."


@app.route("/db-check")
def database_check():
    # Shows how many rows each table has, so we can confirm the seed worked.
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