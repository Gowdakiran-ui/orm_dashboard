"""phase_6_2_alert_accuracy

Revision ID: d591a620c92a
Revises: 4cdcbf89cc1b
Create Date: 2026-06-27 14:44:07.527498

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd591a620c92a'
down_revision: Union[str, None] = '4cdcbf89cc1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('alerts', sa.Column('confidence_score', sa.Float(), nullable=True))
    op.add_column('alerts', sa.Column('evidence_score', sa.Float(), nullable=True))
    op.add_column('alerts', sa.Column('article_count', sa.Integer(), nullable=True, server_default='1'))
    op.add_column('alerts', sa.Column('supporting_signals', sa.JSON(), nullable=True))
    op.add_column('alerts', sa.Column('explainability', sa.JSON(), nullable=True))
    op.add_column('alerts', sa.Column('lifecycle_status', sa.String(length=30), nullable=False, server_default='NEW'))
    op.add_column('alerts', sa.Column('lifecycle_history', sa.JSON(), nullable=True))
    op.add_column('alerts', sa.Column('escalation_history', sa.JSON(), nullable=True))
    op.add_column('alerts', sa.Column('human_summary', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('alerts', 'human_summary')
    op.drop_column('alerts', 'escalation_history')
    op.drop_column('alerts', 'lifecycle_history')
    op.drop_column('alerts', 'lifecycle_status')
    op.drop_column('alerts', 'explainability')
    op.drop_column('alerts', 'supporting_signals')
    op.drop_column('alerts', 'article_count')
    op.drop_column('alerts', 'evidence_score')
    op.drop_column('alerts', 'confidence_score')
