"""Persist ticket connector reconciliation state.

Revision ID: f7398b77ecb5
Revises: cf03ccb11945
"""

import sqlalchemy as sa
from alembic import op

revision = "f7398b77ecb5"
down_revision = "cf03ccb11945"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("external_ticket_id", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("sync_status", sa.String(30), nullable=False, server_default="pending"))


def downgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_column("sync_status")
        batch_op.drop_column("external_ticket_id")
