"""Per-user progress, derived from answer attempts.

A question's status for a user comes from their *latest* attempt on it:
absent = unseen, True = last answered correctly, False = last answered wrongly.
"""

from __future__ import annotations

from sqlalchemy import func, select

from extensions import db
from models import Attempt, Category, Question


def latest_status(user_id: int) -> dict[str, bool]:
    """question_id → whether the user's latest attempt on it was correct."""
    latest_ids = (select(func.max(Attempt.id))
                  .where(Attempt.user_id == user_id)
                  .group_by(Attempt.question_id))
    rows = db.session.execute(
        select(Attempt.question_id, Attempt.is_correct).where(Attempt.id.in_(latest_ids)))
    return {qid: ok for qid, ok in rows}


def _pct(correct: int, answered: int) -> int | None:
    return round(100 * correct / answered) if answered else None


def category_stats(user_id: int) -> list[dict]:
    """One row per category: slug, name, total, answered, correct, wrong, pct."""
    status = latest_status(user_id)
    rows = db.session.execute(
        select(Category.slug, Category.name, Question.id)
        .join(Question).order_by(Category.position))
    by_slug: dict[str, dict] = {}
    for slug, name, qid in rows:
        row = by_slug.setdefault(slug, {"slug": slug, "name": name, "total": 0,
                                        "answered": 0, "correct": 0, "wrong": 0})
        row["total"] += 1
        if qid in status:
            row["answered"] += 1
            row["correct" if status[qid] else "wrong"] += 1
    result = list(by_slug.values())
    for row in result:
        row["pct"] = _pct(row["correct"], row["answered"])
    return result


def totals(rows: list[dict]) -> dict:
    """Sum category_stats rows into one overall row."""
    total = {key: sum(r[key] for r in rows) for key in ("total", "answered", "correct", "wrong")}
    total["pct"] = _pct(total["correct"], total["answered"])
    return total
