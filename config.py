"""
config.py - Every setting for Qless lives here.

Secrets (passwords, keys) come from the .env file.
Business rules (slot length, low-stock limit, etc.) are plain numbers
you can safely edit below.
"""

import os
from datetime import timedelta

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
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)   # Stay logged in for one shift

    # ---------- Passwords and recovery ----------
    MIN_PASSWORD_LENGTH = 8             # Shortest password allowed at signup
    RESET_OTP_MINUTES = 10              # A password-reset code works for 10 minutes
    SHOW_RESET_OTP_ON_SCREEN = True     # Demo mode: show the code on screen (no email server yet)

    # ---------- MySQL database ----------
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "qless_db")

    # ---------- Pickup slot rules (edit these safely) ----------
    SLOT_LENGTH_MINUTES = 15            # Each pickup slot is 15 minutes
    DEFAULT_SLOT_CAPACITY = 12          # Max orders per slot (manager can change later)
    CANTEEN_OPEN_HOUR = 0               # First slot starts at 00:00 (24-hour testing mode)
    CANTEEN_CLOSE_HOUR = 24             # Last slot ends at 24:00 (use 9 and 17 for the real demo)

    # ---------- Order rules from the blueprint ----------
    CANCEL_BEFORE_SLOT_MINUTES = 10     # Student can cancel until 10 min before pickup
    UNCOLLECTED_AFTER_MINUTES = 30      # Flag order for staff after 30 min uncollected
    LOW_STOCK_LIMIT = 5                 # Show "Low Stock" badge at 5 or fewer left

    # ---------- Student ordering rules (edit these safely) ----------
    SLOT_LEAD_MINUTES = 10              # A slot must start at least 10 min from now (kitchen needs time)
    MAX_QTY_PER_ITEM = 10               # Most portions of one dish in a single order
    MAX_DIFFERENT_ITEMS = 8             # Most different dishes in a single order
    BUSY_SLOT_PERCENT = 80              # Slots at 80% or more show a "Filling fast" warning
    MENU_CATEGORY_ORDER = [             # Order of the category chips on the menu
        "Breakfast", "Meals", "Snacks", "Rolls & Wraps", "Beverages",
    ]

    # ---------- Live updates ----------
    POLL_INTERVAL_SECONDS = 15          # Browser refreshes order status every 15 s