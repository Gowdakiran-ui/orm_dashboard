"""phase_4_2_trend_accuracy

Revision ID: 5db69e61bbb2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-26 15:29:39.212441

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5db69e61bbb2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("trend_events", sa.Column("trend_direction", sa.String(length=50), nullable=True))
    op.add_column("trend_events", sa.Column("decision_reason", sa.Text(), nullable=True))
    op.add_column("trend_events", sa.Column("triggering_documents", sa.JSON(), nullable=True))
    op.add_column("trend_events", sa.Column("time_window", sa.String(length=50), nullable=True, server_default="24h_vs_7d"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("trend_events", "time_window")
    op.drop_column("trend_events", "triggering_documents")
    op.drop_column("trend_events", "decision_reason")
    op.drop_column("trend_events", "trend_direction")

