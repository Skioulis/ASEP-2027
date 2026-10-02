"""Shared Flask extensions.

Kept in their own module so ``app``, ``models`` and the views can all import
them without circular imports.
"""

from __future__ import annotations

import sqlite3

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base enabling SQLAlchemy 2.0 typed models (Mapped[...])."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def _use_sqlite_wal(dbapi_connection, connection_record) -> None:
    # WAL lets concurrent gunicorn workers/threads read while one of them writes.
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
