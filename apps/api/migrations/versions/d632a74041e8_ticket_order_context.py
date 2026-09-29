"""Persist verified order context in support ticket handoffs.

Revision ID: d632a74041e8
Revises: ea72a4b95702
"""

import sqlalchemy as sa
from alembic import op

revision = "d632a74041e8"
down_revision = "ea72a4b95702"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("order_context", sa.JSON(), nullable=False,
                                      server_default=sa.text("'[]'")))


def downgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_column("order_context")
