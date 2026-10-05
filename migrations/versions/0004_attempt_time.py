"""record how long each quiz answer took

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('attempt', schema=None) as batch_op:
        batch_op.add_column(sa.Column('time_ms', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('attempt', schema=None) as batch_op:
        batch_op.drop_column('time_ms')
