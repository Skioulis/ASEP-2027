"""JSON API used by static/app.js: categories, browse pages, quizzes, answers.

Questions are sent with their correct index (as the static site did): this is a
study tool, so hiding answers from the browser is not a goal.
"""

from __future__ import annotations

import random

from flask import Blueprint, abort, current_app, jsonify, make_response, request
from flask_login import current_user
from sqlalchemy import func, select

from extensions import db
from models import Attempt, Category, Question
from ratelimit import limiter
from stats import latest_status

bp = Blueprint("api", __name__, url_prefix="/api")

PAGE_SIZE = 10
POOLS = ("all", "unseen", "wrong")
MODES = ("quiz", "browse")


def _fail(status: int, message: str):
    abort(make_response(jsonify(error=message), status))


def _require_login() -> None:
    if not current_user.is_authenticated:
        _fail(401, "Απαιτείται σύνδεση.")


def _category_arg() -> Category | None:
    slug = request.args.get("category", "")
    if not slug:
        return None
    category = db.session.scalar(select(Category).filter_by(slug=slug))
    if category is None:
        _fail(404, f"Άγνωστη κατηγορία: {slug}")
    return category


def _questions(category: Category | None):
    stmt = select(Question).join(Category).order_by(Category.position, Question.number)
    if category is not None:
        stmt = stmt.where(Question.category_id == category.id)
    return stmt


@bp.get("/categories")
def categories():
    rows = db.session.execute(
        select(Category, func.count(Question.id)).outerjoin(Question)
        .group_by(Category.id).order_by(Category.position))
    return jsonify([{"slug": c.slug, "name": c.name, "count": n} for c, n in rows])


@bp.get("/questions")
def questions():
    stmt = _questions(_category_arg())
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery()))
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(request.args.get("page", 1, type=int), 1), pages)
    items = db.session.scalars(stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    return jsonify(items=[q.to_dict() for q in items], page=page, pages=pages, total=total)


@bp.get("/quiz")
def quiz():
    pool = request.args.get("pool", "all")
    if pool not in POOLS:
        _fail(400, "Άγνωστο σύνολο ερωτήσεων.")
    if pool != "all":
        _require_login()
    category = _category_arg()
    size = min(max(request.args.get("size", 25, type=int), 1), 100)
    candidates = db.session.scalars(_questions(category)).all()
    if pool != "all":
        status = latest_status(current_user.id)
        if pool == "unseen":
            candidates = [q for q in candidates if q.id not in status]
        else:
            candidates = [q for q in candidates if status.get(q.id) is False]
    picked = random.sample(candidates, min(size, len(candidates)))
    return jsonify(items=[q.to_dict() for q in picked], pool=pool, available=len(candidates))


@bp.post("/attempts")
def record_attempt():
    _require_login()
    if not limiter.hit(f"attempt:{current_user.id}", *current_app.config["ATTEMPT_RATE"]):
        _fail(429, "Πάρα πολλές απαντήσεις σε λίγο χρόνο. Περιμένετε λίγο.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        _fail(400, "Μη έγκυρη απάντηση.")
    qid = data.get("question_id")
    question = db.session.get(Question, qid) if isinstance(qid, str) else None
    if question is None:
        _fail(404, "Άγνωστη ερώτηση.")
    chosen, mode = data.get("chosen"), data.get("mode", "quiz")
    valid_choice = isinstance(chosen, int) and not isinstance(chosen, bool) and 0 <= chosen <= 3
    if not valid_choice or mode not in MODES:
        _fail(400, "Μη έγκυρη απάντηση.")
    attempt = Attempt(user_id=current_user.id, question_id=question.id, chosen=chosen,
                      is_correct=chosen == question.correct, mode=mode)
    db.session.add(attempt)
    db.session.commit()
    return jsonify(is_correct=attempt.is_correct, correct=question.correct), 201
