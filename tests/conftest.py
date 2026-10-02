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
