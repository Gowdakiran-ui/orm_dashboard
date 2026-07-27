"""phase_5_1_risk_hardening

Revision ID: 7222e184965d
Revises: 5db69e61bbb2
Create Date: 2026-06-26 16:22:49.407101

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7222e184965d'
down_revision: Union[str, None] = '5db69e61bbb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create risk_client_states table
    op.create_table(
        "risk_client_states",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("processing_status", sa.String(length=30), nullable=False, server_default="RISK_PENDING"),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("batch_id", sa.String(length=64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"))
    )
    op.create_index("ix_risk_client_states_client_id", "risk_client_states", ["client_id"], unique=True)

    # 2. Add observability columns to risk_events
    op.add_column("risk_events", sa.Column("run_id", sa.String(length=64), nullable=True))
    op.add_column("risk_events", sa.Column("batch_id", sa.String(length=64), nullable=True))
    op.add_column("risk_events", sa.Column("worker_id", sa.String(length=64), nullable=True))
    op.add_column("risk_events", sa.Column("latency_ms", sa.Float(), nullable=True))
    op.add_column("risk_events", sa.Column("retry_count", sa.Integer(), nullable=True, server_default="0"))

    # 3. Clean up existing duplicates in risk_events before applying unique index
    op.execute("""
        DELETE FROM risk_events a USING risk_events b 
        WHERE a.id < b.id 
          AND a.client_id = b.client_id 
          AND COALESCE(a.document_id::text, '') = COALESCE(b.document_id::text, '') 
          AND COALESCE(a.entity_id::text, '') = COALESCE(b.entity_id::text, '')
    """)

    # 4. Create functional unique index on risk_events
    op.execute(
        "CREATE UNIQUE INDEX uq_risk_events_daily ON risk_events "
        "(client_id, COALESCE(document_id::text, ''), COALESCE(entity_id::text, ''))"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Drop functional unique index
    op.execute("DROP INDEX IF EXISTS uq_risk_events_daily")

    # 2. Drop columns from risk_events
    op.drop_column("risk_events", "retry_count")
    op.drop_column("risk_events", "latency_ms")
    op.drop_column("risk_events", "worker_id")
    op.drop_column("risk_events", "batch_id")
    op.drop_column("risk_events", "run_id")

    # 3. Drop risk_client_states table
    op.drop_index("ix_risk_client_states_client_id", table_name="risk_client_states")
    op.drop_table("risk_client_states")

