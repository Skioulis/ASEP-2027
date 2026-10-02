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
