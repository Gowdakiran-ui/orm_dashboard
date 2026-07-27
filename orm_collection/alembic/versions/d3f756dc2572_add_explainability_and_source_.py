"""add_explainability_and_source_reliability_to_sentiment

Revision ID: d3f756dc2572
Revises: 48904a14a274
Create Date: 2026-06-26 12:22:51.579887

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f756dc2572'
down_revision: Union[str, None] = '48904a14a274'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document_sentiments', sa.Column('explainability_metadata', sa.JSON(), nullable=True))
    op.add_column('entity_sentiments', sa.Column('explainability_metadata', sa.JSON(), nullable=True))

def downgrade() -> None:
    op.drop_column('entity_sentiments', 'explainability_metadata')
    op.drop_column('document_sentiments', 'explainability_metadata')
