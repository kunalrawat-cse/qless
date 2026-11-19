"""
public.py - The public website (no login needed).

Pages:
  /                 Home
  /how-it-works     How It Works
  /sustainability   Sustainability
  /about            About
  /contact          Contact
  /open-app         Sends a logged-in user to their own home screen

The pages are plain templates with no database queries, so they load fast
and never break if MySQL is switched off.
"""

from flask import Blueprint, g, redirect, render_template, url_for

from routes.access import home_url_for_role

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def home():
    # Everyone sees the public Home page, logged in or not.
    # The navbar button changes to "Open my app" for logged-in users.
    return render_template("public/home.html")


@public_bp.route("/how-it-works")
def how_it_works():
    return render_template("public/how_it_works.html")


@public_bp.route("/sustainability")
def sustainability():
    return render_template("public/sustainability.html")


@public_bp.route("/about")
def about():
    return render_template("public/about.html")


@public_bp.route("/contact")
def contact():
    return render_template("public/contact.html")


@public_bp.route("/open-app")
def open_app():
    # Used by the "Open my app" button in the navbar
    if g.user is None:
        return redirect(url_for("auth.login"))
    return redirect(home_url_for_role(g.user["role"]))
