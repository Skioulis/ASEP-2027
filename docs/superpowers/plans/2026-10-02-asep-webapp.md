# ASEP 2027 Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Flask web app, run in Docker and published with Tailscale Funnel, that serves the 1988-question ASEP bank (quiz + browse for everyone, per-user progress after sign-up, and an admin area for questions, import/export and users).

**Architecture:** Flask app factory (`app.py`) with SQLite via Flask-SQLAlchemy/Flask-Migrate; blueprints `main` (pages), `auth`, `api` (JSON for the vanilla-JS frontend ported from the static site) and `admin` (server-rendered). Pure modules `bank.py` (JSON bank ⇄ DB) and `stats.py` (progress from latest attempts) hold the logic. The container runs migrations, seeds `data/` once, ensures the admin account and starts gunicorn on port 8000.

**Tech Stack:** Python 3.12 (container) / 3.14 (dev), Flask 3.1, Flask-SQLAlchemy 3.1, Flask-Migrate 4.1, SQLAlchemy 2.0, Flask-Login 0.6, Flask-WTF 1.2 (CSRF only), gunicorn, pytest, Bootstrap 5 + Font Awesome (CDN), Docker Compose, Tailscale Funnel.

**Spec:** `docs/superpowers/specs/2026-10-01-asep-webapp-design.md`

## Global Constraints

- Work in `/home/skioulis/PycharmProjects/ASEP-2027` on branch `webapp`; run every command from the repo root.
- Dependencies are exactly the pins in `requirements.txt` (Task 1). Add no others.
- All user-facing text (templates, flash messages, API `error` strings) is Greek; code, comments, CLI output and commit messages are English.
- Question JSON format: `index.json` = `[{name, slug, count}]`; `categories/<slug>.json` = `[{id, n, q, a, c}]`, `id` = `"<slug>-<n>"`, `a` = exactly 4 options (index 0–3 = α/β/γ/δ), `c` = 0-based correct index. `data/` is the seed source and must not be edited by the app.
- Database path comes from the `ASEP_DB` env var (default `./asep.db`). The container listens on port 8000, published only on `127.0.0.1`.
- Usernames are stored lowercase, `[a-z0-9_.-]{3,32}`; passwords ≥ 8 characters.
- Tests: `.venv/bin/python -m pytest` (pytest config in `pytest.ini`). Every task ends with the whole suite green.
- Every commit message ends with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The machine's system Python has no `ensurepip`: create venvs with `python3 -m venv --without-pip .venv` and install with `/home/skioulis/air/Asep_2027/.venv/bin/pip --python .venv/bin/python install …`.

## File Map

| File | Responsibility | Task |
|---|---|---|
| `requirements.txt`, `pytest.ini` | pinned deps, test config | 1 |
| `extensions.py` | `db`, `migrate`, `login_manager`, `csrf` singletons | 1 |
| `models.py` | `Category`, `Question`, `User`, `Attempt`, `load_user` | 1 |
| `app.py` | `create_app(config)`, env config, ProxyFix, blueprints, error pages, `localtime` filter | 1 → 9 |
| `migrations/` | Alembic env (`flask db init`) + `0001_initial_schema.py` | 1 |
| `bank.py` | validate / read / seed (2); export / plan_import / apply_import (8) | 2, 8 |
| `cli.py` | `flask seed` (2), `flask ensure-admin` (10) | 2, 10 |
| `stats.py` | `latest_status`, `category_stats`, `totals` | 3 |
| `ratelimit.py` | in-memory `RateLimiter`, `limiter` | 4 |
| `views/main.py` | `/` (4), `/stats` (6) | 4, 6 |
| `views/auth.py` | `/register`, `/login`, `/logout` | 4 |
| `views/api.py` | `/api/categories`, `/api/questions`, `/api/quiz`, `/api/attempts` | 5 |
| `views/admin.py` | questions (7), import/export (8), users (9) | 7–9 |
| `templates/`, `static/` | Bootstrap pages; `static/app.js` quiz/browse UI | 4–9 |
| `Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yaml`, `.dockerignore`, `.env.example`, `README.md` | container + docs | 10 |
| `tests/` | one test module per task, fixtures in `tests/fixtures/bank/` | 1–10 |

---

### Task 1: Project skeleton, models and initial migration

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `extensions.py`, `models.py`, `app.py`, `migrations/` (generated), `migrations/versions/0001_initial_schema.py`
- Test: `tests/__init__.py`, `tests/conftest.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `extensions.db / migrate / login_manager / csrf`; models `Category(id, slug, name, position, questions)`, `Question(id: str, category_id, number, text, options: list[str], correct: int, updated_at, category, attempts, to_dict() -> {id, n, q, a, c, category})`, `User(id, username, password_hash, is_admin, active, created_at, last_login_at, attempts, is_active, set_password(pw), check_password(pw) -> bool)`, `Attempt(id, user_id, question_id, chosen, is_correct, mode, created_at)`, `models.utcnow()`, `models.load_user(user_id: str) -> User | None`; `app.create_app(config: dict | None = None) -> Flask` and module-level `app.app`; config keys `DATA_DIR`, `LOGIN_RATE`, `REGISTER_RATE`; pytest fixtures `app`, `client`.

- [ ] **Step 1: Create the dev virtualenv**

`requirements.txt` (create):

```text
Flask==3.1.3
Flask-SQLAlchemy==3.1.1
Flask-Migrate==4.1.0
SQLAlchemy==2.0.51
Flask-Login==0.6.3
Flask-WTF==1.2.2
gunicorn==23.0.0
pytest==9.1.1
tzdata==2026.4
```

```bash
python3 -m venv --without-pip .venv
/home/skioulis/air/Asep_2027/.venv/bin/pip --python .venv/bin/python install -r requirements.txt
```

Expected: installs without errors; `.venv/bin/flask --version` prints `Flask 3.1.3`.

- [ ] **Step 2: Write the failing tests**

`pytest.ini` (create):

```ini
[pytest]
testpaths = tests
filterwarnings =
    ignore:datetime.datetime.utcnow:DeprecationWarning:flask_login
    ignore:'get_engine' is deprecated:DeprecationWarning
```

Create an empty `tests/__init__.py`.

`tests/conftest.py` (create):

```python
"""Test fixtures: a throwaway migrated database per test."""

from __future__ import annotations

import pytest
from flask_migrate import upgrade

from app import create_app
from extensions import db


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
    })
    with application.app_context():
        upgrade()
        yield application
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()
```

`tests/test_models.py` (create):

```python
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
    assert load_user(str(user.id)) is user
    user.active = False
    db.session.commit()
    assert load_user(str(user.id)) is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py`
Expected: FAIL — `E   ModuleNotFoundError: No module named 'app'`

- [ ] **Step 4: Write the extensions, models and app factory**

`extensions.py` (create):

```python
"""Shared Flask extensions.

Kept in their own module so ``app``, ``models`` and the views can all import
them without circular imports.
"""

from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base enabling SQLAlchemy 2.0 typed models (Mapped[...])."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
```

`models.py` (create):

```python
"""Database models: the question bank, user accounts, and answer attempts.

Deletes cascade through the ORM relationships (not SQLite foreign-key
pragmas), so deleting a question or a user also deletes its attempts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(default=0)

    questions: Mapped[list[Question]] = relationship(
        back_populates="category", order_by="Question.number",
        cascade="all, delete-orphan")


class Question(db.Model):
    # "<category slug>-<number in the PDF>", e.g. "dioikitiko-dikaio-57".
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), index=True)
    number: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    # Exactly four option strings, index 0-3 = α/β/γ/δ.
    options: Mapped[list[str]] = mapped_column(JSON)
    correct: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    category: Mapped[Category] = relationship(back_populates="questions")
    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="question", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        """The compact shape the frontend and the JSON files use."""
        return {"id": self.id, "n": self.number, "q": self.text,
                "a": list(self.options), "c": self.correct,
                "category": self.category.slug}


class User(UserMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lowercase; restricted to [a-z0-9_.-] by the register form.
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    # Named "active" because UserMixin already defines the is_active property.
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime | None]

    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="user", cascade="all, delete-orphan")

    @property
    def is_active(self) -> bool:
        """Flask-Login refuses to log in users whose is_active is False."""
        return self.active

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Attempt(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    question_id: Mapped[str] = mapped_column(ForeignKey("question.id"))
    chosen: Mapped[int]
    is_correct: Mapped[bool]
    mode: Mapped[str] = mapped_column(String(10))  # "quiz" | "browse"
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = relationship(back_populates="attempts")
    question: Mapped[Question] = relationship(back_populates="attempts")

    __table_args__ = (Index("ix_attempt_user_question", "user_id", "question_id"),)


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    # Returning None for disabled users logs them out on their next request.
    user = db.session.get(User, int(user_id))
    return user if user is not None and user.active else None
```

`app.py` (create):

```python
"""Flask application factory for the ASEP 2027 question bank."""

from __future__ import annotations

import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import csrf, db, login_manager, migrate

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Overridable so the database can live on a mounted volume in Docker.
DB_PATH = os.environ.get("ASEP_DB", os.path.join(BASE_DIR, "asep.db"))

def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    # Wait up to 15s on a locked SQLite file (helps with multiple gunicorn workers).
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 15}}
    # Signs the session cookie. Override in production (.env).
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-asep-key")
    # Funnel serves the site over https, so production cookies are Secure.
    secure = os.environ.get("SESSION_COOKIE_SECURE") == "1"
    app.config["SESSION_COOKIE_SECURE"] = secure
    app.config["REMEMBER_COOKIE_SECURE"] = secure
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # CSRF tokens stay valid for the whole session (quiz tabs can stay open).
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    # The extracted question bank used by `flask seed`.
    app.config["DATA_DIR"] = os.path.join(BASE_DIR, "data")
    # Admin import posts a category JSON (~250 KB today) back with the preview.
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = 5 * 1024 * 1024
    # (max attempts, window in seconds) for the public login/register forms.
    app.config["LOGIN_RATE"] = (10, 300)
    app.config["REGISTER_RATE"] = (10, 3600)
    if config:
        app.config.update(config)

    # Tailscale Funnel terminates TLS and proxies one hop to the container.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    # render_as_batch: SQLite needs batch mode for ALTER TABLE migrations.
    migrate.init_app(app, db, render_as_batch=True)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Συνδεθείτε για να συνεχίσετε."
    login_manager.login_message_category = "warning"

    # Import models so their tables register with the metadata.
    import models  # noqa: F401

    return app


app = create_app()
```

- [ ] **Step 5: Create the migration**

Run: `FLASK_APP=app .venv/bin/flask db init` (generates `migrations/` with `alembic.ini`, `env.py`, `script.py.mako`, `versions/`).

Then write the initial schema by hand so the revision id is stable:

`migrations/versions/0001_initial_schema.py` (create):

```python
"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('category',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=32), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('question',
    sa.Column('id', sa.String(length=160), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('options', sa.JSON(), nullable=False),
    sa.Column('correct', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['category.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('question', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_question_category_id'), ['category_id'], unique=False)

    op.create_table('attempt',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.String(length=160), nullable=False),
    sa.Column('chosen', sa.Integer(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('mode', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['question.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('attempt', schema=None) as batch_op:
        batch_op.create_index('ix_attempt_user_question', ['user_id', 'question_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('attempt', schema=None) as batch_op:
        batch_op.drop_index('ix_attempt_user_question')

    op.drop_table('attempt')
    with op.batch_alter_table('question', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_question_category_id'))

    op.drop_table('question')
    op.drop_table('user')
    op.drop_table('category')
    # ### end Alembic commands ###
```

Check the migration matches the models:

```bash
FLASK_APP=app ASEP_DB=/tmp/asep-check.db .venv/bin/flask db upgrade
FLASK_APP=app ASEP_DB=/tmp/asep-check.db .venv/bin/flask db check
rm /tmp/asep-check.db
```

Expected: `Running upgrade  -> 0001, initial schema`, then `No new upgrade operations detected.`

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `5 passed`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini extensions.py models.py app.py migrations tests
git commit -m "Add Flask app skeleton, models and initial migration" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Question bank module and `flask seed`

**Files:**
- Create: `bank.py`, `cli.py`, `tests/fixtures/bank/index.json`, `tests/fixtures/bank/categories/alpha.json`, `tests/fixtures/bank/categories/beta.json`
- Modify: `app.py` (register the CLI), `tests/conftest.py` (fixture bank)
- Test: `tests/test_bank.py`

**Interfaces:**
- Consumes: models and `create_app` from Task 1.
- Produces: `bank.BankError(problems: list[str])` (`.problems`), `bank.validate_items(items, slug) -> list[str]`, `bank.read_bank(data_dir) -> list[{slug, name, items}]` (raises `BankError`), `bank.seed(data_dir) -> int` (0 when questions already exist), private `bank._new_question(item, pos, category) -> Question`; `cli.register_cli(app)` with command `flask seed`; conftest `FIXTURE_BANK` (2 categories: `alpha` "Άλφα Δίκαιο" with alpha-1..3, `beta` "Βήτα Οικονομία" with beta-1..2) and fixture `bank_loaded`.

- [ ] **Step 1: Write the fixture bank and failing tests**

`tests/fixtures/bank/index.json` (create):

```json
[
 {"name": "Άλφα Δίκαιο", "slug": "alpha", "count": 3},
 {"name": "Βήτα Οικονομία", "slug": "beta", "count": 2}
]
```

`tests/fixtures/bank/categories/alpha.json` (create):

```json
[
 {"id": "alpha-1", "n": 1, "q": "Ποια είναι η πρωτεύουσα της Ελλάδας;", "a": ["Θεσσαλονίκη", "Αθήνα", "Πάτρα", "Λάρισα"], "c": 1},
 {"id": "alpha-2", "n": 2, "q": "Πόσα άρθρα έχει το Σύνταγμα;", "a": ["120", "100", "90", "150"], "c": 0},
 {"id": "alpha-3", "n": 3, "q": "Ποιος ψηφίζει τους νόμους;", "a": ["Η Κυβέρνηση", "Ο Πρόεδρος", "Η Βουλή", "Τα δικαστήρια"], "c": 2}
]
```

`tests/fixtures/bank/categories/beta.json` (create):

```json
[
 {"id": "beta-1", "n": 1, "q": "Τι μετρά ο πληθωρισμός;", "a": ["Την ανεργία", "Τη μεταβολή του επιπέδου τιμών", "Το ΑΕΠ", "Τους φόρους"], "c": 1},
 {"id": "beta-2", "n": 2, "q": "Η αμοιβή του κεφαλαίου είναι:", "a": ["Το ενοίκιο", "Ο μισθός", "Το κέρδος", "Ο τόκος"], "c": 3}
]
```

Replace `tests/conftest.py` with:

```python
"""Test fixtures: a throwaway migrated database per test and a small question
bank (tests/fixtures/bank)."""

from __future__ import annotations

import os

import pytest
from flask_migrate import upgrade

from app import create_app
from extensions import db

FIXTURE_BANK = os.path.join(os.path.dirname(__file__), "fixtures", "bank")


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "DATA_DIR": FIXTURE_BANK,
    })
    with application.app_context():
        upgrade()
        yield application
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def bank_loaded(app):
    """Seed the 5-question fixture bank (categories alpha: 3, beta: 2)."""
    import bank
    bank.seed(FIXTURE_BANK)
```

`tests/test_bank.py` (create):

```python
import os

import pytest
from sqlalchemy import func, select

import bank
from extensions import db
from models import Category, Question
from tests.conftest import FIXTURE_BANK

REAL_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
GOOD = {"id": "alpha-1", "n": 1, "q": "Ερώτηση;", "a": ["α", "β", "γ", "δ"], "c": 0}


def test_validate_accepts_good_items():
    assert bank.validate_items([GOOD], "alpha") == []


def test_validate_n_is_optional():
    item = {k: v for k, v in GOOD.items() if k != "n"}
    assert bank.validate_items([item], "alpha") == []


def test_validate_rejects_non_list():
    assert len(bank.validate_items({"id": "x"}, "alpha")) == 1


def test_validate_reports_every_problem():
    items = [
        GOOD,
        dict(GOOD),                                   # duplicate id
        dict(GOOD, id="beta-1"),                      # wrong prefix
        dict(GOOD, id="alpha-3", a=["α", "β", "γ"]),  # 3 options
        dict(GOOD, id="alpha-4", c=4),                # c out of range
        dict(GOOD, id="alpha-5", q="  "),             # empty question
        dict(GOOD, id="alpha-6", c=True),             # bool is not an index
    ]
    problems = bank.validate_items(items, "alpha")
    assert len(problems) == 6
    assert "διπλό id" in problems[0]
    assert "alpha-" in problems[1]


def test_read_bank_returns_categories_in_index_order():
    data = bank.read_bank(FIXTURE_BANK)
    assert [c["slug"] for c in data] == ["alpha", "beta"]
    assert [len(c["items"]) for c in data] == [3, 2]


def test_real_extracted_bank_is_valid():
    data = bank.read_bank(REAL_DATA)
    assert len(data) == 11
    assert sum(len(c["items"]) for c in data) == 1988


def test_read_bank_raises_with_all_problems(tmp_path):
    (tmp_path / "categories").mkdir()
    (tmp_path / "index.json").write_text('[{"name": "Άλφα", "slug": "alpha", "count": 1}]')
    (tmp_path / "categories" / "alpha.json").write_text('[{"id": "zzz", "q": "", "a": [], "c": 9}]')
    with pytest.raises(bank.BankError) as excinfo:
        bank.read_bank(str(tmp_path))
    assert len(excinfo.value.problems) == 4


def test_seed_loads_once(app):
    assert bank.seed(FIXTURE_BANK) == 5
    assert bank.seed(FIXTURE_BANK) == 0
    assert db.session.scalar(select(func.count()).select_from(Question)) == 5
    alpha = db.session.scalar(select(Category).filter_by(slug="alpha"))
    assert [q.id for q in alpha.questions] == ["alpha-1", "alpha-2", "alpha-3"]
    assert alpha.questions[1].options[0] == "120"


def test_seed_cli_command(app):
    runner = app.test_cli_runner()
    assert "Seeded 5 questions." in runner.invoke(args=["seed"]).output
    assert "already loaded" in runner.invoke(args=["seed"]).output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bank.py`
Expected: FAIL — `E   ModuleNotFoundError: No module named 'bank'`

- [ ] **Step 3: Implement `bank.py` and the seed command**

`bank.py` (create):

```python
"""The question bank as JSON files: validate, seed, import and export.

