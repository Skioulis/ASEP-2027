"""store question options as readable UTF-8 JSON

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04

"""
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

_question = sa.table("question", sa.column("id", sa.String), sa.column("options", sa.JSON))


def _rewrite_options(ensure_ascii: bool) -> None:
    """Re-serialize every question's options; the JSON values themselves don't change."""
    bind = op.get_bind()
    rows = bind.execute(sa.select(_question.c.id, _question.c.options)).all()
    if not rows:
        return
    # A bare string parameter can't be assigned to a Postgres json column.
    value = "CAST(:opts AS json)" if bind.dialect.name == "postgresql" else ":opts"
    bind.execute(
        sa.text(f"UPDATE question SET options = {value} WHERE id = :id"),
        [{"id": qid, "opts": json.dumps(options, ensure_ascii=ensure_ascii)}
         for qid, options in rows])


def upgrade():
    # Rows were written with json.dumps' default \u escapes; store readable Greek.
    _rewrite_options(ensure_ascii=False)


def downgrade():
    _rewrite_options(ensure_ascii=True)
