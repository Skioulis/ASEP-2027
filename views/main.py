"""Public pages: the quiz/browse app shell and the progress page."""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from stats import category_stats, totals

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/stats")
@login_required
def stats():
    rows = category_stats(current_user.id)
    return render_template("stats.html", rows=rows, total=totals(rows))
