"""Database models: the question bank, user accounts, and answer attempts.

Deletes cascade through the ORM relationships (not SQLite foreign-key
pragmas), so deleting a question or a user also deletes its attempts.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

from flask import current_app
from flask_login import UserMixin
from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(default=0)

    questions: Mapped[list[Question]] = relationship(
        back_populates="category", order_by="Question.number",
        cascade="all, delete-orphan")


class Question(db.Model):
    # "<category slug>-<number in the PDF>", e.g. "dioikitiko-dikaio-57".
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), index=True)
    number: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    # Exactly four option strings, index 0-3 = α/β/γ/δ.
    options: Mapped[list[str]] = mapped_column(JSON)
    correct: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    category: Mapped[Category] = relationship(back_populates="questions")
    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="question", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        """The compact shape the frontend and the JSON files use."""
        return {"id": self.id, "n": self.number, "q": self.text,
                "a": list(self.options), "c": self.correct,
                "category": self.category.slug}


class User(UserMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lowercase; restricted to [a-z0-9_.-] by the register form.
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    # Named "active" because UserMixin already defines the is_active property.
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime | None]

    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="user", cascade="all, delete-orphan")

    @property
    def is_active(self) -> bool:
        """Flask-Login refuses to log in users whose is_active is False."""
        return self.active

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def session_stamp(self) -> str:
        """Short keyed fingerprint of the current password hash."""
        return hmac.new(current_app.secret_key.encode(), self.password_hash.encode(),
                        hashlib.sha256).hexdigest()[:16]

    def get_id(self) -> str:
        """Flask-Login session/remember-cookie id: ``<id>:<password fingerprint>``.

        Changing the password changes the id, which logs out old sessions and
        remember cookies.
        """
        return f"{self.id}:{self.session_stamp()}"


class Attempt(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    question_id: Mapped[str] = mapped_column(ForeignKey("question.id"))
    chosen: Mapped[int]
    is_correct: Mapped[bool]
    mode: Mapped[str] = mapped_column(String(10))  # "quiz" | "browse"
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = relationship(back_populates="attempts")
    question: Mapped[Question] = relationship(back_populates="attempts")

    __table_args__ = (Index("ix_attempt_user_question", "user_id", "question_id"),)


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    # Returning None logs the user out on their next request: for disabled
    # users, and for ids minted before the password last changed.
    parts = user_id.split(":")
    if len(parts) != 2 or not (parts[0].isascii() and parts[0].isdigit()):
        return None
    user = db.session.get(User, int(parts[0]))
    if user is None or not user.active:
        return None
    # Compare as bytes: compare_digest rejects non-ASCII str.
    if not hmac.compare_digest(user.session_stamp().encode(), parts[1].encode()):
        return None
    return user
