"""add_explainability_and_reliability_to_risk_events

Revision ID: 2d3cc4ebe86e
Revises: 7222e184965d
Create Date: 2026-06-27 08:04:32.546764

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d3cc4ebe86e'
down_revision: Union[str, None] = '7222e184965d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('risk_events', sa.Column('source_reliability', sa.Float(), nullable=True))
    op.add_column('risk_events', sa.Column('explainability', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('risk_events', 'explainability')
    op.drop_column('risk_events', 'source_reliability')
