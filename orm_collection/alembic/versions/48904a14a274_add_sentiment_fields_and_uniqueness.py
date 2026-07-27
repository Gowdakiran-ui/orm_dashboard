"""add_sentiment_fields_and_uniqueness

Revision ID: 48904a14a274
Revises: 4e75afd0f858
Create Date: 2026-06-26 09:34:07.537004

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48904a14a274'
down_revision: Union[str, None] = '4e75afd0f858'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add sentiment-related columns to the documents table
    op.add_column('documents', sa.Column('sentiment_processing_status', sa.String(length=30), nullable=True, server_default='SENTIMENT_PENDING'))
    op.add_column('documents', sa.Column('sentiment_retry_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('documents', sa.Column('sentiment_failed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('sentiment_failure_reason', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('sentiment_run_id', sa.String(length=64), nullable=True))
    op.add_column('documents', sa.Column('sentiment_batch_id', sa.String(length=64), nullable=True))
    op.add_column('documents', sa.Column('sentiment_processing_time_ms', sa.Float(), nullable=True))

    # 2. Cleanup existing duplicate rows in document_sentiments (keep only the latest one based on created_at or id)
    op.execute("""
        DELETE FROM document_sentiments a USING document_sentiments b
        WHERE a.created_at < b.created_at AND a.document_id = b.document_id
    """)
    # Tie-breaker delete for exact matching timestamps:
    op.execute("""
        DELETE FROM document_sentiments a USING document_sentiments b
        WHERE a.id < b.id AND a.document_id = b.document_id
    """)

    # 3. Cleanup existing duplicate rows in entity_sentiments
    op.execute("""
        DELETE FROM entity_sentiments a USING entity_sentiments b
        WHERE a.created_at < b.created_at AND a.document_id = b.document_id AND a.entity_id = b.entity_id
    """)
    op.execute("""
        DELETE FROM entity_sentiments a USING entity_sentiments b
        WHERE a.id < b.id AND a.document_id = b.document_id AND a.entity_id = b.entity_id
    """)

    # 4. Add unique constraints to prevent future duplicates
    op.create_unique_constraint('uq_document_sentiments_document_id', 'document_sentiments', ['document_id'])
    op.create_unique_constraint('uq_entity_sentiments_doc_entity', 'entity_sentiments', ['document_id', 'entity_id'])


def downgrade() -> None:
    op.drop_constraint('uq_entity_sentiments_doc_entity', 'entity_sentiments', type_='unique')
    op.drop_constraint('uq_document_sentiments_document_id', 'document_sentiments', type_='unique')

    op.drop_column('documents', 'sentiment_processing_time_ms')
    op.drop_column('documents', 'sentiment_batch_id')
    op.drop_column('documents', 'sentiment_run_id')
    op.drop_column('documents', 'sentiment_failure_reason')
    op.drop_column('documents', 'sentiment_failed_at')
    op.drop_column('documents', 'sentiment_retry_count')
    op.drop_column('documents', 'sentiment_processing_status')
