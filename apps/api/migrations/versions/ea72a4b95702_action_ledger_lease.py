"""Track the current ticket sync claim lease separately from audit creation time.

Revision ID: ea72a4b95702
Revises: f7398b77ecb5
"""

import sqlalchemy as sa
from alembic import op

revision = "ea72a4b95702"
down_revision = "f7398b77ecb5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("action_ledger") as batch_op:
        batch_op.add_column(sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("action_ledger") as batch_op:
        batch_op.drop_column("lease_until")
