"""Flask application factory for the ASEP 2027 question bank."""

from __future__ import annotations

import os

from flask import Flask, render_template
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


app = create_app()