On-disk format (also the admin import/export format):

    index.json              [{name, slug, count}]
    categories/<slug>.json  [{id, n, q, a, c}]

``id`` is "<slug>-<n>", ``n`` the number printed in the PDF (optional on
import; defaults to the item's 1-based position), ``q`` the question text,
``a`` exactly four options (α..δ) and ``c`` the 0-based correct index.
"""

from __future__ import annotations

import json
import os

from sqlalchemy import func, select

from extensions import db
from models import Category, Question

class BankError(ValueError):
    """Question data failed validation; ``problems`` lists every issue."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_items(items: object, slug: str) -> list[str]:
    """Return human-readable problems with one category's items (empty = valid)."""
    if not isinstance(items, list):
        return ["Το αρχείο πρέπει να περιέχει λίστα ερωτήσεων (JSON array)."]
    problems: list[str] = []
    seen: set[str] = set()
    for pos, item in enumerate(items, 1):
        if not isinstance(item, dict):
            problems.append(f"Ερώτηση {pos}: δεν είναι αντικείμενο JSON.")
            continue
        qid = item.get("id")
        label = f"Ερώτηση {pos} ({qid})"
        if not isinstance(qid, str) or not qid.startswith(f"{slug}-"):
            problems.append(f"{label}: το id πρέπει να αρχίζει με «{slug}-».")
        elif qid in seen:
            problems.append(f"{label}: διπλό id.")
        else:
            seen.add(qid)
        if not isinstance(item.get("q"), str) or not item["q"].strip():
            problems.append(f"{label}: λείπει το κείμενο της ερώτησης.")
        options = item.get("a")
        if not (isinstance(options, list) and len(options) == 4
                and all(isinstance(o, str) and o.strip() for o in options)):
            problems.append(f"{label}: χρειάζονται ακριβώς 4 μη κενές απαντήσεις.")
        if not (_is_int(item.get("c")) and 0 <= item["c"] <= 3):
            problems.append(f"{label}: η σωστή απάντηση (c) πρέπει να είναι 0–3.")
        number = item.get("n", pos)
        if not (_is_int(number) and number > 0):
            problems.append(f"{label}: ο αριθμός (n) πρέπει να είναι θετικός ακέραιος.")
    return problems


def read_bank(data_dir: str) -> list[dict]:
    """Read and validate a bank directory → [{slug, name, items}] in index order."""
    with open(os.path.join(data_dir, "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    bank, problems = [], []
    for entry in index:
        path = os.path.join(data_dir, "categories", f"{entry['slug']}.json")
        with open(path, encoding="utf-8") as fh:
            items = json.load(fh)
        problems += [f"{entry['slug']}: {p}" for p in validate_items(items, entry["slug"])]
        bank.append({"slug": entry["slug"], "name": entry["name"], "items": items})
    if problems:
        raise BankError(problems)
    return bank


def _new_question(item: dict, pos: int, category: Category) -> Question:
    return Question(id=item["id"], number=item.get("n", pos), text=item["q"],
                    options=list(item["a"]), correct=item["c"], category=category)


def seed(data_dir: str) -> int:
    """Load the bank into an empty database; return questions inserted (0 = already seeded)."""
    if db.session.scalar(select(func.count()).select_from(Question)):
        return 0
    total = 0
    for position, entry in enumerate(read_bank(data_dir)):
        category = Category(slug=entry["slug"], name=entry["name"], position=position)
        db.session.add(category)
        for pos, item in enumerate(entry["items"], 1):
            db.session.add(_new_question(item, pos, category))
            total += 1
    db.session.commit()
    return total
```

`cli.py` (create):

```python
"""Flask CLI commands run by docker/entrypoint.sh on every container start."""

from __future__ import annotations

import click
from flask import Flask, current_app

import bank


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_command() -> None:
        """Load data/ into the database if it holds no questions yet."""
        inserted = bank.seed(current_app.config["DATA_DIR"])
        click.echo(f"Seeded {inserted} questions." if inserted
                   else "Questions already loaded; nothing to do.")
```

In `app.py`, replace the end of `create_app` (from `# Import models so their tables register with the metadata.` through `return app`) with:

```python
    # Import models so their tables register with the metadata.
    import models  # noqa: F401
    from cli import register_cli

    register_cli(app)

    return app
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `14 passed`

`test_real_extracted_bank_is_valid` reads the real `data/` (11 categories, 1988 questions), so the shipped bank is validated on every run.

- [ ] **Step 5: Commit**

```bash
git add bank.py cli.py app.py tests
git commit -m "Add question bank loader and flask seed command" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Progress statistics

**Files:**
- Create: `stats.py`
- Modify: `tests/conftest.py` (user helper)
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `Attempt`, `Category`, `Question`; `bank_loaded` fixture.
- Produces: `stats.latest_status(user_id) -> dict[str, bool]` (question id → latest attempt correct; absent = unseen), `stats.category_stats(user_id) -> list[{slug, name, total, answered, correct, wrong, pct}]` (`pct` = rounded % or `None`), `stats.totals(rows) -> {total, answered, correct, wrong, pct}`; conftest `PASSWORD = "secret-pass"`, `make_user(username="maria", password=PASSWORD, is_admin=False, active=True) -> User`, fixture `user`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/conftest.py` with:

```python
"""Test fixtures: a throwaway migrated database per test, a small question
bank (tests/fixtures/bank), and a helper to create users."""

from __future__ import annotations

import os

import pytest
from flask_migrate import upgrade

from app import create_app
from extensions import db

FIXTURE_BANK = os.path.join(os.path.dirname(__file__), "fixtures", "bank")
PASSWORD = "secret-pass"


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "DATA_DIR": FIXTURE_BANK,
    })
    with application.app_context():
        upgrade()
        yield application
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def bank_loaded(app):
    """Seed the 5-question fixture bank (categories alpha: 3, beta: 2)."""
    import bank
    bank.seed(FIXTURE_BANK)


def make_user(username="maria", password=PASSWORD, is_admin=False, active=True):
    from models import User
    user = User(username=username, is_admin=is_admin, active=active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def user(app):
    return make_user()
```

`tests/test_stats.py` (create):

```python
from extensions import db
from models import Attempt
from stats import category_stats, latest_status, totals
from tests.conftest import make_user


def _answer(user, qid, ok):
    db.session.add(Attempt(user_id=user.id, question_id=qid, chosen=0, is_correct=ok, mode="quiz"))
    db.session.commit()


def test_latest_attempt_decides_status(bank_loaded, user):
    _answer(user, "alpha-1", False)
    _answer(user, "alpha-1", True)
    _answer(user, "alpha-2", True)
    _answer(user, "alpha-2", False)
    assert latest_status(user.id) == {"alpha-1": True, "alpha-2": False}


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_stats.py`
Expected: FAIL — `E   ModuleNotFoundError: No module named 'stats'`

- [ ] **Step 3: Implement `stats.py`**

`stats.py` (create):

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `18 passed`

- [ ] **Step 5: Commit**

```bash
git add stats.py tests
git commit -m "Add per-user progress statistics" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Accounts — rate limiter, register, login, logout, base layout

**Files:**
- Create: `ratelimit.py`, `views/__init__.py`, `views/main.py`, `views/auth.py`, `templates/base.html`, `templates/error.html`, `templates/index.html` (placeholder, replaced in Task 6), `templates/auth/login.html`, `templates/auth/register.html`, `static/style.css`
- Modify: `app.py` (blueprints + error pages), `tests/conftest.py` (final version)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `User`, `utcnow`, `login_manager` (`login_view = "auth.login"`), config `LOGIN_RATE` / `REGISTER_RATE` = `(limit, window_seconds)`.
- Produces: `ratelimit.RateLimiter.hit(key, limit, window, now=None) -> bool`, `.reset()`, module singleton `ratelimit.limiter`; blueprints `main.bp` (endpoint `main.index` at `/`) and `auth.bp` (`auth.register` `/register`, `auth.login` `/login`, `auth.logout` POST `/logout`); `templates/base.html` with `<meta name="csrf-token">`, `<body data-auth="0|1">`, flash messages, `{% block content %}` / `{% block scripts %}`; `templates/error.html` (`code`); conftest `FreshUserClient`, `login(client, username="maria", password=PASSWORD)`, fixtures `user_client`, `admin` (username `boss`), `admin_client`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/conftest.py` with (final version — `FreshUserClient` is needed because the fixture's open app context makes every request share `g`, where Flask-Login caches the current user):

```python
"""Test fixtures: a throwaway migrated database per test, a small question
bank (tests/fixtures/bank), and helpers to create and log in users."""

from __future__ import annotations

import os

import pytest
from flask import g
from flask.testing import FlaskClient
from flask_migrate import upgrade

from app import create_app
from extensions import db
from ratelimit import limiter

FIXTURE_BANK = os.path.join(os.path.dirname(__file__), "fixtures", "bank")
PASSWORD = "secret-pass"


class FreshUserClient(FlaskClient):
    """Test client that forgets the cached Flask-Login user between requests.

    The ``app`` fixture keeps one app context open for the whole test, so
    every request shares its ``g`` — and Flask-Login caches the current user
    there. Without this, a second client would see the first client's login.
    """

    def open(self, *args, **kwargs):
        g.pop("_login_user", None)
        return super().open(*args, **kwargs)


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "DATA_DIR": FIXTURE_BANK,
    })
    application.test_client_class = FreshUserClient
    limiter.reset()
    with application.app_context():
        upgrade()
        yield application
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def bank_loaded(app):
    """Seed the 5-question fixture bank (categories alpha: 3, beta: 2)."""
    import bank
    bank.seed(FIXTURE_BANK)


def make_user(username="maria", password=PASSWORD, is_admin=False, active=True):
    from models import User
    user = User(username=username, is_admin=is_admin, active=active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login(client, username="maria", password=PASSWORD):
    return client.post("/login", data={"username": username, "password": password})


@pytest.fixture
def user(app):
    return make_user()


@pytest.fixture
def user_client(client, user):
    login(client)
    return client


@pytest.fixture
def admin(app):
    return make_user("boss", is_admin=True)


@pytest.fixture
def admin_client(client, admin):
    login(client, "boss")
    return client
```

`tests/test_auth.py` (create):

```python
import pytest
from sqlalchemy import select

from app import create_app
from extensions import db
from models import User
from ratelimit import RateLimiter
from tests.conftest import PASSWORD, login, make_user


def _register(client, username="Maria_1", password=PASSWORD, confirm=None):
    return client.post("/register", data={"username": username, "password": password,
                                          "confirm": confirm or password})


def test_rate_limiter_window():
    limiter = RateLimiter()
    assert limiter.hit("k", 2, 60, now=0)
    assert limiter.hit("k", 2, 60, now=1)
    assert not limiter.hit("k", 2, 60, now=2)
    assert limiter.hit("k", 2, 60, now=61)   # first hit expired
    assert limiter.hit("other", 2, 60, now=2)


def test_register_creates_lowercase_user_and_logs_in(client):
    response = _register(client)
    assert response.status_code == 302
    user = db.session.scalar(select(User))
    assert user.username == "maria_1"
    assert not user.is_admin
    assert "maria_1" in client.get("/").get_data(as_text=True)


@pytest.mark.parametrize("username,password,confirm,message", [
    ("ab", PASSWORD, None, "3–32"),
    ("μαρία", PASSWORD, None, "3–32"),
    ("maria", "short", None, "τουλάχιστον 8"),
    ("maria", PASSWORD, "different-pass", "δεν ταιριάζουν"),
])
def test_register_rejects_bad_input(client, username, password, confirm, message):
    response = _register(client, username, password, confirm)
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    assert db.session.scalar(select(User)) is None


def test_register_rejects_duplicate_username(client, user):
    response = _register(client, "MARIA")
    assert response.status_code == 400
    assert "χρησιμοποιείται ήδη" in response.get_data(as_text=True)


def test_login_and_logout(client, user):
    response = login(client)
    assert response.status_code == 302
    assert user.last_login_at is not None
    assert "Έξοδος (maria)" in client.get("/").get_data(as_text=True)
    client.post("/logout")
    assert "Σύνδεση" in client.get("/").get_data(as_text=True)


def test_login_wrong_password(client, user):
    response = login(client, password="nope-nope")
    assert response.status_code == 400
    assert "Λάθος όνομα χρήστη ή κωδικός" in response.get_data(as_text=True)


def test_login_disabled_user(client, app):
    make_user(active=False)
    response = login(client)
    assert response.status_code == 403
    assert "απενεργοποιηθεί" in response.get_data(as_text=True)


def test_login_follows_only_local_next(client, user):
    assert client.post("/login?next=/stats", data={"username": "maria", "password": PASSWORD}
                       ).headers["Location"] == "/stats"
    client.post("/logout")
    assert client.post("/login?next=//evil.example", data={"username": "maria", "password": PASSWORD}
                       ).headers["Location"] == "/"


def test_login_is_rate_limited(client, app, user):
    app.config["LOGIN_RATE"] = (2, 60)
    login(client, password="wrong-1")
    login(client, password="wrong-2")
    response = login(client)
    assert response.status_code == 429


def test_register_is_rate_limited(client, app):
    app.config["REGISTER_RATE"] = (1, 60)
    _register(client, "first")
    client.post("/logout")
    assert _register(client, "second").status_code == 429


def test_csrf_is_enforced_when_enabled(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'csrf.db'}",
                      "TESTING": True})
    response = app.test_client().post("/login", data={"username": "x", "password": "y"})
    assert response.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_auth.py`
Expected: FAIL — `E   ModuleNotFoundError: No module named 'ratelimit'`

- [ ] **Step 3: Implement the rate limiter and auth views**

`ratelimit.py` (create):

```python
"""A tiny in-memory sliding-window rate limiter for the public auth forms.

State is per process, so with N gunicorn workers the effective limit is up to
N times higher — good enough to blunt password guessing and sign-up spam
without adding Redis or another dependency.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float, now: float | None = None) -> bool:
        """Record one attempt for ``key``; False if it exceeds ``limit`` per ``window`` seconds."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
