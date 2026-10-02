"""Public pages: the quiz/browse app shell and the progress page."""

from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")
