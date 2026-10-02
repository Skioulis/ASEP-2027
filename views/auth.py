"""Sign-up, login and logout."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select

from extensions import db
from models import User, utcnow
from ratelimit import limiter

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
MIN_PASSWORD = 8
TOO_MANY = "Πάρα πολλές προσπάθειες. Δοκιμάστε ξανά σε λίγα λεπτά."


def _client_ip() -> str:
    return request.remote_addr or "unknown"


def _safe_next(target: str | None) -> str:
    """Only follow same-site relative paths after login (no open redirects)."""
    if (
        target
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
        and not any(ord(c) < 32 or c == "\x7f" for c in target)
    ):
        parts = urlsplit(target)
        if not parts.scheme and not parts.netloc:
            return target
    return url_for("main.index")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    username = request.form.get("username", "").strip().lower()
    if request.method == "GET":
        return render_template("auth/register.html", username="")
    password = request.form.get("password", "")
    error, status = None, 400
    if not limiter.hit(f"register:{_client_ip()}", *current_app.config["REGISTER_RATE"]):
        error, status = TOO_MANY, 429
    elif not USERNAME_RE.match(username):
        error = "Το όνομα χρήστη πρέπει να έχει 3–32 λατινικούς χαρακτήρες, ψηφία ή . _ -"
    elif len(password) < MIN_PASSWORD:
        error = f"Ο κωδικός πρέπει να έχει τουλάχιστον {MIN_PASSWORD} χαρακτήρες."
    elif password != request.form.get("confirm", ""):
        error = "Οι κωδικοί δεν ταιριάζουν."
    elif db.session.scalar(select(User).filter_by(username=username)):
        error = "Το όνομα χρήστη χρησιμοποιείται ήδη."
    if error:
        flash(error, "danger")
        return render_template("auth/register.html", username=username), status
    user = User(username=username, last_login_at=utcnow())
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user, remember=True)
    flash("Καλώς ήρθατε! Η πρόοδός σας θα αποθηκεύεται πλέον.", "success")
    return redirect(url_for("main.index"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    username = request.form.get("username", "").strip().lower()
    if request.method == "GET":
        return render_template("auth/login.html", username="")
    error, status = None, 400
    if not limiter.hit(f"login:{_client_ip()}:{username}", *current_app.config["LOGIN_RATE"]):
        error, status = TOO_MANY, 429
    else:
        user = db.session.scalar(select(User).filter_by(username=username))
        if user is None or not user.check_password(request.form.get("password", "")):
            error = "Λάθος όνομα χρήστη ή κωδικός."
        elif not user.active:
            error, status = "Ο λογαριασμός έχει απενεργοποιηθεί.", 403
    if error:
        flash(error, "danger")
        return render_template("auth/login.html", username=username), status
    user.last_login_at = utcnow()
    db.session.commit()
    login_user(user, remember=True)
    return redirect(_safe_next(request.args.get("next")))


@bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.index"))
