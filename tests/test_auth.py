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


def test_rate_limiter_caps_key_length():
    limiter = RateLimiter()
    # Junk keys sharing their first MAX_KEY_LENGTH characters share one bucket.
    assert limiter.hit("a" * 128 + "x" * 10_000, 1, 60, now=0)
    assert not limiter.hit("a" * 128 + "y" * 10_000, 1, 60, now=1)
    assert len(limiter) == 1


def test_rate_limiter_prunes_expired_keys():
    limiter = RateLimiter(prune_every=1)
    for i in range(10):
        assert limiter.hit(f"k{i}", 5, 60, now=i)
    assert len(limiter) == 10          # all still inside the window
    assert limiter.hit("late", 5, 60, now=1000)
    assert len(limiter) == 1           # the ten stale keys are gone


def test_rate_limiter_keeps_keys_inside_window():
    limiter = RateLimiter(prune_every=1)
    assert limiter.hit("old", 5, 60, now=0)
    assert limiter.hit("recent", 5, 60, now=50)
    assert limiter.hit("new", 5, 60, now=100)   # "old" expired, "recent" has not
    assert len(limiter) == 2
    assert not limiter.hit("recent", 1, 60, now=101)   # its hit was kept


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


@pytest.mark.parametrize("target", [
    "//evil.example",
    "///evil.example",
    "/%09/evil.example",   # tab: stripped by Werkzeug, leaving //evil.example
    "/%0a/x",              # newline: redirect() would raise ValueError
    "/%0d/x",
    "/%5Cevil.example",    # backslash: browsers treat it as /
    "http://evil.example",
    "https://evil.example/x",
])
def test_login_rejects_unsafe_next(client, user, target):
    response = client.post(f"/login?next={target}", data={"username": "maria", "password": PASSWORD})
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_login_keeps_local_next_with_query_string(client, user):
    response = client.post("/login?next=%2F%3Fcategory%3Dalpha%26start%3Dquiz",
                           data={"username": "maria", "password": PASSWORD})
    assert response.headers["Location"] == "/?category=alpha&start=quiz"


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
