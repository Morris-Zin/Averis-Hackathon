"""Record successful provider usage settlement

Revision ID: a83d6f9e2741
Revises: 6c4266208142
Create Date: 2026-09-19 23:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a83d6f9e2741"
down_revision: str | Sequence[str] | None = "6c4266208142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add reserved rates, usage, settlement, and reconciliation audit fields."""
    op.add_column(
        "reservations",
        sa.Column("input_usd_per_million", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "reservations",
        sa.Column("output_usd_per_million", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "reservations", sa.Column("actual_amount", sa.Integer(), nullable=True)
    )
    op.add_column(
        "reservations", sa.Column("input_tokens", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "reservations", sa.Column("output_tokens", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "reservations",
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "reservations",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reservations", sa.Column("reconciliation_issue", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Remove usage settlement audit fields."""
    op.drop_column("reservations", "reconciliation_issue")
    op.drop_column("reservations", "settled_at")
    op.drop_column("reservations", "provider_request_id")
    op.drop_column("reservations", "output_tokens")
    op.drop_column("reservations", "input_tokens")
    op.drop_column("reservations", "actual_amount")
    op.drop_column("reservations", "output_usd_per_million")
    op.drop_column("reservations", "input_usd_per_million")
