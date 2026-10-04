import json

from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from extensions import db

GREEK = ["Αθήνα", "Πάτρα", "Βόλος", "Χανιά"]


def _stored_options(qid):
    """The options column exactly as the database holds it (not decoded)."""
    return db.session.execute(
        text("SELECT CAST(options AS TEXT) FROM question WHERE id = :id"), {"id": qid}).scalar()


def test_options_are_stored_as_readable_greek(bank_loaded):
    raw = _stored_options("alpha-1")
    assert "Αθήνα" in raw
    assert "\\u" not in raw


def test_migration_0002_unescapes_existing_options(app):
    downgrade(revision="0001")
    escaped = json.dumps(GREEK)  # json.dumps default: \u escapes, as stored before 0002
    value = "CAST(:opts AS json)" if db.engine.dialect.name == "postgresql" else ":opts"
    db.session.execute(text("INSERT INTO category (id, slug, name, position) VALUES (1, 'alpha', 'Άλφα', 0)"))
    db.session.execute(
        text("INSERT INTO question (id, category_id, number, text, options, correct, updated_at) "
             f"VALUES ('alpha-1', 1, 1, 'Ερώτηση;', {value}, 1, CURRENT_TIMESTAMP)"),
        {"opts": escaped})
    db.session.commit()
    assert "\\u" in _stored_options("alpha-1")

    upgrade()

    raw = _stored_options("alpha-1")
    assert "\\u" not in raw
    assert json.loads(raw) == GREEK