```

`views/__init__.py` (create):

```python
"""Blueprints: main (pages), auth, api (JSON), admin."""
```

`views/main.py` (create):

```python
"""Public pages: the quiz/browse app shell and the progress page."""

from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")
```

`views/auth.py` (create):

```python
"""Sign-up, login and logout."""

from __future__ import annotations

import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select

from extensions import db
from models import User, utcnow
from ratelimit import limiter

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
MIN_PASSWORD = 8
TOO_MANY = "Πάρα πολλές προσπάθειες. Δοκιμάστε ξανά σε λίγα λεπτά."


def _client_ip() -> str:
    return request.remote_addr or "unknown"


def _safe_next(target: str | None) -> str:
    """Only follow same-site relative paths after login (no open redirects)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.index")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    username = request.form.get("username", "").strip().lower()
    if request.method == "GET":
        return render_template("auth/register.html", username="")
    password = request.form.get("password", "")
    error, status = None, 400
    if not limiter.hit(f"register:{_client_ip()}", *current_app.config["REGISTER_RATE"]):
        error, status = TOO_MANY, 429
    elif not USERNAME_RE.match(username):
        error = "Το όνομα χρήστη πρέπει να έχει 3–32 λατινικούς χαρακτήρες, ψηφία ή . _ -"
    elif len(password) < MIN_PASSWORD:
        error = f"Ο κωδικός πρέπει να έχει τουλάχιστον {MIN_PASSWORD} χαρακτήρες."
    elif password != request.form.get("confirm", ""):
        error = "Οι κωδικοί δεν ταιριάζουν."
    elif db.session.scalar(select(User).filter_by(username=username)):
        error = "Το όνομα χρήστη χρησιμοποιείται ήδη."
    if error:
        flash(error, "danger")
        return render_template("auth/register.html", username=username), status
    user = User(username=username, last_login_at=utcnow())
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user, remember=True)
    flash("Καλώς ήρθατε! Η πρόοδός σας θα αποθηκεύεται πλέον.", "success")
    return redirect(url_for("main.index"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    username = request.form.get("username", "").strip().lower()
    if request.method == "GET":
        return render_template("auth/login.html", username="")
    error, status = None, 400
    if not limiter.hit(f"login:{_client_ip()}:{username}", *current_app.config["LOGIN_RATE"]):
        error, status = TOO_MANY, 429
    else:
        user = db.session.scalar(select(User).filter_by(username=username))
        if user is None or not user.check_password(request.form.get("password", "")):
            error = "Λάθος όνομα χρήστη ή κωδικός."
        elif not user.active:
            error, status = "Ο λογαριασμός έχει απενεργοποιηθεί.", 403
    if error:
        flash(error, "danger")
        return render_template("auth/login.html", username=username), status
    user.last_login_at = utcnow()
    db.session.commit()
    login_user(user, remember=True)
    return redirect(_safe_next(request.args.get("next")))


@bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.index"))
```

- [ ] **Step 4: Add the templates and stylesheet**

`templates/base.html` (create):

```html
<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="{{ csrf_token() }}">
  <title>{% block title %}ΑΣΕΠ 2027 — Τράπεζα Θεμάτων{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" rel="stylesheet">
  <link href="{{ url_for('static', filename='style.css') }}" rel="stylesheet">
</head>
<body data-auth="{{ '1' if current_user.is_authenticated else '0' }}">

<nav class="navbar navbar-expand navbar-dark bg-primary">
  <div class="container">
    <a class="navbar-brand fw-bold" href="{{ url_for('main.index') }}">
      <i class="fas fa-graduation-cap me-2"></i>ΑΣΕΠ 2027
    </a>
    <ul class="navbar-nav ms-auto align-items-center flex-wrap">
      {% if current_user.is_authenticated %}
        <li class="nav-item">
          <form method="post" action="{{ url_for('auth.logout') }}" class="d-inline">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button class="btn btn-link nav-link" type="submit">
              <i class="fas fa-sign-out-alt me-1"></i>Έξοδος ({{ current_user.username }})
            </button>
          </form>
        </li>
      {% else %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('auth.login') }}"><i class="fas fa-sign-in-alt me-1"></i>Σύνδεση</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('auth.register') }}"><i class="fas fa-user-plus me-1"></i>Εγγραφή</a></li>
      {% endif %}
    </ul>
  </div>
</nav>

{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    <div class="container mt-3">
      {% for category, message in messages %}
        <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
          {{ message }}
          <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Κλείσιμο"></button>
        </div>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}

{% block content %}{% endblock %}

<footer class="mt-5">
  <div class="container text-center">
    <p class="mb-1">
      Φτιαγμένο από <a href="https://github.com/skioulis" target="_blank" rel="noopener">Φώτης Φωτιάδης (skioulis)</a>
    </p>
    <small>Τα θέματα ανήκουν στο ΑΣΕΠ. Η εφαρμογή είναι για εκπαιδευτική χρήση.</small>
  </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

`templates/error.html` (create):

```html
{% extends "base.html" %}
{% block title %}{{ code }} — ΑΣΕΠ 2027{% endblock %}
{% block content %}
{% set texts = {
  403: "Δεν έχετε πρόσβαση σε αυτή τη σελίδα.",
  404: "Η σελίδα δεν βρέθηκε.",
  500: "Κάτι πήγε στραβά. Δοκιμάστε ξανά σε λίγο.",
} %}
<div class="container py-5 text-center">
  <h1 class="display-4 text-primary">{{ code }}</h1>
  <p class="lead">{{ texts.get(code, texts[500]) }}</p>
  <a class="btn btn-primary" href="{{ url_for('main.index') }}"><i class="fas fa-home me-1"></i>Αρχική</a>
</div>
{% endblock %}
```

`templates/index.html` (create):

```html
{% extends "base.html" %}
{% block content %}
<div class="container py-5 text-center">
  <h2 class="text-primary">ΑΣΕΠ 2027 — Τράπεζα Θεμάτων</h2>
  <p class="text-muted">Το quiz και η μελέτη ερωτήσεων προστίθενται στο επόμενο βήμα.</p>
</div>
{% endblock %}
```

`templates/auth/login.html` (create):

```html
{% extends "base.html" %}
{% block title %}Σύνδεση — ΑΣΕΠ 2027{% endblock %}
{% block content %}
<div class="container py-5" style="max-width: 420px">
  <h3 class="mb-4"><i class="fas fa-sign-in-alt me-2 text-primary"></i>Σύνδεση</h3>
  <form method="post">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="mb-3">
      <label class="form-label" for="username">Όνομα χρήστη</label>
      <input class="form-control" id="username" name="username" value="{{ username }}" required autofocus autocomplete="username">
    </div>
    <div class="mb-3">
      <label class="form-label" for="password">Κωδικός</label>
      <input class="form-control" id="password" name="password" type="password" required autocomplete="current-password">
    </div>
    <button class="btn btn-primary w-100" type="submit">Σύνδεση</button>
  </form>
  <p class="mt-3 text-center">Δεν έχετε λογαριασμό; <a href="{{ url_for('auth.register') }}">Εγγραφή</a></p>
</div>
{% endblock %}
```

`templates/auth/register.html` (create):

```html
{% extends "base.html" %}
{% block title %}Εγγραφή — ΑΣΕΠ 2027{% endblock %}
{% block content %}
<div class="container py-5" style="max-width: 420px">
  <h3 class="mb-2"><i class="fas fa-user-plus me-2 text-primary"></i>Εγγραφή</h3>
  <p class="text-muted mb-4">Με λογαριασμό αποθηκεύεται η πρόοδός σας: στατιστικά, λάθη και αναπάντητες ερωτήσεις.</p>
  <form method="post">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="mb-3">
      <label class="form-label" for="username">Όνομα χρήστη</label>
      <input class="form-control" id="username" name="username" value="{{ username }}" required autofocus
             pattern="[A-Za-z0-9_.\-]{3,32}" autocomplete="username">
      <div class="form-text">3–32 λατινικοί χαρακτήρες, ψηφία ή . _ -</div>
    </div>
    <div class="mb-3">
      <label class="form-label" for="password">Κωδικός</label>
      <input class="form-control" id="password" name="password" type="password" minlength="8" required autocomplete="new-password">
    </div>
    <div class="mb-3">
      <label class="form-label" for="confirm">Επιβεβαίωση κωδικού</label>
      <input class="form-control" id="confirm" name="confirm" type="password" minlength="8" required autocomplete="new-password">
    </div>
    <button class="btn btn-primary w-100" type="submit">Δημιουργία λογαριασμού</button>
  </form>
  <p class="mt-3 text-center">Έχετε ήδη λογαριασμό; <a href="{{ url_for('auth.login') }}">Σύνδεση</a></p>
</div>
{% endblock %}
```

`static/style.css` (create):

```css
/* Look carried over from the static site (index.html <style>). */
body { background-color: #f8f9fa; display: flex; flex-direction: column; min-height: 100vh; }
footer { margin-top: auto; }

.hero {
  background: linear-gradient(135deg, #0d6efd 0%, #0a58ca 100%);
  color: white;
  padding: 2rem 0 1.5rem;
}

.mode-card {
  cursor: pointer;
  transition: transform .15s, box-shadow .15s;
  border: 2px solid transparent;
}
.mode-card:hover { transform: translateY(-3px); box-shadow: 0 6px 20px rgba(0,0,0,.12); }

.question-card {
  border-left: 5px solid #0d6efd;
  margin-bottom: 1.25rem;
}

/* Question text may contain line breaks (tables, lists, poems). */
.qtext { white-space: pre-line; }

/* Browse mode */
.answer-btn {
  text-align: left;
  background: white;
  border: 1px solid #dee2e6;
  transition: background .15s, border-color .15s;
}
.answer-btn:hover:not(:disabled) { background: #f0f4ff; border-color: #0d6efd; }
.answer-btn.correct  { background: #d1e7dd; border-color: #0f5132; color: #0f5132; font-weight: 600; }
.answer-btn.wrong    { background: #f8d7da; border-color: #842029; color: #842029; }
.answer-btn.revealed { background: #d1e7dd; border-color: #0f5132; color: #0f5132; }
.answer-btn:disabled { opacity: 1; }

/* Quiz mode */
.quiz-option {
  text-align: left;
  background: white;
  border: 2px solid #dee2e6;
  border-radius: 8px;
  padding: .75rem 1rem;
  margin-bottom: .5rem;
  width: 100%;
  transition: background .15s, border-color .15s;
}
.quiz-option:hover:not(:disabled) { background: #f0f4ff; border-color: #0d6efd; }
.quiz-option.correct { border-color: #198754; background: #d1e7dd; color: #0f5132; font-weight: 600; }
.quiz-option.wrong   { border-color: #dc3545; background: #f8d7da; color: #842029; }

.progress-bar-quiz { height: 8px; border-radius: 4px; }

.score-circle {
  width: 140px; height: 140px;
  border-radius: 50%;
  border: 8px solid;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  margin: 0 auto 1.5rem;
  font-size: 2rem; font-weight: 700;
}

#categoryFilter { max-width: 340px; }
#poolFilter { max-width: 240px; }

.badge-category { font-size: .72rem; }

footer {
  background: linear-gradient(135deg, #0d6efd 0%, #0a58ca 100%);
  color: white;
  padding: 2rem 0 1.5rem;
}
footer a { color: #cfe2ff; }
```

- [ ] **Step 5: Register the blueprints and error pages**

In `app.py`, change `from flask import Flask` to `from flask import Flask, render_template`, then replace the end of `create_app` (from `# Import models…` through `return app`) with:

```python
    # Import models so their tables register with the metadata.
    import models  # noqa: F401
    from cli import register_cli
    from views import auth, main

    for blueprint in (main.bp, auth.bp):
        app.register_blueprint(blueprint)
    register_cli(app)

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def error_page(error):
        code = getattr(error, "code", 500)
        return render_template("error.html", code=code), code

    return app
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `32 passed`

- [ ] **Step 7: Commit**

```bash
git add ratelimit.py views templates static app.py tests
git commit -m "Add sign-up, login and logout with rate limiting" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: JSON API

**Files:**
- Create: `views/api.py`
- Modify: `app.py` (register `api.bp`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `Question.to_dict()`, `stats.latest_status`, `current_user`.
- Produces (all JSON; errors are `{"error": "<Greek message>"}`):
  - `GET /api/categories` → `[{slug, name, count}]` in position order
  - `GET /api/questions?category=<slug>&page=<n>` → `{items, page, pages, total}`, `api.PAGE_SIZE = 10`, page clamped to `1..pages`; unknown category → 404
  - `GET /api/quiz?category=<slug>&pool=all|unseen|wrong&size=25` → `{items, pool, available}` (random, unique, `size` clamped 1..100); `unseen`/`wrong` need login (401); unknown pool → 400
  - `POST /api/attempts` `{question_id, chosen: 0-3, mode: "quiz"|"browse"}` → 201 `{is_correct, correct}`; guest 401, unknown question 404, bad input 400. CSRF token via `X-CSRFToken` header.

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py` (create):

```python
from sqlalchemy import select

from extensions import db
from models import Attempt
from views import api


def _answer(client, qid, chosen, mode="quiz"):
    return client.post("/api/attempts", json={"question_id": qid, "chosen": chosen, "mode": mode})


def test_categories(client, bank_loaded):
    assert client.get("/api/categories").get_json() == [
        {"slug": "alpha", "name": "Άλφα Δίκαιο", "count": 3},
        {"slug": "beta", "name": "Βήτα Οικονομία", "count": 2},
    ]


def test_questions_all_and_by_category(client, bank_loaded):
    data = client.get("/api/questions").get_json()
    assert data["total"] == 5 and data["pages"] == 1
    assert [q["id"] for q in data["items"]] == ["alpha-1", "alpha-2", "alpha-3", "beta-1", "beta-2"]
    assert data["items"][0] == {"id": "alpha-1", "n": 1, "q": "Ποια είναι η πρωτεύουσα της Ελλάδας;",
                                "a": ["Θεσσαλονίκη", "Αθήνα", "Πάτρα", "Λάρισα"], "c": 1,
                                "category": "alpha"}
    beta = client.get("/api/questions?category=beta").get_json()
    assert [q["id"] for q in beta["items"]] == ["beta-1", "beta-2"]


def test_questions_pagination(client, bank_loaded, monkeypatch):
    monkeypatch.setattr(api, "PAGE_SIZE", 2)
    page3 = client.get("/api/questions?page=3").get_json()
    assert (page3["page"], page3["pages"], len(page3["items"])) == (3, 3, 1)
    clamped = client.get("/api/questions?page=99").get_json()
    assert clamped["page"] == 3
    assert client.get("/api/questions?page=abc").get_json()["page"] == 1


def test_unknown_category_is_404_json(client, bank_loaded):
    response = client.get("/api/questions?category=nope")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_quiz_returns_random_unique_questions(client, bank_loaded):
    data = client.get("/api/quiz?size=3").get_json()
    ids = [q["id"] for q in data["items"]]
    assert len(ids) == 3 == len(set(ids))
    assert data["available"] == 5
    everything = client.get("/api/quiz?category=alpha&size=25").get_json()
    assert sorted(q["id"] for q in everything["items"]) == ["alpha-1", "alpha-2", "alpha-3"]


def test_quiz_pools_need_login(client, bank_loaded):
    assert client.get("/api/quiz?pool=wrong").status_code == 401
    assert client.get("/api/quiz?pool=bogus").status_code == 400


def test_quiz_unseen_and_wrong_pools(user_client, bank_loaded):
    _answer(user_client, "alpha-1", 1)   # correct
    _answer(user_client, "alpha-2", 3)   # wrong
    unseen = user_client.get("/api/quiz?category=alpha&pool=unseen").get_json()
    assert [q["id"] for q in unseen["items"]] == ["alpha-3"]
    wrong = user_client.get("/api/quiz?category=alpha&pool=wrong").get_json()
    assert [q["id"] for q in wrong["items"]] == ["alpha-2"]


def test_attempt_requires_login(client, bank_loaded):
    assert _answer(client, "alpha-1", 1).status_code == 401


def test_attempt_is_recorded(user_client, bank_loaded, user):
    response = _answer(user_client, "alpha-1", 0, mode="browse")
    assert response.status_code == 201
    assert response.get_json() == {"is_correct": False, "correct": 1}
    attempt = db.session.scalar(select(Attempt))
    assert (attempt.user_id, attempt.question_id, attempt.chosen, attempt.mode) == \
           (user.id, "alpha-1", 0, "browse")


def test_attempt_validation(user_client, bank_loaded):
    assert _answer(user_client, "nope-1", 0).status_code == 404
    assert _answer(user_client, 7, 0).status_code == 404
    assert _answer(user_client, "alpha-1", 4).status_code == 400
    assert _answer(user_client, "alpha-1", True).status_code == 400
    assert _answer(user_client, "alpha-1", 0, mode="exam").status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api.py`
Expected: FAIL — `E   ImportError: cannot import name 'api' from 'views'`

- [ ] **Step 3: Implement the API**

`views/api.py` (create):

```python
"""JSON API used by static/app.js: categories, browse pages, quizzes, answers.

