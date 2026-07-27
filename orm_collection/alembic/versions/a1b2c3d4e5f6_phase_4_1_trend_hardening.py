"""Phase 4.1 Trend Hardening — State Machine, Deduplication, Observability

Revision ID: a1b2c3d4e5f6
Revises: 0b186a3e0525
Create Date: 2026-06-26 14:50:00.000000

Changes:
  1. trend_events — add run_id, batch_id, trend_date, baseline_established
  2. trend_events — add functional unique index for duplicate protection
  3. trend_client_states — new table for per-client state machine
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd3f756dc2572'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Phase 4.1 upgrades."""

    # -----------------------------------------------------------------------
    # 1. Add new columns to trend_events
    # -----------------------------------------------------------------------
    op.add_column(
        'trend_events',
        sa.Column('run_id', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'trend_events',
        sa.Column('batch_id', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'trend_events',
        sa.Column('trend_date', sa.Date(), nullable=True)
    )
    op.add_column(
        'trend_events',
        sa.Column(
            'baseline_established',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true')
        )
    )

    # Backfill trend_date from created_at for existing rows
    op.execute(
        "UPDATE trend_events SET trend_date = DATE(created_at) WHERE trend_date IS NULL"
    )

    # Index on trend_date for range queries
    op.create_index(
        'ix_trend_events_trend_date',
        'trend_events',
        ['trend_date'],
        unique=False
    )

    # -----------------------------------------------------------------------
    # 2. Functional unique index for duplicate protection (R5)
    #
    # IMPORTANT: The forensic audit confirmed duplicate TrendEvent rows exist
    # in production. Before creating the unique index, we must deduplicate
    # existing rows, keeping the most recently created row per key.
    #
    # Effective constraint after cleanup:
    #   UNIQUE (client_id, trend_type, COALESCE(entity_id::text,''),
    #           COALESCE(topic_id::text,''), trend_date)
    # -----------------------------------------------------------------------

    # Step 2a: Deduplicate existing rows — delete all but the MAX id per key
    op.execute("""
        DELETE FROM trend_events
        WHERE id NOT IN (
            SELECT DISTINCT ON (
                client_id,
                trend_type,
                COALESCE(entity_id::text, ''),
                COALESCE(topic_id::text, ''),
                trend_date
            ) id
            FROM trend_events
            ORDER BY
                client_id,
                trend_type,
                COALESCE(entity_id::text, ''),
                COALESCE(topic_id::text, ''),
                trend_date,
                created_at DESC NULLS LAST
        )
    """)

    # Step 2b: Create the functional unique index now that duplicates are gone
    op.execute("""
        CREATE UNIQUE INDEX uq_trend_events_daily
        ON trend_events (
            client_id,
            trend_type,
            COALESCE(entity_id::text, ''),
            COALESCE(topic_id::text, ''),
            trend_date
        )
        WHERE trend_date IS NOT NULL
    """)

    # -----------------------------------------------------------------------
    # 3. Create trend_client_states table (R2 — State Machine)
    # -----------------------------------------------------------------------
    op.create_table(
        'trend_client_states',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('processing_status', sa.String(length=30), nullable=False,
                  server_default='TREND_PENDING'),
        sa.Column('run_id', sa.String(length=64), nullable=True),
        sa.Column('batch_id', sa.String(length=64), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id', name='uq_trend_client_states_client_id')
    )
    op.create_index(
        'ix_trend_client_states_client_id',
        'trend_client_states',
        ['client_id'],
        unique=True
    )
    op.create_index(
        'ix_trend_client_states_processing_status',
        'trend_client_states',
        ['processing_status'],
        unique=False
    )


def downgrade() -> None:
    """Reverse Phase 4.1 upgrades."""

    # Drop trend_client_states
    op.drop_index('ix_trend_client_states_processing_status', table_name='trend_client_states')
    op.drop_index('ix_trend_client_states_client_id', table_name='trend_client_states')
    op.drop_table('trend_client_states')

    # Drop functional unique index
    op.execute("DROP INDEX IF EXISTS uq_trend_events_daily")

    # Drop trend_events index
    op.drop_index('ix_trend_events_trend_date', table_name='trend_events')

    # Drop new columns from trend_events
    op.drop_column('trend_events', 'baseline_established')
    op.drop_column('trend_events', 'trend_date')
    op.drop_column('trend_events', 'batch_id')
    op.drop_column('trend_events', 'run_id')
