"""
security.py - CSRF protection.

CSRF is an attack where another website tricks your browser into sending
a form to Qless while you are logged in. To block it, every form carries
a secret token that only our own pages know.

- csrf_token()        gives the token to put inside a form
- check_csrf_token()  runs before every POST request and rejects bad ones
"""

import secrets

from flask import abort, request, session


def csrf_token():
    # Create the token once per session, then reuse it
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def check_csrf_token():
    # Reading pages is safe. Only requests that change data need a token.
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    expected_token = session.get("csrf_token", "")

    # HTML forms send it as a field, fetch() calls send it as a header
    sent_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""

    if not expected_token or not secrets.compare_digest(expected_token.encode(), sent_token.encode()):
        abort(400)