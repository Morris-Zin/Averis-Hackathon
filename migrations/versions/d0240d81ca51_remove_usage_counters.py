"""Remove obsolete application usage quotas."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0240d81ca51"
down_revision: str | Sequence[str] | None = "a83d6f9e2741"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("counters")


def downgrade() -> None:
    op.create_table(
        "counters",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
