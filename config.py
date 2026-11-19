"""
config.py - Every setting for Qless lives here.

Secrets (passwords, keys) come from the .env file.
Business rules (slot length, low-stock limit, etc.) are plain numbers
you can safely edit below.
"""

import os

from dotenv import load_dotenv

# Read the .env file so os.getenv() can see its values
load_dotenv()


class Config:
    # ---------- Flask basics ----------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-change-me")
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

    # ---------- Session / cookie safety ----------
    SESSION_COOKIE_HTTPONLY = True      # JavaScript cannot read the login cookie
    SESSION_COOKIE_SAMESITE = "Lax"     # Helps block cross-site request tricks

    # ---------- MySQL database ----------
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "qless_db")

    # ---------- Pickup slot rules (edit these safely) ----------
    SLOT_LENGTH_MINUTES = 15            # Each pickup slot is 15 minutes
    DEFAULT_SLOT_CAPACITY = 12         # Max orders per slot (manager can change later)
    CANTEEN_OPEN_HOUR = 9               # First slot starts at 09:00
    CANTEEN_CLOSE_HOUR = 17             # Last slot ends at 17:00

    # ---------- Order rules from the blueprint ----------
    CANCEL_BEFORE_SLOT_MINUTES = 10     # Student can cancel until 10 min before pickup
    UNCOLLECTED_AFTER_MINUTES = 30      # Flag order for staff after 30 min uncollected
    LOW_STOCK_LIMIT = 5                 # Show "Low Stock" badge at 5 or fewer left

    # ---------- Live updates ----------
    POLL_INTERVAL_SECONDS = 15          # Browser refreshes order status every 15 s