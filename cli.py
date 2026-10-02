"""Flask CLI commands run by docker/entrypoint.sh on every container start."""

from __future__ import annotations

import os

import click
from flask import Flask, current_app
from sqlalchemy import select

import bank
from extensions import db
from models import User
from views.auth import USERNAME_RE


def ensure_admin(username: str, password: str) -> User:
    """Create the admin account, or reset an existing one to admin + this password."""
    username = username.strip().lower()
    user = db.session.scalar(select(User).filter_by(username=username))
    is_new = user is None
    if is_new:
        user = User(username=username)
        db.session.add(user)
    # Re-hashing on every start would change the session id and log the admin out.
    if is_new or not user.check_password(password):
        user.set_password(password)
    user.is_admin = True
    user.active = True
    db.session.commit()
    return user


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_command() -> None:
        """Load data/ into the database if it holds no categories yet."""
        inserted = bank.seed(current_app.config["DATA_DIR"])
        click.echo(f"Seeded {inserted} questions." if inserted
                   else "Bank already loaded; nothing to do.")

    @app.cli.command("ensure-admin")
    def ensure_admin_command() -> None:
        """Create/update the admin from ADMIN_USERNAME and ADMIN_PASSWORD."""
        username = os.environ.get("ADMIN_USERNAME", "")
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not username or not password:
            click.echo("ADMIN_USERNAME/ADMIN_PASSWORD not set; skipping.")
            return
        username = username.strip().lower()
        if not USERNAME_RE.fullmatch(username):
            raise click.ClickException("ADMIN_USERNAME must match [a-z0-9_.-]{3,32}.")
        if len(password) < 8:
            raise click.ClickException("ADMIN_PASSWORD must be at least 8 characters.")
        user = ensure_admin(username, password)
        click.echo(f"Admin '{user.username}' is ready.")
