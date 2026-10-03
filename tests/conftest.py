"""Test fixtures: a throwaway migrated database per test, a small question
bank (tests/fixtures/bank), and helpers to create and log in users.

Tests run on a per-test SQLite file by default. Set TEST_DATABASE_URL to run
them on PostgreSQL instead; its database name must contain "test" because
every test drops and recreates all tables there.
"""

from __future__ import annotations

import os

import pytest
from flask import g
from flask.testing import FlaskClient
from flask_migrate import upgrade
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app import create_app
from extensions import db
from ratelimit import limiter

FIXTURE_BANK = os.path.join(os.path.dirname(__file__), "fixtures", "bank")
PASSWORD = "secret-pass"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def pytest_sessionstart(session):
    """Refuse to wipe a database that is not clearly a test database."""
    if TEST_DATABASE_URL and "test" not in (make_url(TEST_DATABASE_URL).database or ""):
        pytest.exit(
            'TEST_DATABASE_URL must name a database containing "test": '
            "the tests drop every table in it.",
            returncode=2,
        )


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
        "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL or f"sqlite:///{tmp_path / 'test.db'}",
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "DATA_DIR": FIXTURE_BANK,
    })
    application.test_client_class = FreshUserClient
    limiter.reset()
    with application.app_context():
        if db.engine.dialect.name == "postgresql":
            # The database outlives the test; start every test from nothing.
            db.drop_all()
            db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
            db.session.commit()
        upgrade()
        yield application
        db.session.remove()
        # Return the connections: every test builds its own app and engine.
        db.engine.dispose()


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
