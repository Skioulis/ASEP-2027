from extensions import db
from models import Attempt, Question
from stats import category_stats, latest_status, totals
from tests.conftest import make_user


def _answer(user, qid, ok):
    question = db.session.get(Question, qid)
    chosen = question.correct if ok else (question.correct + 1) % 4
    db.session.add(Attempt(user_id=user.id, question_id=qid, chosen=chosen, is_correct=ok, mode="quiz"))
    db.session.commit()


def test_latest_attempt_decides_status(bank_loaded, user):
    _answer(user, "alpha-1", False)
    _answer(user, "alpha-1", True)
    _answer(user, "alpha-2", True)
    _answer(user, "alpha-2", False)
    assert latest_status(user.id) == {"alpha-1": True, "alpha-2": False}


def test_status_follows_answer_key_changes(bank_loaded, user):
    # alpha-1's correct answer is 1, so choosing 0 was wrong when it was recorded...
    db.session.add(Attempt(user_id=user.id, question_id="alpha-1", chosen=0,
                           is_correct=False, mode="quiz"))
    db.session.commit()
    assert latest_status(user.id) == {"alpha-1": False}
    # ...but after an admin fixes the key, the same attempt counts as correct.
    db.session.get(Question, "alpha-1").correct = 0
    db.session.commit()
    assert latest_status(user.id) == {"alpha-1": True}


def test_other_users_attempts_are_ignored(bank_loaded, user):
    other = make_user("nikos")
    _answer(other, "alpha-1", True)
    assert latest_status(user.id) == {}


def test_category_stats_and_totals(bank_loaded, user):
    _answer(user, "alpha-1", True)
    _answer(user, "alpha-2", False)
    _answer(user, "beta-1", True)
    rows = category_stats(user.id)
    assert rows == [
        {"slug": "alpha", "name": "Άλφα Δίκαιο", "total": 3, "answered": 2,
         "correct": 1, "wrong": 1, "pct": 50},
        {"slug": "beta", "name": "Βήτα Οικονομία", "total": 2, "answered": 1,
         "correct": 1, "wrong": 0, "pct": 100},
    ]
    assert totals(rows) == {"total": 5, "answered": 3, "correct": 2, "wrong": 1, "pct": 67}


def test_stats_for_new_user(bank_loaded, user):
    rows = category_stats(user.id)
    assert [r["pct"] for r in rows] == [None, None]
    assert totals(rows)["pct"] is None
