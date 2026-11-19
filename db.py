"""
db.py - The ONE place that talks to MySQL.

Every route in the app uses these three small helpers instead of
writing connection code each time:
    fetch_all(sql, params)  -> list of rows (each row is a dictionary)
    fetch_one(sql, params)  -> a single row, or None
    execute(sql, params)    -> runs INSERT / UPDATE / DELETE, returns new row id

The %s placeholders keep user input safe from SQL injection.
Never build SQL by gluing strings together with user input.
"""

import pymysql
from pymysql.cursors import DictCursor

from config import Config


def get_connection():
    # Open a new connection using the settings from config.py / .env
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


def fetch_all(sql, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    finally:
        connection.close()


def fetch_one(sql, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    finally:
        connection.close()


def execute(sql, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            connection.commit()
            return cursor.lastrowid
    except Exception:
        # Undo a half-finished change if anything went wrong
        connection.rollback()
        raise
    finally:
        connection.close()