"""Admin area (admins only): edit questions, import/export the bank, manage users."""

from __future__ import annotations

import io
import json
import unicodedata

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_user
from sqlalchemy import func, select

import bank
from extensions import db, login_manager
from models import Attempt, Category, Question, User

bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGE_SIZE = 25
MIN_PASSWORD = 8
USER_ACTIONS = ("toggle-active", "toggle-admin", "reset-password", "delete")


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


# ── Import / export ──────────────────────────────────────────────────────────

@bp.get("/export")
def export():
    return send_file(io.BytesIO(bank.export_zip()), mimetype="application/zip",
                     as_attachment=True, download_name="asep-questions.zip")


@bp.route("/import", methods=["GET", "POST"])
def import_bank():
    if request.method == "GET":
        return render_template("admin/import.html", categories=_categories(), selected="")
    category = _category_or_404(request.form.get("category", ""))

    def form_error(problems: list[str]):
        return render_template("admin/import.html", categories=_categories(),
                               selected=category.slug, problems=problems), 400

    if "payload" in request.form:  # step 2: the admin confirmed the preview
        raw = request.form["payload"]
    else:
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return form_error(["Επιλέξτε αρχείο JSON."])
        try:
            raw = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return form_error(["Το αρχείο δεν είναι κείμενο UTF-8."])
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        return form_error([f"Μη έγκυρο JSON: {exc}"])
    try:
        if request.form.get("confirm") == "1":
            plan = bank.apply_import(category, items)
            flash(f"Εισαγωγή στην κατηγορία «{category.name}»: {len(plan.added)} νέες, "
                  f"{len(plan.changed)} αλλαγμένες, {len(plan.removed)} διαγραμμένες.", "success")
            return redirect(url_for("admin.questions", category=category.slug))
        plan = bank.plan_import(category, items)
    except bank.BankError as exc:
        return form_error(exc.problems)
    return render_template("admin/import_preview.html", category=category,
                           plan=plan, payload=raw)


# ── Users ────────────────────────────────────────────────────────────────────

@bp.get("/users")
def users():
    rows = db.session.execute(
        select(User, func.count(Attempt.id)).outerjoin(Attempt)
        .group_by(User.id).order_by(User.created_at.desc())).all()
    return render_template("admin/users.html", rows=rows)


@bp.post("/users/<int:uid>/<action>")
def user_action(uid: int, action: str):
    if action not in USER_ACTIONS:
        abort(404)
    user = db.session.get(User, uid) or abort(404)
    if user.id == current_user.id and action != "reset-password":
        flash("Δεν μπορείτε να απενεργοποιήσετε, να υποβαθμίσετε ή να διαγράψετε "
              "τον δικό σας λογαριασμό.", "danger")
        return redirect(url_for("admin.users"))
    if action == "toggle-active":
        user.active = not user.active
        message = f"Ο χρήστης {user.username} {'ενεργοποιήθηκε' if user.active else 'απενεργοποιήθηκε'}."
    elif action == "toggle-admin":
        user.is_admin = not user.is_admin
        message = f"Ο χρήστης {user.username} {'είναι πλέον' if user.is_admin else 'δεν είναι πλέον'} διαχειριστής."
    elif action == "reset-password":
        password = request.form.get("password", "")
        if len(password) < MIN_PASSWORD:
            flash(f"Ο νέος κωδικός πρέπει να έχει τουλάχιστον {MIN_PASSWORD} χαρακτήρες.", "danger")
            return redirect(url_for("admin.users"))
        user.set_password(password)
        message = f"Ο κωδικός του {user.username} άλλαξε."
    else:
        db.session.delete(user)
        message = f"Ο χρήστης {user.username} διαγράφηκε."
    db.session.commit()
    if action == "reset-password" and user.id == current_user.id:
        # The new password changed the session id; keep this admin signed in.
        login_user(user, remember=True)
    flash(message, "success")
    return redirect(url_for("admin.users"))
