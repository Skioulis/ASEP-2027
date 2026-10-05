import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

import app as app_module
from app import create_app
from extensions import db

PG_URI = "postgresql+psycopg://asep:pw@db.invalid:5432/asep"
# Environment variables that decide which database the app talks to.
DB_ENV_KEYS = ("DATABASE_URL", "HOST", "PORT", "ADMIN", "DATABASE", "PASSWORD", "ASEP_DB")


@pytest.fixture(autouse=True)
def clean_database_env(monkeypatch):
    """Keep the developer's shell from deciding which database a test sees."""
    for key in DB_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def production_env(monkeypatch, **extra):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "1")
    monkeypatch.setenv("SECRET_KEY", "a-real-secret")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_production_requires_a_secret_key(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "1")
    monkeypatch.setenv("DATABASE_URL", PG_URI)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "a-real-secret")
    # Creating the app opens no connection, so the unreachable host is fine.
    app = create_app()
    assert app.config["SECRET_KEY"] == "a-real-secret"
    assert app.config["SQLALCHEMY_DATABASE_URI"] == PG_URI


def test_production_refuses_sqlite(monkeypatch, tmp_path):
    production_env(monkeypatch)
    # No database variables at all: the SQLite fallback is development only.
    with pytest.raises(RuntimeError, match="Production needs PostgreSQL"):
        create_app()
    # The check uses the final URI, so a SQLite override is refused too ...
    monkeypatch.setenv("DATABASE_URL", PG_URI)
    with pytest.raises(RuntimeError, match="env/database.env"):
        create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'prod.db'}"})
    # ... and a PostgreSQL override rescues an environment that points at SQLite.
    monkeypatch.delenv("DATABASE_URL")
    app = create_app({"SQLALCHEMY_DATABASE_URI": PG_URI})
    assert app.config["SQLALCHEMY_DATABASE_URI"] == PG_URI


def test_engine_options_follow_the_final_database(monkeypatch, tmp_path):
    sqlite_uri = f"sqlite:///{tmp_path / 'dev.db'}"
    assert create_app({"SQLALCHEMY_DATABASE_URI": sqlite_uri}).config[
        "SQLALCHEMY_ENGINE_OPTIONS"] == {"connect_args": {"timeout": 15},
                                       "json_serializer": app_module._json_dumps}
    # The options depend on the URI after the override, not the environment.
    monkeypatch.setenv("DATABASE_URL", PG_URI)
    assert create_app({"SQLALCHEMY_DATABASE_URI": sqlite_uri}).config[
        "SQLALCHEMY_ENGINE_OPTIONS"] == {"connect_args": {"timeout": 15},
                                       "json_serializer": app_module._json_dumps}
    assert create_app().config["SQLALCHEMY_ENGINE_OPTIONS"] == {
        "pool_pre_ping": True, "pool_recycle": 1800, "json_serializer": app_module._json_dumps}
    # An override that sets its own engine options wins.
    custom = {"pool_size": 2}
    assert create_app({"SQLALCHEMY_ENGINE_OPTIONS": custom}).config[
        "SQLALCHEMY_ENGINE_OPTIONS"] == custom


def test_responses_carry_security_headers(client):
    response = client.get("/")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"


def test_sqlite_runs_in_wal_mode(app):
    if db.engine.dialect.name != "sqlite":
        pytest.skip("WAL is a SQLite journal mode")
    assert db.session.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_database_url_is_used_as_is():
    url = "postgresql+psycopg://u:p@db.example:6543/asep"
    env = {"DATABASE_URL": url, "HOST": "other", "ADMIN": "a", "DATABASE": "d", "PASSWORD": "x"}
    assert app_module.database_uri(env) == url
    # Any other URL (SQLite for a one-off run, say) is passed through untouched.
    assert app_module.database_uri({"DATABASE_URL": "sqlite:////tmp/x.db"}) == "sqlite:////tmp/x.db"


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_database_url_postgres_schemes_use_psycopg(scheme):
    rewritten = app_module.database_uri({"DATABASE_URL": f"{scheme}://u:p@h:5432/d?sslmode=require"})
    assert rewritten == "postgresql+psycopg://u:p@h:5432/d?sslmode=require"


def test_empty_database_url_is_ignored():
    env = {"DATABASE_URL": "", "HOST": "h", "ADMIN": "u", "DATABASE": "d", "PASSWORD": "p"}
    assert app_module.database_uri(env).startswith("postgresql+psycopg://u:p@h")
    assert app_module.database_uri({"DATABASE_URL": ""}).startswith("sqlite:///")


def test_database_env_keys_build_a_psycopg_url():
    password = "p@ss:w/o#r$d"
    uri = app_module.database_uri({
        "HOST": "10.1.2.3", "PORT": "5433", "ADMIN": "asep", "DATABASE": "asep_db",
        "PASSWORD": password,
    })
    url = make_url(uri)
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.username, url.database) == ("10.1.2.3", 5433, "asep", "asep_db")
    assert url.password == password


@pytest.mark.parametrize("port", [None, ""])
def test_database_env_port_defaults_to_5432(port):
    env = {"HOST": "h", "ADMIN": "u", "DATABASE": "d", "PASSWORD": "p"}
    if port is not None:
        env["PORT"] = port
    assert make_url(app_module.database_uri(env)).port == 5432


@pytest.mark.parametrize("missing", ["HOST", "ADMIN", "DATABASE", "PASSWORD"])
@pytest.mark.parametrize("blank", [True, False])
def test_partial_database_env_falls_back_to_sqlite(missing, blank):
    env = {"HOST": "h", "PORT": "5432", "ADMIN": "u", "DATABASE": "d", "PASSWORD": "p"}
    if blank:
        env[missing] = ""
    else:
        del env[missing]
    assert app_module.database_uri(env) == app_module.database_uri({})
    assert app_module.database_uri(env).startswith("sqlite:///")


def test_sqlite_fallback_honours_asep_db():
    assert app_module.database_uri({"ASEP_DB": "/var/lib/asep/dev.db"}) == "sqlite:////var/lib/asep/dev.db"
    default = app_module.database_uri({})
    assert default == "sqlite:///" + os.path.join(app_module.BASE_DIR, "asep.db")
    assert app_module.database_uri({"ASEP_DB": ""}) == default


def test_duration_filter_formats_milliseconds():
    assert app_module.duration(0) == "0:00"
    assert app_module.duration(42_000) == "0:42"
    assert app_module.duration(125_400) == "2:05"
    assert app_module.duration(2_500) == "0:03"      # half up, same as the quiz screen
    assert app_module.duration(3_600_000) == "60:00"
    assert app_module.duration(None) == "—"
