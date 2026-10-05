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


def test_migration_0003_turns_the_two_tables_into_markup(app):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "m0003", "migrations/versions/0003_question_tables.py")
    m0003 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m0003)

    downgrade(revision="0002")
    db.session.execute(text("INSERT INTO category (id, slug, name, position) "
                            "VALUES (1, 'oikonomikes-epistimes', 'Οικονομικές Επιστήμες', 0)"))
    insert = text("INSERT INTO question (id, category_id, number, text, options, correct, updated_at) "
                  f"VALUES (:id, 1, :n, :text, {'CAST(:opts AS json)' if db.engine.dialect.name == 'postgresql' else ':opts'}, 1, CURRENT_TIMESTAMP)")
    opts = json.dumps(GREEK, ensure_ascii=False)
    old150, _ = m0003.TABLES["oikonomikes-epistimes-150"]
    db.session.execute(insert, {"id": "oikonomikes-epistimes-150", "n": 150, "text": old150, "opts": opts})
    # An admin already edited #197: the migration must leave it alone.
    db.session.execute(insert, {"id": "oikonomikes-epistimes-197", "n": 197, "text": "Edited by admin", "opts": opts})
    db.session.commit()

    upgrade()

    stored = dict(db.session.execute(text("SELECT id, text FROM question")).all())
    assert stored["oikonomikes-epistimes-150"] == m0003.TABLES["oikonomikes-epistimes-150"][1]
    assert "| 0 – 10.000 | 10 |" in stored["oikonomikes-epistimes-150"]
    assert stored["oikonomikes-epistimes-197"] == "Edited by admin"