Questions are sent with their correct index (as the static site did): this is a
study tool, so hiding answers from the browser is not a goal.
"""

from __future__ import annotations

import random

from flask import Blueprint, abort, jsonify, make_response, request
from flask_login import current_user
from sqlalchemy import func, select

from extensions import db
from models import Attempt, Category, Question
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
    category = _category_arg()
    pool = request.args.get("pool", "all")
    if pool not in POOLS:
        _fail(400, "Άγνωστο σύνολο ερωτήσεων.")
    size = min(max(request.args.get("size", 25, type=int), 1), 100)
    candidates = db.session.scalars(_questions(category)).all()
    if pool != "all":
        _require_login()
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
    data = request.get_json(silent=True) or {}
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
```

In `app.py`, register the blueprint — the end of `create_app` becomes:

```python
    # Import models so their tables register with the metadata.
    import models  # noqa: F401
    from cli import register_cli
    from views import api, auth, main

    for blueprint in (main.bp, auth.bp, api.bp):
        app.register_blueprint(blueprint)
    register_cli(app)

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def error_page(error):
        code = getattr(error, "code", 500)
        return render_template("error.html", code=code), code

    return app
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `42 passed`

- [ ] **Step 5: Commit**

```bash
git add views/api.py app.py tests/test_api.py
git commit -m "Add JSON API for categories, browse, quiz and attempts" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Quiz/browse frontend and progress page

**Files:**
- Create: `templates/stats.html`, `static/app.js`, `.claude/launch.json` (overwrite)
- Modify: `views/main.py` (add `/stats`), `templates/index.html` (full app shell), `templates/base.html` (Πρόοδος link)
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: the Task 5 API, `stats.category_stats` / `totals`, `base.html` blocks.
- Produces: endpoint `main.stats` (`/stats`, login required); `index.html` element ids used by `app.js`: `categoryFilter`, `poolFilter` (logged-in only), `btnQuiz`, `btnBrowse`, `messageBox`, `loading`, `welcome`, `quizContainer`, `browseContainer`, `browseQuestions`, `pagination`; deep links `/?category=<slug>&pool=wrong|unseen&start=quiz|browse` (used by the stats page).

- [ ] **Step 1: Write the failing tests**

`tests/test_pages.py` (create):

```python
from extensions import db
from models import Attempt


def test_index_page_has_app_shell(client, bank_loaded):
    html = client.get("/").get_data(as_text=True)
    assert 'name="csrf-token"' in html
    assert 'id="categoryFilter"' in html
    assert "app.js" in html
    assert 'id="poolFilter"' not in html       # pools only for logged-in users


def test_index_shows_pool_filter_when_logged_in(user_client, bank_loaded):
    html = user_client.get("/").get_data(as_text=True)
    assert 'id="poolFilter"' in html
    assert 'data-auth="1"' in html


def test_stats_requires_login(client):
    response = client.get("/stats")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


def test_stats_page_shows_progress(user_client, bank_loaded, user):
    db.session.add(Attempt(user_id=user.id, question_id="alpha-2", chosen=1,
                           is_correct=False, mode="quiz"))
    db.session.commit()
    html = user_client.get("/stats").get_data(as_text=True)
    assert "Άλφα Δίκαιο" in html
    assert "1/3" in html
    assert "pool=wrong" in html and "category=alpha" in html


def test_unknown_page_uses_error_template(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert "Η σελίδα δεν βρέθηκε" in response.get_data(as_text=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pages.py`
Expected: FAIL — `4 failed, 1 passed`

- [ ] **Step 3: Add the stats route and pages**

`views/main.py` (replace):

```python
"""Public pages: the quiz/browse app shell and the progress page."""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from stats import category_stats, totals

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/stats")
@login_required
def stats():
    rows = category_stats(current_user.id)
    return render_template("stats.html", rows=rows, total=totals(rows))
```

`templates/stats.html` (create):

```html
{% extends "base.html" %}
{% block title %}Πρόοδος — ΑΣΕΠ 2027{% endblock %}
{% macro pct_badge(pct) -%}
  {%- if pct is none -%}<span class="text-muted">—</span>
  {%- else -%}<span class="badge {{ 'bg-success' if pct >= 80 else 'bg-primary' if pct >= 60 else 'bg-warning text-dark' if pct >= 40 else 'bg-danger' }}">{{ pct }}%</span>
  {%- endif -%}
{%- endmacro %}
{% block content %}
<div class="container py-4">
  <h3 class="mb-3"><i class="fas fa-chart-bar me-2 text-primary"></i>Η πρόοδός μου</h3>

  <div class="row g-3 mb-4 text-center">
    <div class="col-6 col-md-3"><div class="card p-3"><div class="fs-3 fw-bold">{{ total.answered }}/{{ total.total }}</div><small class="text-muted">Απαντημένες</small></div></div>
    <div class="col-6 col-md-3"><div class="card p-3"><div class="fs-3 fw-bold text-success">{{ total.correct }}</div><small class="text-muted">Σωστές (τελευταία απάντηση)</small></div></div>
    <div class="col-6 col-md-3"><div class="card p-3"><div class="fs-3 fw-bold text-danger">{{ total.wrong }}</div><small class="text-muted">Λάθος (τελευταία απάντηση)</small></div></div>
    <div class="col-6 col-md-3"><div class="card p-3"><div class="fs-3 fw-bold">{{ pct_badge(total.pct) }}</div><small class="text-muted">Ποσοστό επιτυχίας</small></div></div>
  </div>

  <div class="card">
    <div class="table-responsive">
      <table class="table table-hover align-middle mb-0">
        <thead class="table-light">
          <tr><th>Κατηγορία</th><th class="text-center">Απαντημένες</th><th class="text-center">Σωστές</th><th class="text-center">Λάθος</th><th class="text-center">%</th><th></th></tr>
        </thead>
        <tbody>
        {% for row in rows %}
          <tr>
            <td>{{ row.name }}</td>
            <td class="text-center">{{ row.answered }}/{{ row.total }}</td>
            <td class="text-center text-success">{{ row.correct }}</td>
            <td class="text-center text-danger">{{ row.wrong }}</td>
            <td class="text-center">{{ pct_badge(row.pct) }}</td>
            <td class="text-end text-nowrap">
              {% if row.wrong %}
                <a class="btn btn-sm btn-outline-danger" href="{{ url_for('main.index', category=row.slug, pool='wrong', start='quiz') }}"><i class="fas fa-redo me-1"></i>Λάθη</a>
              {% endif %}
              {% if row.answered < row.total %}
                <a class="btn btn-sm btn-outline-primary" href="{{ url_for('main.index', category=row.slug, pool='unseen', start='quiz') }}"><i class="fas fa-eye-slash me-1"></i>Αναπάντητες</a>
              {% endif %}
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endblock %}
```

`templates/index.html` (replace):

```html
{% extends "base.html" %}
{% block content %}
<div class="hero">
  <div class="container d-flex flex-column align-items-center text-center">
    <p class="mb-3 opacity-75">Επιλέξτε κατηγορία και τρόπο μελέτης</p>

    <div class="mb-3 w-100 d-flex flex-wrap justify-content-center gap-2">
      <select id="categoryFilter" class="form-select">
        <option value="">Όλες οι κατηγορίες</option>
      </select>
      {% if current_user.is_authenticated %}
      <select id="poolFilter" class="form-select">
        <option value="all">Όλες οι ερωτήσεις</option>
        <option value="unseen">Μόνο αναπάντητες</option>
        <option value="wrong">Μόνο όσες έκανα λάθος</option>
      </select>
      {% endif %}
    </div>

    <div class="d-flex flex-wrap justify-content-center gap-2">
      <button id="btnQuiz" class="btn btn-light fw-semibold">
        <i class="fas fa-dice me-2"></i>25 Τυχαίες Ερωτήσεις
      </button>
      <button id="btnBrowse" class="btn btn-outline-light fw-semibold">
        <i class="fas fa-list me-2"></i>Όλες οι Ερωτήσεις
      </button>
    </div>
  </div>
</div>

<div class="container mt-4">
  <div id="messageBox"></div>

  <div id="loading" class="text-center py-5 d-none">
    <div class="spinner-border text-primary" role="status"></div>
    <p class="mt-2 text-muted">Φόρτωση ερωτήσεων…</p>
  </div>

  <div id="welcome">
    {% if not current_user.is_authenticated %}
    <div class="alert alert-info text-center">
      <i class="fas fa-info-circle me-1"></i>
      <a href="{{ url_for('auth.register') }}">Κάντε εγγραφή</a> ή <a href="{{ url_for('auth.login') }}">συνδεθείτε</a>
      για να αποθηκεύεται η πρόοδός σας.
    </div>
    {% endif %}
    <div class="row g-4 justify-content-center">
      <div class="col-md-5">
        <div class="card mode-card h-100 text-center p-3" onclick="document.getElementById('btnQuiz').click()">
          <div class="card-body">
            <i class="fas fa-dice fa-3x text-primary mb-3"></i>
            <h5 class="card-title">Quiz Mode</h5>
            <p class="card-text text-muted">25 τυχαίες ερωτήσεις. Απαντήστε και δείτε το σκορ σας.</p>
          </div>
        </div>
      </div>
      <div class="col-md-5">
        <div class="card mode-card h-100 text-center p-3" onclick="document.getElementById('btnBrowse').click()">
          <div class="card-body">
            <i class="fas fa-book-open fa-3x text-success mb-3"></i>
            <h5 class="card-title">Μελέτη</h5>
            <p class="card-text text-muted">Περιηγηθείτε σε όλες τις ερωτήσεις και ελέγξτε τις απαντήσεις σας.</p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div id="quizContainer" class="d-none"></div>

  <div id="browseContainer" class="d-none">
    <div id="browseQuestions"></div>
    <div id="pagination" class="d-flex justify-content-center mt-4"></div>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='app.js') }}"></script>
{% endblock %}
```

In `templates/base.html`, add the progress link as the first item inside `{% if current_user.is_authenticated %}` in the navbar:

```html
        <li class="nav-item"><a class="nav-link" href="{{ url_for('main.stats') }}"><i class="fas fa-chart-bar me-1"></i>Πρόοδος</a></li>
```

- [ ] **Step 4: Port the frontend script**

Ported from `~/air/Asep_2027/app.js`: same quiz/review/browse UI, but data comes from the API, options are labelled α/β/γ/δ, question numbers show the PDF number, and logged-in answers are POSTed to `/api/attempts`.

`static/app.js` (create):

```javascript
'use strict';

// Quiz + browse UI. Ported from the static site; questions now come from the
// JSON API, and answers are recorded for logged-in users.

// ── Category colour map ───────────────────────────────────────────────────────
const CATEGORY_COLORS = {
  'Διοικητικό Δίκαιο':                                                      'bg-success',
  'Συνταγματικό Δίκαιο':                                                    'bg-primary',
  'Οικονομικές Επιστήμες':                                                  'bg-warning text-dark',
  'Πληροφορική και Ψηφιακή Διακυβέρνηση':                                   'bg-dark',
  'Ευρωπαϊκοί Θεσμοί και Δίκαιο':                                          'bg-danger',
  'Διοίκηση Ανθρώπινου Δυναμικού':                                          'bg-info text-dark',
  'Σύγχρονη Ιστορία της Ελλάδος (1875-σήμερα)':                            'bg-secondary',
  'Κώδικας Κατάστασης Πολιτικών Διοικητικών Υπαλλήλων και Υπαλλήλων Ν.Π.Δ.Δ.': 'bg-secondary',
  'Διοίκηση Επιχειρήσεων και Οργανισμών':                                   'bg-primary',
  'Κώδικας συμπεριφοράς δημοσίων Υπαλλήλων':                               'bg-success',
  'Γενικός Κανονισμός για την Προστασία των Δεδομένων (GDPR)':              'bg-danger',
};
const LETTERS = ['α', 'β', 'γ', 'δ'];
const QUIZ_SIZE = 25;
const LOGGED_IN = document.body.dataset.auth === '1';
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]').content;

function categoryBadge(name) {
  const cls = CATEGORY_COLORS[name] || 'bg-secondary';
  return `<span class="badge badge-category ${cls} me-1">${escHtml(name)}</span>`;
}

// ── State ─────────────────────────────────────────────────────────────────────
let catBySlug = {};       // slug → { slug, name, count }

// Quiz state
let quizSet = [];
let quizIndex = 0;
let quizAnswers = {};     // question id → chosen option index

// Browse state
let browse = { page: 1, pages: 1, total: 0, items: [] };
let browseChoice = {};    // question id → chosen index, or -1 when only revealed

// ── DOM refs ──────────────────────────────────────────────────────────────────
const elLoading        = document.getElementById('loading');
const elWelcome        = document.getElementById('welcome');
const elMessage        = document.getElementById('messageBox');
const elQuiz           = document.getElementById('quizContainer');
const elBrowse         = document.getElementById('browseContainer');
const elBrowseQ        = document.getElementById('browseQuestions');
const elPagination     = document.getElementById('pagination');
const elCategoryFilter = document.getElementById('categoryFilter');
const elPoolFilter     = document.getElementById('poolFilter');   // only when logged in
const btnQuiz          = document.getElementById('btnQuiz');
const btnBrowse        = document.getElementById('btnBrowse');

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(path, options = {}) {
  const res = await fetch(path, { credentials: 'same-origin', ...options });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

function recordAttempt(q, chosen, mode) {
  if (!LOGGED_IN) return;
  api('/api/attempts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
    body: JSON.stringify({ question_id: q.id, chosen, mode }),
  }).catch(err => console.warn('Η απάντηση δεν αποθηκεύτηκε:', err.message));
}

function toQuestion(item) {
  const cat = catBySlug[item.category];
  return { id: item.id, n: item.n, question: item.q, answers: item.a,
           correct: item.c, category: cat ? cat.name : item.category };
}

function selectedParams(extra = {}) {
  const params = new URLSearchParams(extra);
  if (elCategoryFilter.value) params.set('category', elCategoryFilter.value);
  return params;
}

// ── Boot ──────────────────────────────────────────────────────────────────────
async function init() {
  showSection('loading');
  let categories;
  try {
    categories = await api('/api/categories');
  } catch (e) {
    showSection('welcome');
    showMessage(`Αδυναμία φόρτωσης κατηγοριών: ${escHtml(e.message)}`);
    return;
  }
  categories.forEach(c => { catBySlug[c.slug] = c; });
  populateCategoryFilter(categories);

  // Deep links from the stats page, e.g. /?category=x&pool=wrong&start=quiz
  const params = new URLSearchParams(window.location.search);
  if (catBySlug[params.get('category')]) elCategoryFilter.value = params.get('category');
  if (elPoolFilter && ['all', 'unseen', 'wrong'].includes(params.get('pool'))) {
    elPoolFilter.value = params.get('pool');
  }
  showSection('welcome');
  if (params.get('start') === 'quiz') startQuiz();
  else if (params.get('start') === 'browse') startBrowse(1);
}

function populateCategoryFilter(categories) {
  categories
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name, 'el'))
    .forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.slug;
      opt.textContent = `${c.name} (${c.count})`;
      elCategoryFilter.appendChild(opt);
    });
}

// ── Section visibility & messages ─────────────────────────────────────────────
function showSection(name) {
  elLoading.classList.toggle('d-none', name !== 'loading');
  elWelcome.classList.toggle('d-none', name !== 'welcome');
  elQuiz.classList.toggle('d-none', name !== 'quiz');
  elBrowse.classList.toggle('d-none', name !== 'browse');
  if (name !== 'welcome') elMessage.innerHTML = '';
}

function showMessage(html, kind = 'danger') {
  elMessage.innerHTML = `<div class="alert alert-${kind}">${html}</div>`;
}

// ── QUIZ MODE ─────────────────────────────────────────────────────────────────
async function startQuiz() {
  const pool = elPoolFilter ? elPoolFilter.value : 'all';
  showSection('loading');
  let data;
  try {
    data = await api('/api/quiz?' + selectedParams({ size: QUIZ_SIZE, pool }));
  } catch (e) {
    showSection('welcome');
    showMessage(`Αδυναμία φόρτωσης quiz: ${escHtml(e.message)}`);
    return;
  }
  if (data.items.length === 0) {
    showSection('welcome');
    const empty = {
      wrong: 'Δεν υπάρχουν ερωτήσεις που απαντήσατε λάθος εδώ. Μπράβο!',
      unseen: 'Έχετε ήδη απαντήσει όλες τις ερωτήσεις εδώ.',
      all: 'Δεν βρέθηκαν ερωτήσεις για αυτή την κατηγορία.',
    };
    showMessage(empty[data.pool] || empty.all, 'info');
    return;
  }
  quizSet = data.items.map(toQuestion);
  quizIndex = 0;
  quizAnswers = {};
  showSection('quiz');
  renderQuizQuestion();
}

function renderQuizQuestion() {
  const total = quizSet.length;
  const q = quizSet[quizIndex];
  const chosen = quizAnswers[q.id];
  const answered = chosen !== undefined;
  const pct = Math.round(((quizIndex + (answered ? 1 : 0)) / total) * 100);

  const optionsHtml = q.answers.map((text, i) => {
    let cls = 'quiz-option';
    if (answered && i === q.correct) cls += ' correct';
    else if (answered && i === chosen) cls += ' wrong';
    return `<button class="${cls}" ${answered ? 'disabled' : ''} onclick="chooseAnswer(${i})">
      <strong>${LETTERS[i]}.</strong> ${escHtml(text)}
    </button>`;
  }).join('');

  let feedbackHtml = '';
  if (answered) {
    const correct = chosen === q.correct;
    feedbackHtml = `<div class="alert ${correct ? 'alert-success' : 'alert-danger'} mt-3 mb-0">
      ${correct
        ? '<i class="fas fa-check-circle me-2"></i>Σωστά!'
        : `<i class="fas fa-times-circle me-2"></i>Λάθος! Σωστή απάντηση: <strong>${LETTERS[q.correct]}</strong>`}
    </div>`;
  }

  const isLast = quizIndex === total - 1;
  elQuiz.innerHTML = `
    <div class="mb-3">
      <div class="d-flex justify-content-between align-items-center mb-1">
        <small class="text-muted">Ερώτηση ${quizIndex + 1} / ${total}</small>
        <small class="text-muted">${pct}%</small>
      </div>
      <div class="progress progress-bar-quiz">
        <div class="progress-bar" style="width:${pct}%"></div>
      </div>
    </div>
    <div class="card question-card">
      <div class="card-header">${categoryBadge(q.category)}
        <span class="badge bg-secondary ms-1">#${q.n}</span>
      </div>
      <div class="card-body">
        <h5 class="card-title mb-4 qtext">${escHtml(q.question)}</h5>
        ${optionsHtml}
        ${feedbackHtml}
        <div class="d-flex justify-content-between mt-4">
          <button class="btn btn-outline-secondary" onclick="quizNav(-1)" ${quizIndex === 0 ? 'disabled' : ''}>
            <i class="fas fa-arrow-left me-1"></i>Προηγούμενο
          </button>
          <button class="btn btn-primary" onclick="quizNav(1)">
            ${isLast
              ? 'Αποτελέσματα <i class="fas fa-flag-checkered ms-1"></i>'
              : 'Επόμενο <i class="fas fa-arrow-right ms-1"></i>'}
          </button>
        </div>
      </div>
    </div>`;
}

function chooseAnswer(i) {
  const q = quizSet[quizIndex];
  if (quizAnswers[q.id] !== undefined) return;
  quizAnswers[q.id] = i;
  recordAttempt(q, i, 'quiz');
  renderQuizQuestion();
}

function quizNav(dir) {
  const next = quizIndex + dir;
  if (next < 0) return;
  if (next >= quizSet.length) { renderQuizResults(); return; }
  quizIndex = next;
  renderQuizQuestion();
}

function renderQuizResults() {
  const total = quizSet.length;
  const correct = quizSet.filter(q => quizAnswers[q.id] === q.correct).length;
  const pct = Math.round((correct / total) * 100);
  const color = pct >= 80 ? '#198754' : pct >= 60 ? '#0d6efd' : pct >= 40 ? '#fd7e14' : '#dc3545';

  const reviewRows = quizSet.map((q, i) => {
    const chosen = quizAnswers[q.id];
    const icon = chosen === undefined
      ? '<i class="fas fa-minus text-muted"></i>'
      : chosen === q.correct
        ? '<i class="fas fa-check text-success"></i>'
        : '<i class="fas fa-times text-danger"></i>';
    return `<tr>
      <td>${i + 1}</td>
      <td>${escHtml(q.question.substring(0, 70))}${q.question.length > 70 ? '…' : ''}</td>
      <td>${chosen === undefined ? '—' : LETTERS[chosen]}</td>
      <td>${LETTERS[q.correct]}</td>
      <td class="text-center">${icon}</td>
    </tr>`;
  }).join('');

  elQuiz.innerHTML = `
    <div class="card mb-4">
      <div class="card-header bg-primary text-white">
        <h5 class="mb-0"><i class="fas fa-trophy me-2"></i>Αποτελέσματα Quiz</h5>
      </div>
      <div class="card-body text-center py-4">
        <div class="score-circle" style="border-color:${color}; color:${color};">
          <div>${correct}/${total}</div>
          <div style="font-size:1rem;font-weight:400">${pct}%</div>
        </div>
        <div class="progress mb-4" style="height:14px; max-width:400px; margin:0 auto;">
          <div class="progress-bar" style="width:${pct}%; background:${color}"></div>
        </div>
        <div class="d-flex gap-2 justify-content-center flex-wrap">
          <button class="btn btn-primary" onclick="startQuiz()"><i class="fas fa-redo me-2"></i>Νέο Quiz</button>
          <button class="btn btn-outline-secondary" onclick="renderReview()"><i class="fas fa-search me-2"></i>Ανασκόπηση Απαντήσεων</button>
          ${LOGGED_IN ? '<a class="btn btn-outline-success" href="/stats"><i class="fas fa-chart-bar me-2"></i>Η πρόοδός μου</a>' : ''}
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><strong>Σύνοψη</strong></div>
      <div class="table-responsive">
        <table class="table table-sm table-hover mb-0">
          <thead class="table-light">
            <tr><th>#</th><th>Ερώτηση</th><th>Απάντησα</th><th>Σωστή</th><th></th></tr>
          </thead>
          <tbody>${reviewRows}</tbody>
        </table>
      </div>
    </div>`;
}

function renderReview() {
  const html = quizSet.map((q, i) => {
    const chosen = quizAnswers[q.id];
    const opts = q.answers.map((text, k) => {
      let cls = 'list-group-item';
      if (k === q.correct) cls += ' list-group-item-success';
      else if (k === chosen) cls += ' list-group-item-danger';
      return `<div class="${cls}">
        <strong>${LETTERS[k]}.</strong> ${escHtml(text)}
        ${k === q.correct ? '<i class="fas fa-check ms-2 text-success"></i>' : ''}
        ${k === chosen && k !== q.correct ? '<i class="fas fa-times ms-2 text-danger"></i>' : ''}
      </div>`;
    }).join('');
    const badge = chosen === q.correct
      ? '<span class="badge bg-success ms-2">Σωστή</span>'
      : chosen === undefined
        ? '<span class="badge bg-secondary ms-2">Αναπάντητη</span>'
        : '<span class="badge bg-danger ms-2">Λάθος</span>';
    return `<div class="card question-card mb-3">
      <div class="card-header d-flex align-items-center flex-wrap gap-1">
        ${categoryBadge(q.category)}
        <span class="badge bg-secondary">#${q.n}</span>
        <span class="badge bg-light text-dark">Ερ. ${i + 1}</span>
        ${badge}
      </div>
      <div class="card-body">
        <h6 class="card-title qtext">${escHtml(q.question)}</h6>
        <div class="list-group mt-2">${opts}</div>
      </div>
    </div>`;
  }).join('');

  elQuiz.innerHTML = `
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <h5 class="mb-0">Ανασκόπηση Απαντήσεων</h5>
      <div class="d-flex gap-2">
        <button class="btn btn-sm btn-outline-secondary" onclick="renderQuizResults()">
          <i class="fas fa-arrow-left me-1"></i>Πίσω στα Αποτελέσματα
        </button>
        <button class="btn btn-sm btn-primary" onclick="startQuiz()"><i class="fas fa-redo me-1"></i>Νέο Quiz</button>
      </div>
    </div>
    ${html}`;
}

// ── BROWSE MODE ───────────────────────────────────────────────────────────────
async function startBrowse(page) {
  showSection('loading');
  let data;
  try {
    data = await api('/api/questions?' + selectedParams({ page }));
  } catch (e) {
    showSection('welcome');
    showMessage(`Αδυναμία φόρτωσης ερωτήσεων: ${escHtml(e.message)}`);
    return;
  }
  browse = { page: data.page, pages: data.pages, total: data.total, items: data.items.map(toQuestion) };
  browseChoice = {};
  showSection('browse');
  elBrowseQ.innerHTML = `<p class="text-muted small">${data.total} ερωτήσεις — σελίδα ${data.page} / ${data.pages}</p>`
    + browse.items.map(browseCard).join('');
  renderPagination();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function browseCard(q) {
  const choice = browseChoice[q.id];
  const done = choice !== undefined;
  const opts = q.answers.map((text, i) => {
    let cls = 'answer-btn btn w-100 mb-1 text-start';
    if (done && i === q.correct) cls += choice === -1 ? ' revealed' : ' correct';
    else if (done && i === choice) cls += ' wrong';
    return `<button class="${cls}" ${done ? 'disabled' : ''} onclick="browseAnswer('${q.id}', ${i})">
      <strong>${LETTERS[i]}.</strong> ${escHtml(text)}
      ${done && i === q.correct ? '<i class="fas fa-check ms-2"></i>' : ''}
    </button>`;
  }).join('');

  let status = '';
  if (choice === -1) status = '<span class="badge bg-success ms-auto"><i class="fas fa-eye me-1"></i>Αποκαλύφθηκε</span>';
  else if (done && choice === q.correct) status = '<span class="badge bg-success ms-auto"><i class="fas fa-check me-1"></i>Σωστά</span>';
  else if (done) status = '<span class="badge bg-danger ms-auto"><i class="fas fa-times me-1"></i>Λάθος</span>';

  return `<div class="card question-card" id="bq-${q.id}">
    <div class="card-header d-flex align-items-center flex-wrap gap-1">
      ${categoryBadge(q.category)}
      <span class="badge bg-secondary">#${q.n}</span>
      ${status}
    </div>
    <div class="card-body">
      <h6 class="card-title mb-3 qtext">${escHtml(q.question)}</h6>
      <div>${opts}</div>
      ${done ? '' : `<button class="btn btn-sm btn-outline-primary mt-2" onclick="browseAnswer('${q.id}', -1)">
          <i class="fas fa-eye me-1"></i>Εμφάνιση σωστής απάντησης</button>`}
    </div>
  </div>`;
}

// i = chosen option index, or -1 to just reveal the answer (not recorded).
function browseAnswer(qId, i) {
  const q = browse.items.find(x => x.id === qId);
  if (!q || browseChoice[qId] !== undefined) return;
  browseChoice[qId] = i;
  if (i >= 0) recordAttempt(q, i, 'browse');
  document.getElementById(`bq-${qId}`).outerHTML = browseCard(q);
}

function renderPagination() {
  const { page, pages } = browse;
  if (pages <= 1) { elPagination.innerHTML = ''; return; }

  const maxVisible = 5;
  let start = Math.max(1, page - Math.floor(maxVisible / 2));
  const end = Math.min(pages, start + maxVisible - 1);
  if (end - start + 1 < maxVisible) start = Math.max(1, end - maxVisible + 1);

  let html = '<ul class="pagination flex-wrap">';
  html += pageItem('&laquo;', page - 1, page === 1);
  if (start > 1) {
    html += pageItem('1', 1);
    if (start > 2) html += '<li class="page-item disabled"><span class="page-link">…</span></li>';
  }
  for (let i = start; i <= end; i++) html += pageItem(i, i, false, i === page);
  if (end < pages) {
    if (end < pages - 1) html += '<li class="page-item disabled"><span class="page-link">…</span></li>';
    html += pageItem(pages, pages);
  }
  html += pageItem('&raquo;', page + 1, page === pages);
  html += '</ul>';

  elPagination.innerHTML = html;
  elPagination.querySelectorAll('.page-link[data-page]').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      const p = parseInt(el.dataset.page, 10);
      if (!isNaN(p) && p >= 1 && p <= pages) startBrowse(p);
    });
  });
}

function pageItem(label, page, disabled = false, active = false) {
  const cls = `page-item${disabled ? ' disabled' : ''}${active ? ' active' : ''}`;
  return `<li class="${cls}"><a class="page-link" href="#" data-page="${page}">${label}</a></li>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Event listeners ───────────────────────────────────────────────────────────
btnQuiz.addEventListener('click', startQuiz);
btnBrowse.addEventListener('click', () => startBrowse(1));
elCategoryFilter.addEventListener('change', () => {
  // If a mode is already active, restart it with the new filter
  if (!elQuiz.classList.contains('d-none')) startQuiz();
  else if (!elBrowse.classList.contains('d-none')) startBrowse(1);
});
if (elPoolFilter) {
  elPoolFilter.addEventListener('change', () => {
    if (!elQuiz.classList.contains('d-none')) startQuiz();
  });
}

// Expose for inline onclick handlers
window.chooseAnswer      = chooseAnswer;
window.quizNav           = quizNav;
window.startQuiz         = startQuiz;
window.renderReview      = renderReview;
window.renderQuizResults = renderQuizResults;
window.browseAnswer      = browseAnswer;

init();
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `47 passed`

- [ ] **Step 6: Check it in the browser**

`.claude/launch.json` (replace):

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "asep-dev",
      "runtimeExecutable": "sh",
      "runtimeArgs": [
        "-c",
        "FLASK_APP=app .venv/bin/flask db upgrade && FLASK_APP=app .venv/bin/flask seed && FLASK_APP=app exec .venv/bin/flask run --port 8001"
      ],
      "port": 8001
    }
  ]
}
```

Start `asep-dev` with the preview tool and verify at `http://localhost:8001`:
1. Guest: the category list shows 11 categories with counts; **25 Τυχαίες Ερωτήσεις** starts a quiz; answering colours the options and shows Σωστά/Λάθος; results and review render.
2. Register a test user (any name, password ≥ 8): the pool selector appears; answer a quiz question and confirm `POST /api/attempts → 201` in the network log.
3. Browse **Οικονομικές Επιστήμες** page 15: question #150 shows the tax table on separate lines; clicking an option marks it wrong/right.
4. `/stats` shows the answered question and the **Λάθη** / **Αναπάντητες** shortcuts start the right quiz.
5. No errors in the browser console.

`asep.db` is git-ignored (`*.db`).

- [ ] **Step 7: Commit**

```bash
git add views/main.py templates static/app.js .claude/launch.json tests/test_pages.py
git commit -m "Add quiz and browse frontend with progress page" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Admin — edit, add and delete questions

**Files:**
- Create: `views/admin.py`, `templates/admin/_nav.html`, `templates/admin/questions.html`, `templates/admin/question_form.html`
- Modify: `app.py` (register `admin.bp`), `templates/base.html` (Διαχείριση link)
- Test: `tests/test_admin_questions.py`

**Interfaces:**
- Consumes: `login_manager.unauthorized()`, models, `base.html`.
- Produces: blueprint `admin.bp` at `/admin` (guests → login redirect, non-admins → 403) with endpoints `admin.home` (`/admin/` → redirect), `admin.questions` (`/admin/questions?category=&q=&page=`, 25/page, accent-insensitive search via `_fold`), `admin.new_question` (`/admin/questions/new?category=<slug>`, id `<slug>-<max n + 1>`), `admin.edit_question` (`/admin/questions/<qid>`), `admin.delete_question` (POST `/admin/questions/<qid>/delete`); helpers `_categories()`, `_category_or_404(slug)`; `templates/admin/_nav.html` driven by a `tabs` list of `(endpoint, icon, label)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_admin_questions.py` (create):

```python
from sqlalchemy import func, select

from extensions import db
from models import Attempt, Question


def _form(text="Νέα ερώτηση;", options=("α1", "β1", "γ1", "δ1"), correct=2):
    data = {"text": text, "correct": correct}
    data.update({f"a{i}": opt for i, opt in enumerate(options)})
    return data


def test_guest_is_sent_to_login(client):
    response = client.get("/admin/questions")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


def test_regular_user_is_forbidden(user_client):
    assert user_client.get("/admin/questions").status_code == 403


def test_admin_link_only_for_admins(user_client, bank_loaded):
    assert "/admin/" not in user_client.get("/").get_data(as_text=True)


def test_question_list_and_filters(admin_client, bank_loaded):
    html = admin_client.get("/admin/questions").get_data(as_text=True)
    assert "5 ερωτήσεις" in html
    html = admin_client.get("/admin/questions?category=beta").get_data(as_text=True)
    assert "2 ερωτήσεις" in html and "beta-1" in html and "alpha-1" not in html


def test_search_ignores_case_and_greek_accents(admin_client, bank_loaded):
    html = admin_client.get("/admin/questions?q=ΠΡΩΤΕΥΟΥΣΑ").get_data(as_text=True)
    assert "1 ερωτήσεις" in html and "alpha-1" in html
    html = admin_client.get("/admin/questions?q=τοκος").get_data(as_text=True)  # matches option «Ο τόκος»
    assert "beta-2" in html


def test_edit_question(admin_client, bank_loaded):
    response = admin_client.post("/admin/questions/alpha-1", data=_form())
    assert response.status_code == 302
    question = db.session.get(Question, "alpha-1")
    assert (question.text, question.options, question.correct) == \
           ("Νέα ερώτηση;", ["α1", "β1", "γ1", "δ1"], 2)


def test_edit_rejects_incomplete_form(admin_client, bank_loaded):
    response = admin_client.post("/admin/questions/alpha-1",
                                 data=_form(options=("α1", "", "γ1", "δ1")))
    assert response.status_code == 200
    assert "Συμπληρώστε και τις 4 απαντήσεις" in response.get_data(as_text=True)
    assert db.session.get(Question, "alpha-1").options[1] == "Αθήνα"


def test_new_question_gets_next_number(admin_client, bank_loaded):
    response = admin_client.post("/admin/questions/new?category=beta", data=_form())
    assert response.headers["Location"] == "/admin/questions/beta-3"
    question = db.session.get(Question, "beta-3")
    assert question.number == 3 and question.category.slug == "beta"


def test_delete_question_removes_attempts(admin_client, bank_loaded, admin):
    db.session.add(Attempt(user_id=admin.id, question_id="alpha-3", chosen=2,
                           is_correct=True, mode="quiz"))
    db.session.commit()
    response = admin_client.post("/admin/questions/alpha-3/delete")
    assert response.headers["Location"] == "/admin/questions?category=alpha"
    assert db.session.get(Question, "alpha-3") is None
    assert db.session.scalar(select(func.count()).select_from(Attempt)) == 0


def test_missing_question_is_404(admin_client, bank_loaded):
    assert admin_client.get("/admin/questions/nope-1").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_admin_questions.py`
Expected: FAIL — `E       AssertionError: assert 404 == 403`

- [ ] **Step 3: Implement the question admin**

`views/admin.py` (create):

```python
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
```

`templates/admin/_nav.html` (create):

```html
{% set tabs = [("admin.questions", "fa-question-circle", "Ερωτήσεις")] %}
<ul class="nav nav-tabs mb-4">
  {% for endpoint, icon, label in tabs %}
    <li class="nav-item">
      <a class="nav-link {{ 'active' if request.endpoint == endpoint }}" href="{{ url_for(endpoint) }}">
        <i class="fas {{ icon }} me-1"></i>{{ label }}
      </a>
    </li>
  {% endfor %}
</ul>
```

`templates/admin/questions.html` (create):

```html
{% extends "base.html" %}
{% block title %}Ερωτήσεις — Διαχείριση{% endblock %}
{% block content %}
<div class="container py-4">
  {% include "admin/_nav.html" %}

  <form class="row g-2 mb-3" method="get">
    <div class="col-md-5">
      <select class="form-select" name="category">
        <option value="">Όλες οι κατηγορίες</option>
        {% for c in categories %}
          <option value="{{ c.slug }}" {{ 'selected' if c.slug == slug }}>{{ c.name }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-5">
      <input class="form-control" name="q" value="{{ term }}" placeholder="Αναζήτηση σε ερωτήσεις/απαντήσεις ή id">
    </div>
    <div class="col-md-2 d-grid">
      <button class="btn btn-primary" type="submit"><i class="fas fa-search me-1"></i>Αναζήτηση</button>
    </div>
  </form>

  <div class="d-flex justify-content-between align-items-center mb-2">
    <span class="text-muted">{{ total }} ερωτήσεις</span>
    {% if slug %}
      <a class="btn btn-sm btn-success" href="{{ url_for('admin.new_question', category=slug) }}"><i class="fas fa-plus me-1"></i>Νέα ερώτηση</a>
    {% endif %}
  </div>

  <div class="card">
    <div class="table-responsive">
      <table class="table table-sm table-hover align-middle mb-0">
        <thead class="table-light"><tr><th>id</th><th>Ερώτηση</th><th>Σωστή</th><th></th></tr></thead>
        <tbody>
        {% for q in items %}
          <tr>
            <td class="text-nowrap"><code>{{ q.id }}</code></td>
            <td class="qtext">{{ q.text|truncate(140) }}</td>
            <td>{{ "αβγδ"[q.correct] }}. {{ q.options[q.correct]|truncate(60) }}</td>
            <td class="text-end"><a class="btn btn-sm btn-outline-primary" href="{{ url_for('admin.edit_question', qid=q.id) }}"><i class="fas fa-edit"></i></a></td>
          </tr>
        {% else %}
          <tr><td colspan="4" class="text-center text-muted py-4">Δεν βρέθηκαν ερωτήσεις.</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  {% if pages > 1 %}
  <nav class="mt-3 d-flex justify-content-center">
    <ul class="pagination">
      {% for p in range(1, pages + 1) %}
        <li class="page-item {{ 'active' if p == page }}">
          <a class="page-link" href="{{ url_for('admin.questions', category=slug, q=term, page=p) }}">{{ p }}</a>
        </li>
      {% endfor %}
    </ul>
  </nav>
  {% endif %}
</div>
{% endblock %}
```

`templates/admin/question_form.html` (create):

```html
{% extends "base.html" %}
{% block title %}{{ question.id if question else 'Νέα ερώτηση' }} — Διαχείριση{% endblock %}
{% block content %}
<div class="container py-4" style="max-width: 860px">
  {% include "admin/_nav.html" %}
  <a href="{{ url_for('admin.questions', category=category.slug) }}" class="small"><i class="fas fa-arrow-left me-1"></i>{{ category.name }}</a>
  <h4 class="mt-2 mb-3">{{ ("Ερώτηση " ~ question.id) if question else "Νέα ερώτηση" }}</h4>

  <form method="post">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="mb-3">
      <label class="form-label" for="text">Κείμενο ερώτησης</label>
      <textarea class="form-control" id="text" name="text" rows="4" required>{{ values.text }}</textarea>
    </div>
    {% for i in range(4) %}
      <div class="input-group mb-2">
        <div class="input-group-text">
          <input class="form-check-input mt-0" type="radio" name="correct" value="{{ i }}" id="correct{{ i }}"
                 {{ 'checked' if values.correct == i }} aria-label="Σωστή απάντηση {{ 'αβγδ'[i] }}">
          <label class="ms-2 fw-bold" for="correct{{ i }}">{{ "αβγδ"[i] }}.</label>
        </div>
        <textarea class="form-control" name="a{{ i }}" rows="2" required>{{ values.options[i] }}</textarea>
      </div>
    {% endfor %}
    <div class="form-text mb-3">Επιλέξτε με το κουμπί την σωστή απάντηση.</div>
    <button class="btn btn-primary" type="submit"><i class="fas fa-save me-1"></i>Αποθήκευση</button>
  </form>

  {% if question %}
  <form method="post" action="{{ url_for('admin.delete_question', qid=question.id) }}" class="mt-4"
        onsubmit="return confirm('Διαγραφή της ερώτησης {{ question.id }} και όλων των απαντήσεων χρηστών σε αυτήν;')">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button class="btn btn-outline-danger btn-sm" type="submit"><i class="fas fa-trash me-1"></i>Διαγραφή ερώτησης</button>
  </form>
  {% endif %}
</div>
{% endblock %}
```

In `templates/base.html`, add the admin link right after the Πρόοδος line:

```html
        {% if current_user.is_admin %}
          <li class="nav-item"><a class="nav-link" href="{{ url_for('admin.home') }}"><i class="fas fa-tools me-1"></i>Διαχείριση</a></li>
        {% endif %}
```

In `app.py`, register the blueprint — the end of `create_app` becomes:

```python
    # Import models so their tables register with the metadata.
    import models  # noqa: F401
    from cli import register_cli
    from views import admin, api, auth, main

    for blueprint in (main.bp, auth.bp, api.bp, admin.bp):
        app.register_blueprint(blueprint)
    register_cli(app)

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def error_page(error):
        code = getattr(error, "code", 500)
        return render_template("error.html", code=code), code

    return app
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `57 passed`

- [ ] **Step 5: Commit**

```bash
git add views/admin.py templates app.py tests/test_admin_questions.py
git commit -m "Add admin question editor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Admin — import and export the bank

**Files:**
- Modify: `bank.py` (export + import), `views/admin.py` (import/export views), `templates/admin/_nav.html` (tab)
- Create: `templates/admin/import.html`, `templates/admin/import_preview.html`
- Test: `tests/test_admin_bank.py`

**Interfaces:**
- Consumes: `bank.validate_items`, `bank._new_question`, `admin._categories`, `admin._category_or_404`.
- Produces: `bank.category_items(category) -> list[dict]`, `bank.export_zip() -> bytes` (`index.json` + `categories/<slug>.json`), `bank.ImportPlan(added, changed, removed: list[str], unchanged: int, attempts_removed: int)`, `bank.plan_import(category, items) -> ImportPlan` (raises `BankError`, also when an added id exists in another category), `bank.apply_import(category, items) -> ImportPlan`; endpoints `admin.export` (GET `/admin/export`, `asep-questions.zip`) and `admin.import_bank` (GET/POST `/admin/import`: upload → preview carrying the JSON in a hidden `payload` field → POST with `confirm=1` applies).

- [ ] **Step 1: Write the failing tests**

`tests/test_admin_bank.py` (create):

```python
import io
import json
import zipfile

import pytest
from sqlalchemy import select

import bank
from extensions import db
from models import Attempt, Category, Question


def _alpha():
    return db.session.scalar(select(Category).filter_by(slug="alpha"))


def _edited_alpha_items():
    """alpha-1 unchanged, alpha-2 reworded, alpha-3 dropped, alpha-4 new."""
    items = bank.category_items(_alpha())
    items[1]["q"] = "Πόσα άρθρα έχει σήμερα το Σύνταγμα;"
    del items[2]
    items.append({"id": "alpha-4", "n": 4, "q": "Νέα;", "a": ["1", "2", "3", "4"], "c": 3})
    return items


def test_plan_import_diffs_by_id(bank_loaded, user):
    db.session.add(Attempt(user_id=user.id, question_id="alpha-3", chosen=0,
                           is_correct=False, mode="quiz"))
    db.session.commit()
    plan = bank.plan_import(_alpha(), _edited_alpha_items())
    assert plan.added == ["alpha-4"]
    assert plan.changed == ["alpha-2"]
    assert plan.removed == ["alpha-3"]
    assert plan.unchanged == 1
    assert plan.attempts_removed == 1


def test_apply_import_replaces_category(bank_loaded):
    bank.apply_import(_alpha(), _edited_alpha_items())
    assert [q.id for q in _alpha().questions] == ["alpha-1", "alpha-2", "alpha-4"]
    assert db.session.get(Question, "alpha-2").text == "Πόσα άρθρα έχει σήμερα το Σύνταγμα;"


def test_plan_import_rejects_invalid_items(bank_loaded):
    with pytest.raises(bank.BankError):
        bank.plan_import(_alpha(), [{"id": "beta-1", "q": "x", "a": ["1", "2", "3", "4"], "c": 0}])


def test_export_round_trips_unchanged(bank_loaded):
    archive = zipfile.ZipFile(io.BytesIO(bank.export_zip()))
    index = json.loads(archive.read("index.json"))
    assert [(c["slug"], c["count"]) for c in index] == [("alpha", 3), ("beta", 2)]
    items = json.loads(archive.read("categories/alpha.json"))
    plan = bank.plan_import(_alpha(), items)
    assert (plan.added, plan.changed, plan.removed, plan.unchanged) == ([], [], [], 3)


def test_export_view_downloads_zip(admin_client, bank_loaded):
    response = admin_client.get("/admin/export")
    assert response.mimetype == "application/zip"
    assert "asep-questions.zip" in response.headers["Content-Disposition"]


def _upload(client, items, category="alpha"):
    payload = json.dumps(items, ensure_ascii=False).encode()
    return client.post("/admin/import", data={"category": category,
                                              "file": (io.BytesIO(payload), "alpha.json")},
                       content_type="multipart/form-data")


def test_import_preview_then_confirm(admin_client, bank_loaded):
    items = _edited_alpha_items()
    preview = _upload(admin_client, items)
    html = preview.get_data(as_text=True)
    assert preview.status_code == 200 and "Επιβεβαίωση εισαγωγής" in html
    assert db.session.get(Question, "alpha-4") is None          # nothing written yet

    confirm = admin_client.post("/admin/import", data={
        "category": "alpha", "confirm": "1", "payload": json.dumps(items, ensure_ascii=False)})
    assert confirm.headers["Location"] == "/admin/questions?category=alpha"
    assert db.session.get(Question, "alpha-4") is not None
    assert db.session.get(Question, "alpha-3") is None


def test_import_shows_validation_problems(admin_client, bank_loaded):
    response = _upload(admin_client, [{"id": "alpha-1", "q": "x", "a": ["1"], "c": 0}])
    assert response.status_code == 400
    assert "4 μη κενές απαντήσεις" in response.get_data(as_text=True)


def test_import_rejects_broken_json(admin_client, bank_loaded):
    response = admin_client.post("/admin/import", data={
        "category": "alpha", "file": (io.BytesIO(b"{not json"), "x.json")},
        content_type="multipart/form-data")
    assert response.status_code == 400
    assert "Μη έγκυρο JSON" in response.get_data(as_text=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_admin_bank.py`
Expected: FAIL — `E       AttributeError: module 'bank' has no attribute 'plan_import'`

- [ ] **Step 3: Add export/import to `bank.py`**

In `bank.py`, replace the import block (between `from __future__ import annotations` and `class BankError`) with:

```python
import io
import json
import os
import zipfile
from dataclasses import dataclass, field

from sqlalchemy import func, select

from extensions import db
from models import Attempt, Category, Question
```

Append to the end of `bank.py`:

```python
def category_items(category: Category) -> list[dict]:
    """A category's questions in the on-disk item format."""
    return [{"id": q.id, "n": q.number, "q": q.text, "a": list(q.options), "c": q.correct}
            for q in category.questions]


