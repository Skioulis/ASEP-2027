"""Admin area (admins only): edit questions, import/export the bank, manage users."""

from __future__ import annotations

import unicodedata

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select

from extensions import db, login_manager
from models import Category, Question

bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGE_SIZE = 25


@bp.before_request
def _require_admin():
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    if not current_user.is_admin:
        abort(403)


def _fold(text: str) -> str:
    """Lowercase and strip Greek accents so «ποια» matches «Ποιά»."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _categories() -> list[Category]:
    return db.session.scalars(select(Category).order_by(Category.position)).all()


def _category_or_404(slug: str) -> Category:
    return db.session.scalar(select(Category).filter_by(slug=slug)) or abort(404)


def _read_question_form() -> tuple[dict, list[str]]:
    values = {"text": request.form.get("text", "").strip(),
              "options": [request.form.get(f"a{i}", "").strip() for i in range(4)],
              "correct": request.form.get("correct", type=int)}
    problems = []
    if not values["text"]:
        problems.append("Το κείμενο της ερώτησης είναι κενό.")
    if not all(values["options"]):
        problems.append("Συμπληρώστε και τις 4 απαντήσεις.")
    if values["correct"] not in (0, 1, 2, 3):
        problems.append("Επιλέξτε τη σωστή απάντηση.")
    return values, problems


# ── Questions ────────────────────────────────────────────────────────────────

@bp.get("/")
def home():
    return redirect(url_for("admin.questions"))


@bp.get("/questions")
def questions():
    slug = request.args.get("category", "")
    term = request.args.get("q", "").strip()
    stmt = select(Question).join(Category).order_by(Category.position, Question.number)
    if slug:
        stmt = stmt.where(Category.slug == slug)
    items = db.session.scalars(stmt).all()
    if term:
        # SQLite's LIKE is ASCII-only case-insensitive, so match Greek in Python.
        needle = _fold(term)
        items = [q for q in items
                 if q.id == term or needle in _fold(" ".join([q.text, *q.options]))]
    pages = max(1, -(-len(items) // PAGE_SIZE))
    page = min(max(request.args.get("page", 1, type=int), 1), pages)
    return render_template("admin/questions.html", categories=_categories(),
                           items=items[(page - 1) * PAGE_SIZE: page * PAGE_SIZE],
                           total=len(items), page=page, pages=pages, slug=slug, term=term)


@bp.route("/questions/new", methods=["GET", "POST"])
def new_question():
    category = _category_or_404(request.args.get("category", ""))
    values = {"text": "", "options": ["", "", "", ""], "correct": None}
    if request.method == "POST":
        values, problems = _read_question_form()
        if not problems:
            number = (db.session.scalar(select(func.max(Question.number))
                                        .where(Question.category_id == category.id)) or 0) + 1
            while db.session.get(Question, f"{category.slug}-{number}"):
                number += 1
            question = Question(id=f"{category.slug}-{number}", number=number,
                                category=category, text=values["text"],
                                options=values["options"], correct=values["correct"])
            db.session.add(question)
            db.session.commit()
            flash(f"Η ερώτηση {question.id} προστέθηκε.", "success")
            return redirect(url_for("admin.edit_question", qid=question.id))
        for problem in problems:
            flash(problem, "danger")
    return render_template("admin/question_form.html", category=category,
                           question=None, values=values)


@bp.route("/questions/<qid>", methods=["GET", "POST"])
def edit_question(qid: str):
    question = db.session.get(Question, qid) or abort(404)
    values = {"text": question.text, "options": list(question.options),
              "correct": question.correct}
    if request.method == "POST":
        values, problems = _read_question_form()
        if not problems:
            question.text = values["text"]
            question.options = values["options"]
            question.correct = values["correct"]
            db.session.commit()
            flash("Η ερώτηση αποθηκεύτηκε.", "success")
            return redirect(url_for("admin.edit_question", qid=qid))
        for problem in problems:
            flash(problem, "danger")
    return render_template("admin/question_form.html", category=question.category,
                           question=question, values=values)


@bp.post("/questions/<qid>/delete")
def delete_question(qid: str):
    question = db.session.get(Question, qid) or abort(404)
    slug = question.category.slug
    db.session.delete(question)
    db.session.commit()
    flash(f"Η ερώτηση {qid} διαγράφηκε.", "success")
    return redirect(url_for("admin.questions", category=slug))
