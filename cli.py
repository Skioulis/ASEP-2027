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