def export_zip() -> bytes:
    """The whole bank as a zip of index.json + categories/<slug>.json."""
    categories = db.session.scalars(select(Category).order_by(Category.position)).all()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        index = []
        for category in categories:
            items = category_items(category)
            archive.writestr(f"categories/{category.slug}.json",
                             json.dumps(items, ensure_ascii=False, indent=1))
            index.append({"name": category.name, "slug": category.slug, "count": len(items)})
        archive.writestr("index.json", json.dumps(index, ensure_ascii=False, indent=1))
    return buffer.getvalue()


@dataclass
class ImportPlan:
    """What importing a file into a category would do (or did)."""
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0
    attempts_removed: int = 0


def plan_import(category: Category, items: object) -> ImportPlan:
    """Diff ``items`` against the category by id. Raises BankError if invalid."""
    problems = validate_items(items, category.slug)
    if problems:
        raise BankError(problems)
    existing = {q.id: q for q in category.questions}
    plan = ImportPlan()
    for pos, item in enumerate(items, 1):
        question = existing.get(item["id"])
        if question is None:
            plan.added.append(item["id"])
        elif ((question.number, question.text, list(question.options), question.correct)
              != (item.get("n", pos), item["q"], list(item["a"]), item["c"])):
            plan.changed.append(item["id"])
        else:
            plan.unchanged += 1
    if plan.added:
        clash = db.session.scalars(select(Question.id).where(Question.id.in_(plan.added))).all()
        if clash:
            raise BankError([f"Το id {qid} υπάρχει ήδη σε άλλη κατηγορία." for qid in clash])
    incoming = {item["id"] for item in items}
    plan.removed = [qid for qid in existing if qid not in incoming]
    if plan.removed:
        plan.attempts_removed = db.session.scalar(
            select(func.count()).select_from(Attempt)
            .where(Attempt.question_id.in_(plan.removed)))
    return plan


