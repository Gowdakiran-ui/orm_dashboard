"""Phase 13: Add pipeline_runs table — single source of truth for pipeline execution

Revision ID: phase_13_pipeline_runs
Revises: phase_7_entity_discovery
Create Date: 2026-07-19 00:00:00.000000

This migration adds the pipeline_runs table which replaces Redis lock/progress
keys as the authoritative source of pipeline execution state.

No existing tables are modified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'phase_13_pipeline_runs'
down_revision: Union[str, None] = 'phase_7_entity_discovery'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pipeline_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('client_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='QUEUED'),
        sa.Column('stage', sa.String(30), nullable=False, server_default='QUEUED'),
        sa.Column('progress_pct', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_worker', sa.String(100), nullable=True),
        sa.Column('execution_mode', sa.String(20), nullable=False, server_default='async'),
        sa.Column('celery_task_id', sa.String(100), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.Column('log_tail', sa.Text(), nullable=True),
        sa.Column('duration_s', sa.Float(), nullable=True),
    )

    # Indexes for common query patterns
    op.create_index(
        'ix_pipeline_runs_client_id',
        'pipeline_runs',
        ['client_id'],
    )
    op.create_index(
        'ix_pipeline_runs_run_id',
        'pipeline_runs',
        ['run_id'],
        unique=True,
    )
    op.create_index(
        'ix_pipeline_runs_client_id_started_at',
        'pipeline_runs',
        ['client_id', 'started_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_pipeline_runs_client_id_started_at', table_name='pipeline_runs')
    op.drop_index('ix_pipeline_runs_run_id', table_name='pipeline_runs')
    op.drop_index('ix_pipeline_runs_client_id', table_name='pipeline_runs')
    op.drop_table('pipeline_runs')
