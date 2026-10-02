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


def test_ensure_admin_keeps_hash_when_password_is_unchanged(app):
    first = ensure_admin("boss", "admin-pass-1").password_hash
    again = ensure_admin("boss", "admin-pass-1").password_hash
    assert again == first


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