def apply_import(category: Category, items: list[dict]) -> ImportPlan:
    """Replace the category's questions with ``items``; attempts on removed ones are deleted."""
    plan = plan_import(category, items)
    existing = {q.id: q for q in category.questions}
    for qid in plan.removed:
        db.session.delete(existing[qid])
    for pos, item in enumerate(items, 1):
        question = existing.get(item["id"])
        if question is None:
            db.session.add(_new_question(item, pos, category))
        else:
            question.number = item.get("n", pos)
            question.text = item["q"]
            question.options = list(item["a"])
            question.correct = item["c"]
    db.session.commit()
    return plan
```

- [ ] **Step 4: Add the admin views and templates**

In `views/admin.py`, replace the import block (between `from __future__ import annotations` and `bp = Blueprint`) with:

```python
import io
import json
import unicodedata

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from sqlalchemy import func, select

import bank
from extensions import db, login_manager
from models import Category, Question
```

Append to the end of `views/admin.py`:

```python
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
```

`templates/admin/_nav.html` (replace):

```html
{% set tabs = [("admin.questions", "fa-question-circle", "Ερωτήσεις"),
                ("admin.import_bank", "fa-file-import", "Εισαγωγή / Εξαγωγή")] %}
<ul class="nav nav-tabs mb-4">
  {% for endpoint, icon, label in tabs %}
    <li class="nav-item">
      <a class="nav-link {{ 'active' if request.endpoint == endpoint }}" href="{{ url_for(endpoint) }}">
        <i class="fas {{ icon }} me-1"></i>{{ label }}
      </a>
    </li>
  {% endfor %}
