from sqlalchemy import func, select

from extensions import db
from models import Attempt, Category, Question, User, load_user


def _question_with_attempt():
    category = Category(slug="alpha", name="Άλφα")
    question = Question(id="alpha-1", number=1, text="Ερώτηση;", options=["α", "β", "γ", "δ"],
                        correct=2, category=category)
    user = User(username="maria")
    user.set_password("secret-pass")
    db.session.add_all([category, question, user])
    db.session.flush()
    db.session.add(Attempt(user_id=user.id, question_id=question.id, chosen=2,
                           is_correct=True, mode="quiz"))
    db.session.commit()
    return question, user


def _attempt_count():
    return db.session.scalar(select(func.count()).select_from(Attempt))


def test_password_is_hashed_and_checked(app):
    user = User(username="maria")
    user.set_password("secret-pass")
    assert user.password_hash != "secret-pass"
    assert user.check_password("secret-pass")
    assert not user.check_password("wrong-pass")


def test_question_to_dict_uses_compact_shape(app):
    question, _ = _question_with_attempt()
    assert question.to_dict() == {"id": "alpha-1", "n": 1, "q": "Ερώτηση;",
                                  "a": ["α", "β", "γ", "δ"], "c": 2, "category": "alpha"}


def test_deleting_question_deletes_its_attempts(app):
    question, _ = _question_with_attempt()
    db.session.delete(question)
    db.session.commit()
    assert _attempt_count() == 0


def test_deleting_user_deletes_their_attempts(app):
    _, user = _question_with_attempt()
    db.session.delete(user)
    db.session.commit()
    assert _attempt_count() == 0


def test_disabled_user_is_not_loaded_into_session(app):
    _, user = _question_with_attempt()
    assert load_user(user.get_id()) is user
    user.active = False
    db.session.commit()
    assert load_user(user.get_id()) is None


def test_changing_password_invalidates_old_session_ids(app):
    _, user = _question_with_attempt()
    old_id = user.get_id()
    assert load_user(old_id) is user
    user.set_password("another-pass")
    db.session.commit()
    assert load_user(old_id) is None
    assert load_user(user.get_id()) is user


def test_malformed_session_ids_are_rejected(app):
    _question_with_attempt()
    for bad_id in ("abc", "1", "1:x:y", "x:abc"):
        assert load_user(bad_id) is None, bad_id
