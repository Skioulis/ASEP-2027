import pytest
from sqlalchemy import text

from app import create_app
from extensions import db


def test_production_requires_a_secret_key(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "1")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "a-real-secret")
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'prod.db'}"})
    assert app.config["SECRET_KEY"] == "a-real-secret"


def test_responses_carry_security_headers(client):
    response = client.get("/")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"


def test_sqlite_runs_in_wal_mode(app):
    assert db.session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