</ul>
```

`templates/admin/import.html` (create):

```html
{% extends "base.html" %}
{% block title %}Εισαγωγή / Εξαγωγή — Διαχείριση{% endblock %}
{% block content %}
<div class="container py-4" style="max-width: 860px">
  {% include "admin/_nav.html" %}

  <div class="card mb-4">
    <div class="card-body">
      <h5 class="card-title"><i class="fas fa-file-export me-2"></i>Εξαγωγή</h5>
      <p class="text-muted">Κατεβάστε όλη την τράπεζα θεμάτων ως zip (<code>index.json</code> + <code>categories/*.json</code>).</p>
      <a class="btn btn-outline-primary" href="{{ url_for('admin.export') }}"><i class="fas fa-download me-1"></i>Λήψη zip</a>
    </div>
  </div>

  <div class="card">
    <div class="card-body">
      <h5 class="card-title"><i class="fas fa-file-import me-2"></i>Εισαγωγή κατηγορίας</h5>
      <p class="text-muted">Ανεβάστε ένα αρχείο <code>categories/&lt;slug&gt;.json</code>. Η κατηγορία θα αντικατασταθεί
        από το περιεχόμενο του αρχείου. Θα δείτε προεπισκόπηση πριν από οποιαδήποτε αλλαγή.</p>
      {% if problems %}
        <div class="alert alert-danger">
          <strong>Το αρχείο δεν μπορεί να εισαχθεί:</strong>
          <ul class="mb-0">{% for p in problems[:30] %}<li>{{ p }}</li>{% endfor %}</ul>
          {% if problems|length > 30 %}<div>… και {{ problems|length - 30 }} ακόμη.</div>{% endif %}
        </div>
      {% endif %}
      <form method="post" enctype="multipart/form-data">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mb-3">
          <label class="form-label" for="category">Κατηγορία</label>
          <select class="form-select" id="category" name="category" required>
            {% for c in categories %}
              <option value="{{ c.slug }}" {{ 'selected' if c.slug == selected }}>{{ c.name }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="mb-3">
          <label class="form-label" for="file">Αρχείο JSON</label>
          <input class="form-control" id="file" name="file" type="file" accept=".json,application/json" required>
        </div>
        <button class="btn btn-primary" type="submit"><i class="fas fa-eye me-1"></i>Προεπισκόπηση</button>
      </form>
    </div>
  </div>
</div>
{% endblock %}
```

`templates/admin/import_preview.html` (create):

```html
{% extends "base.html" %}
{% block title %}Προεπισκόπηση εισαγωγής — Διαχείριση{% endblock %}
{% block content %}
<div class="container py-4" style="max-width: 860px">
  {% include "admin/_nav.html" %}
  <h4 class="mb-3">Προεπισκόπηση: {{ category.name }}</h4>

  <ul class="list-group mb-3">
    <li class="list-group-item d-flex justify-content-between">Νέες ερωτήσεις <span class="badge bg-success">{{ plan.added|length }}</span></li>
    <li class="list-group-item d-flex justify-content-between">Αλλαγμένες ερωτήσεις <span class="badge bg-primary">{{ plan.changed|length }}</span></li>
    <li class="list-group-item d-flex justify-content-between">Αμετάβλητες <span class="badge bg-secondary">{{ plan.unchanged }}</span></li>
    <li class="list-group-item d-flex justify-content-between">Ερωτήσεις που θα διαγραφούν <span class="badge bg-danger">{{ plan.removed|length }}</span></li>
  </ul>
  {% if plan.attempts_removed %}
    <div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-1"></i>
      Θα διαγραφούν επίσης {{ plan.attempts_removed }} απαντήσεις χρηστών στις ερωτήσεις που αφαιρούνται.</div>
  {% endif %}
  {% if plan.removed %}
    <details class="mb-3"><summary>Ερωτήσεις προς διαγραφή</summary>
      <div class="small"><code>{{ plan.removed|join(", ") }}</code></div></details>
  {% endif %}

  <form method="post" class="d-flex gap-2">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="category" value="{{ category.slug }}">
    <input type="hidden" name="confirm" value="1">
    <textarea name="payload" hidden>{{ payload }}</textarea>
    <button class="btn btn-danger" type="submit"><i class="fas fa-check me-1"></i>Επιβεβαίωση εισαγωγής</button>
    <a class="btn btn-outline-secondary" href="{{ url_for('admin.import_bank') }}">Ακύρωση</a>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `65 passed`

- [ ] **Step 6: Commit**

```bash
git add bank.py views/admin.py templates/admin tests/test_admin_bank.py
git commit -m "Add admin import and export of the question bank" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Admin — manage users

**Files:**
- Modify: `views/admin.py` (users views), `templates/admin/_nav.html` (tab), `app.py` (`localtime` filter)
- Create: `templates/admin/users.html`
- Test: `tests/test_admin_users.py`

**Interfaces:**
- Consumes: `User`, `Attempt`, `current_user`.
- Produces: endpoints `admin.users` (GET `/admin/users`) and `admin.user_action` (POST `/admin/users/<uid>/<action>`, action ∈ `admin.USER_ACTIONS` = `toggle-active`, `toggle-admin`, `reset-password` (form field `password`, ≥ 8), `delete`; an admin cannot toggle or delete themselves); `app.localtime(value, fmt="%d/%m/%Y %H:%M") -> str` Jinja filter (naive UTC → Europe/Athens, `None` → `—`).

- [ ] **Step 1: Write the failing tests**

`tests/test_admin_users.py` (create):

```python
from extensions import db
from models import Attempt, User
from tests.conftest import login, make_user


def test_users_page_lists_accounts(admin_client, user):
    html = admin_client.get("/admin/users").get_data(as_text=True)
    assert "maria" in html and "boss" in html


def test_toggle_active_blocks_login(admin_client, user, app):
    admin_client.post(f"/admin/users/{user.id}/toggle-active")
    assert db.session.get(User, user.id).active is False
    other = app.test_client()
    assert login(other).status_code == 403


def test_toggle_admin(admin_client, user):
    admin_client.post(f"/admin/users/{user.id}/toggle-admin")
    assert db.session.get(User, user.id).is_admin is True


def test_reset_password(admin_client, user, app):
    admin_client.post(f"/admin/users/{user.id}/reset-password", data={"password": "brand-new-pass"})
    assert login(app.test_client(), password="brand-new-pass").status_code == 302


def test_reset_password_too_short(admin_client, user):
    admin_client.post(f"/admin/users/{user.id}/reset-password", data={"password": "short"})
    assert db.session.get(User, user.id).check_password("secret-pass")


def test_delete_user_and_their_attempts(admin_client, bank_loaded):
    victim = make_user("victim")
    db.session.add(Attempt(user_id=victim.id, question_id="alpha-1", chosen=1,
                           is_correct=True, mode="quiz"))
    db.session.commit()
    victim_id = victim.id
    admin_client.post(f"/admin/users/{victim_id}/delete")
    assert db.session.get(User, victim_id) is None
    assert db.session.query(Attempt).count() == 0


def test_admin_cannot_lock_themselves_out(admin_client, admin):
    for action in ("toggle-active", "toggle-admin", "delete"):
        admin_client.post(f"/admin/users/{admin.id}/{action}")
    me = db.session.get(User, admin.id)
    assert me is not None and me.active and me.is_admin


def test_unknown_action_is_404(admin_client, user):
    assert admin_client.post(f"/admin/users/{user.id}/explode").status_code == 404


def test_localtime_filter_shows_athens_time():
    from datetime import datetime
    from app import localtime
    assert localtime(datetime(2026, 7, 1, 9, 30)) == "01/07/2026 12:30"    # EEST, UTC+3
    assert localtime(datetime(2026, 1, 1, 9, 30), "%H:%M") == "11:30"      # EET, UTC+2
    assert localtime(None) == "—"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_admin_users.py`
Expected: FAIL — `E       AssertionError: assert 400 == 302` (3 tests pass already because they assert that nothing changes.)

- [ ] **Step 3: Add the users views**

In `views/admin.py`, change the models import to `from models import Attempt, Category, Question, User` and replace `PAGE_SIZE = 25` with:

```python
PAGE_SIZE = 25
MIN_PASSWORD = 8
USER_ACTIONS = ("toggle-active", "toggle-admin", "reset-password", "delete")
```

Append to the end of `views/admin.py`:

```python
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
    flash(message, "success")
    return redirect(url_for("admin.users"))
```

`templates/admin/_nav.html` (replace):

```html
{% set tabs = [("admin.questions", "fa-question-circle", "Ερωτήσεις"),
                ("admin.import_bank", "fa-file-import", "Εισαγωγή / Εξαγωγή"),
                ("admin.users", "fa-users", "Χρήστες")] %}
<ul class="nav nav-tabs mb-4">
  {% for endpoint, icon, label in tabs %}
    <li class="nav-item">
      <a class="nav-link {{ 'active' if request.endpoint == endpoint }}" href="{{ url_for(endpoint) }}">
        <i class="fas {{ icon }} me-1"></i>{{ label }}
      </a>
    </li>
  {% endfor %}
</ul>
```

`templates/admin/users.html` (create):

```html
{% extends "base.html" %}
{% block title %}Χρήστες — Διαχείριση{% endblock %}
{% macro action(user, name, label, style, confirm_text=None) -%}
  <form method="post" action="{{ url_for('admin.user_action', uid=user.id, action=name) }}" class="d-inline"
        {% if confirm_text %}onsubmit="return confirm('{{ confirm_text }}')"{% endif %}>
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button class="btn btn-sm {{ style }}" type="submit">{{ label }}</button>
  </form>
{%- endmacro %}
{% block content %}
<div class="container py-4">
  {% include "admin/_nav.html" %}
  <div class="card">
    <div class="table-responsive">
      <table class="table table-sm table-hover align-middle mb-0">
        <thead class="table-light">
          <tr><th>Χρήστης</th><th>Εγγραφή</th><th>Τελευταία σύνδεση</th><th class="text-center">Απαντήσεις</th><th>Κατάσταση</th><th></th></tr>
        </thead>
        <tbody>
        {% for user, attempts in rows %}
          <tr>
            <td>{{ user.username }}{% if user.is_admin %} <span class="badge bg-dark">admin</span>{% endif %}</td>
            <td>{{ user.created_at|localtime('%d/%m/%Y') }}</td>
            <td>{{ user.last_login_at|localtime }}</td>
            <td class="text-center">{{ attempts }}</td>
            <td>{% if user.active %}<span class="badge bg-success">ενεργός</span>{% else %}<span class="badge bg-secondary">ανενεργός</span>{% endif %}</td>
            <td class="text-end text-nowrap">
              {% if user.id != current_user.id %}
                {{ action(user, 'toggle-active', 'Απενεργοποίηση' if user.active else 'Ενεργοποίηση', 'btn-outline-secondary') }}
                {{ action(user, 'toggle-admin', 'Αφαίρεση admin' if user.is_admin else 'Ορισμός admin', 'btn-outline-dark') }}
                {{ action(user, 'delete', 'Διαγραφή', 'btn-outline-danger', 'Διαγραφή του ' ~ user.username ~ ' και όλης της προόδου του;') }}
              {% endif %}
              <form method="post" action="{{ url_for('admin.user_action', uid=user.id, action='reset-password') }}" class="d-inline-flex gap-1 ms-1">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <input class="form-control form-control-sm" name="password" type="password" minlength="8" placeholder="νέος κωδικός" required style="width: 9rem">
                <button class="btn btn-sm btn-outline-primary" type="submit">Αλλαγή</button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Add the `localtime` filter**

In `app.py`, add below `import os`:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
```

add below the `DB_PATH = …` line:

```python
ATHENS = ZoneInfo("Europe/Athens")


def localtime(value: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Jinja filter: show a stored (naive UTC) timestamp in Greek local time."""
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ATHENS).strftime(fmt)
```

and add `app.add_template_filter(localtime)` right after `register_cli(app)`. `tzdata` (already in `requirements.txt`) supplies the zone data in the slim container.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `74 passed`

- [ ] **Step 6: Commit**

```bash
git add views/admin.py templates/admin app.py tests/test_admin_users.py
git commit -m "Add admin user management" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Admin bootstrap command, Docker image and README

**Files:**
- Modify: `cli.py` (final)
- Create: `Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yaml`, `.dockerignore`, `.env.example`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `bank.seed`, `User`.
- Produces: `cli.ensure_admin(username, password) -> User` (create, or reset to admin + active + new password) and `flask ensure-admin` (reads `ADMIN_USERNAME` / `ADMIN_PASSWORD`; skips when unset; exits non-zero when the password is < 8 chars); image `asep2027` whose entrypoint runs `flask db upgrade` → `flask seed` → `flask ensure-admin` → gunicorn on `0.0.0.0:8000`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py` (create):

```python
from sqlalchemy import select

from cli import ensure_admin
from extensions import db
from models import User
from tests.conftest import make_user


def test_ensure_admin_creates_account(app):
    user = ensure_admin("Boss", "admin-pass-1")
    assert (user.username, user.is_admin, user.active) == ("boss", True, True)
    assert user.check_password("admin-pass-1")


def test_ensure_admin_promotes_and_resets_existing(app):
    make_user("boss", password="old-password", active=False)
    ensure_admin("boss", "new-password")
    user = db.session.scalar(select(User).filter_by(username="boss"))
    assert user.is_admin and user.active and user.check_password("new-password")


def test_cli_skips_without_env(app, monkeypatch):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    result = app.test_cli_runner().invoke(args=["ensure-admin"])
    assert "skipping" in result.output
    assert db.session.scalar(select(User)) is None


def test_cli_rejects_short_password(app, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "boss")
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    result = app.test_cli_runner().invoke(args=["ensure-admin"])
    assert result.exit_code != 0


def test_cli_creates_admin_from_env(app, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "boss")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    result = app.test_cli_runner().invoke(args=["ensure-admin"])
    assert "Admin 'boss' is ready." in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli.py`
Expected: FAIL — `E   ImportError: cannot import name 'ensure_admin' from 'cli'`

- [ ] **Step 3: Implement `ensure-admin`**

`cli.py` (replace):

```python
"""Flask CLI commands run by docker/entrypoint.sh on every container start."""

from __future__ import annotations

import os

import click
from flask import Flask, current_app
from sqlalchemy import select

import bank
from extensions import db
from models import User


def ensure_admin(username: str, password: str) -> User:
    """Create the admin account, or reset an existing one to admin + this password."""
    username = username.strip().lower()
    user = db.session.scalar(select(User).filter_by(username=username))
    if user is None:
        user = User(username=username)
        db.session.add(user)
    user.set_password(password)
    user.is_admin = True
    user.active = True
    db.session.commit()
    return user


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_command() -> None:
        """Load data/ into the database if it holds no questions yet."""
        inserted = bank.seed(current_app.config["DATA_DIR"])
        click.echo(f"Seeded {inserted} questions." if inserted
                   else "Questions already loaded; nothing to do.")

    @app.cli.command("ensure-admin")
    def ensure_admin_command() -> None:
        """Create/update the admin from ADMIN_USERNAME and ADMIN_PASSWORD."""
        username = os.environ.get("ADMIN_USERNAME", "")
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not username or not password:
            click.echo("ADMIN_USERNAME/ADMIN_PASSWORD not set; skipping.")
            return
        if len(password) < 8:
            raise click.ClickException("ADMIN_PASSWORD must be at least 8 characters.")
        user = ensure_admin(username, password)
        click.echo(f"Admin '{user.username}' is ready.")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest`
Expected: `79 passed`

- [ ] **Step 5: Add the container files and README**

`Dockerfile` (create):

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app \
    ASEP_DB=/data/db/asep.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Mount point for the persistent volume holding the SQLite database.
RUN mkdir -p /data/db && chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
```

`docker/entrypoint.sh` (create):

```sh
#!/bin/sh
set -e

echo "[entrypoint] Applying database migrations..."
flask db upgrade

echo "[entrypoint] Loading the question bank (skipped if already loaded)..."
flask seed

echo "[entrypoint] Ensuring the admin account..."
flask ensure-admin

echo "[entrypoint] Starting gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers "${WEB_CONCURRENCY:-3}" --timeout 60 app:app
```

Make it executable: `chmod +x docker/entrypoint.sh`.

`docker-compose.yaml` (create):

```yaml
services:
  web:
    build: .
    image: asep2027
    container_name: asep2027
    ports:
      # Only reachable from this machine; Tailscale Funnel publishes it.
      - "127.0.0.1:8000:8000"
    environment:
      ASEP_DB: /data/db/asep.db
      SECRET_KEY: ${SECRET_KEY:?Set SECRET_KEY in .env}
      # Admin account (re)created on every start. Set both in .env.
      ADMIN_USERNAME: ${ADMIN_USERNAME:-}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:-}
      SESSION_COOKIE_SECURE: "1"
      WEB_CONCURRENCY: 3
    volumes:
      - db_data:/data/db
    restart: unless-stopped

volumes:
  db_data:   # SQLite database (users, progress, edited questions)
```

`.dockerignore` (create):

```text
.venv/
.git/
.gitignore
.idea/
.claude/
__pycache__/
**/__pycache__/
*.pyc
.pytest_cache/
.env
# local database — the container builds its own on the mounted volume
*.db
# source PDFs and design docs are not needed at runtime
themata/
docs/
```

`.env.example` (create):

```text
# Copy to .env and fill in. Never commit .env.
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=
ADMIN_USERNAME=admin
# At least 8 characters. Re-applied on every container start.
ADMIN_PASSWORD=
```

`README.md` (create):

````markdown
# ΑΣΕΠ 2027 — Τράπεζα Θεμάτων (web app)

Flask web app for studying the 2026 ASEP question bank (1988 questions, 11
categories): random quizzes and full browsing for everyone; per-user progress
(stats, "wrong only" / "unseen only" quizzes) after a free sign-up; and an
admin area to edit questions, import/export the bank and manage users.

The questions were extracted from the PDFs in `themata/` into `data/`
(`index.json` + `categories/<slug>.json`). The app loads them into SQLite on
first start.

## Run with Docker (production)

```bash
cp .env.example .env        # then fill in SECRET_KEY and ADMIN_PASSWORD
docker compose up -d --build
docker compose logs -f web  # migrations → seed → admin → gunicorn
```

The app listens on `http://127.0.0.1:8000` (this machine only). On every start
the entrypoint applies migrations, loads `data/` if the database has no
questions yet, and creates/updates the admin account from `ADMIN_USERNAME` /
`ADMIN_PASSWORD`.

### Expose it with Tailscale Funnel

```bash
sudo tailscale funnel --bg 8000   # public https://<machine>.<tailnet>.ts.net
tailscale funnel status
sudo tailscale funnel reset       # stop publishing
```

Funnel must be enabled for your tailnet (the first run prints a link to the
admin console if it is not).

### Back up the database

Users, progress and edited questions live in the `db_data` volume:

```bash
docker compose exec web python -c "import sqlite3; s=sqlite3.connect('/data/db/asep.db'); d=sqlite3.connect('/data/db/backup.db'); s.backup(d)"
docker compose cp web:/data/db/backup.db ./asep-backup.db
```

The question bank alone can also be downloaded from **Διαχείριση → Εισαγωγή /
Εξαγωγή → Λήψη zip**.

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export FLASK_APP=app
.venv/bin/flask db upgrade && .venv/bin/flask seed
ADMIN_USERNAME=admin ADMIN_PASSWORD=change-me-now .venv/bin/flask ensure-admin
.venv/bin/flask run --debug --port 8001
.venv/bin/python -m pytest
```

On this machine the system Python has no `ensurepip`, so create the venv with
`python3 -m venv --without-pip .venv` and install with another pip:
`<other-venv>/bin/pip --python .venv/bin/python install -r requirements.txt`.

## Layout

| Path | Purpose |
|---|---|
| `app.py` | `create_app()` factory, config from env vars |
| `models.py` | Category, Question, User, Attempt |
| `bank.py` | validate / seed / import / export the JSON bank |
| `stats.py` | per-user progress from the latest attempt per question |
| `ratelimit.py` | in-memory limiter for login/register |
| `cli.py` | `flask seed`, `flask ensure-admin` |
| `views/` | `main` (pages), `auth`, `api` (JSON for `static/app.js`), `admin` |
| `data/` | extracted question bank (seed source) |
| `themata/` | source PDFs (not shipped in the image) |
````

- [ ] **Step 6: Build and smoke-test the container**

Docker Desktop must be running (`docker info` succeeds); if it is not, ask the user to start it — do not start it yourself.

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # paste into SECRET_KEY in .env
# set ADMIN_PASSWORD in .env (>= 8 chars)
docker compose up -d --build
docker compose logs web | head -20
curl -s http://127.0.0.1:8000/api/categories | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), sum(c['count'] for c in d))"
```

Expected logs: `Running upgrade  -> 0001`, `Seeded 1988 questions.`, `Admin 'admin' is ready.`, gunicorn `Listening at: http://0.0.0.0:8000`. Expected curl output: `11 1988`. Restart once (`docker compose restart web`) and confirm the log says `Questions already loaded; nothing to do.` `.env` is git-ignored.

- [ ] **Step 7: Commit**

```bash
git add cli.py Dockerfile docker docker-compose.yaml .dockerignore .env.example README.md tests/test_cli.py
git commit -m "Add admin bootstrap command, Docker setup and README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Publish with Tailscale Funnel (user-confirmed)

**Files:** none.

**Interfaces:**
- Consumes: the running container on `127.0.0.1:8000` (Task 10).
- Produces: the public URL `https://<machine>.<tailnet>.ts.net`.

Publishing makes the site reachable from the internet, so **ask the user for explicit confirmation before Step 1**, and let them run `sudo` commands themselves if they prefer.

- [ ] **Step 1: Turn on Funnel**

```bash
sudo tailscale funnel --bg 8000
tailscale funnel status
```

Expected: status lists `https://<machine>.<tailnet>.ts.net (Funnel on)` proxying to `http://127.0.0.1:8000`. If Funnel is not enabled for the tailnet, the command prints an admin-console link — the user must approve it.

- [ ] **Step 2: Verify over the public URL**

Open the URL in the browser: the home page loads over https, sign-up/login keeps the session (cookies are `Secure`), and `/admin` works for the admin account from `.env`. Report the URL to the user.

To stop publishing later: `sudo tailscale funnel reset`.
