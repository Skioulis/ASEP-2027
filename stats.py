"""Per-user progress, derived from answer attempts.

A question's status for a user comes from their *latest* attempt on it, judged
against the *current* answer key: absent = unseen, True = last answered
correctly, False = last answered wrongly. ``Attempt.is_correct`` is only the
historical "correct at the time" value, so editing or re-importing a question's
correct answer immediately updates everyone's progress.
"""

from __future__ import annotations

from sqlalchemy import func, select

from extensions import db
from models import Attempt, Category, Question


def latest_status(user_id: int) -> dict[str, bool]:
    """question_id → whether the user's latest attempt matches the current answer key.

    Compares ``Attempt.chosen`` with ``Question.correct`` instead of reading the
    stored ``Attempt.is_correct`` (what was true when the answer was given).
    """
    latest_ids = (select(func.max(Attempt.id))
                  .where(Attempt.user_id == user_id)
                  .group_by(Attempt.question_id))
    rows = db.session.execute(
        select(Attempt.question_id, Attempt.chosen == Question.correct)
        .join(Question, Question.id == Attempt.question_id)
        .where(Attempt.id.in_(latest_ids)))
    return {qid: bool(ok) for qid, ok in rows}


def _pct(correct: int, answered: int) -> int | None:
    return round(100 * correct / answered) if answered else None


def _avg(time_ms: int, timed: int) -> int | None:
    return round(time_ms / timed) if timed else None


def _answer_times(user_id: int) -> dict[str, tuple[int, int]]:
    """category slug → (number of timed answers, their total ms); every timed answer counts."""
    rows = db.session.execute(
        select(Category.slug, func.count(Attempt.time_ms), func.sum(Attempt.time_ms))
        .join(Question, Question.id == Attempt.question_id).join(Category)
        .where(Attempt.user_id == user_id, Attempt.time_ms.is_not(None))
        .group_by(Category.slug))
    return {slug: (count, int(total)) for slug, count, total in rows}


def category_stats(user_id: int) -> list[dict]:
    """One row per category: slug, name, total, answered, correct, wrong, pct,
    and quiz answer times: timed (count), time_ms (sum), avg_ms."""
    status = latest_status(user_id)
    times = _answer_times(user_id)
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
        row["timed"], row["time_ms"] = times.get(row["slug"], (0, 0))
        row["avg_ms"] = _avg(row["time_ms"], row["timed"])
    return result


def totals(rows: list[dict]) -> dict:
    """Sum category_stats rows into one overall row."""
    keys = ("total", "answered", "correct", "wrong", "timed", "time_ms")
    total = {key: sum(r[key] for r in rows) for key in keys}
    total["pct"] = _pct(total["correct"], total["answered"])
    total["avg_ms"] = _avg(total["time_ms"], total["timed"])
    return total
