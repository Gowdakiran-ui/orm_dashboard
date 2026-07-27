"""phase_6_1_alert_reliability

Revision ID: 4cdcbf89cc1b
Revises: 2d3cc4ebe86e
Create Date: 2026-06-27 13:26:20.499655

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cdcbf89cc1b'
down_revision: Union[str, None] = '2d3cc4ebe86e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create alert_client_states table
    op.create_table(
        "alert_client_states",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("processing_status", sa.String(length=30), nullable=False, server_default="ALERT_PENDING"),
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
    op.create_index("ix_alert_client_states_client_id", "alert_client_states", ["client_id"], unique=True)

    # 2. Add columns to alerts table
    op.add_column("alerts", sa.Column("processing_status", sa.String(length=30), nullable=False, server_default="ALERT_PENDING"))
    op.add_column("alerts", sa.Column("run_id", sa.String(length=64), nullable=True))
    op.add_column("alerts", sa.Column("batch_id", sa.String(length=64), nullable=True))
    op.add_column("alerts", sa.Column("worker_id", sa.String(length=64), nullable=True))
    op.add_column("alerts", sa.Column("latency_ms", sa.Float(), nullable=True))
    op.add_column("alerts", sa.Column("retry_count", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("alerts", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column("alerts", sa.Column("state_history", sa.JSON(), nullable=True))

    # 3. Clean up existing duplicates in alerts before applying unique index
    op.execute("""
        DELETE FROM alerts a USING alerts b 
        WHERE a.id < b.id 
          AND a.client_id = b.client_id 
          AND a.alert_type = b.alert_type 
          AND COALESCE(a.entity_id::text, '') = COALESCE(b.entity_id::text, '') 
          AND COALESCE(a.document_id::text, '') = COALESCE(b.document_id::text, '')
    """)

    # 4. Create functional unique index on alerts
    op.execute(
        "CREATE UNIQUE INDEX uq_alerts_business ON alerts "
        "(client_id, alert_type, COALESCE(entity_id::text, ''), COALESCE(document_id::text, ''))"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Drop functional unique index
    op.execute("DROP INDEX IF EXISTS uq_alerts_business")

    # 2. Drop columns from alerts
    op.drop_column("alerts", "state_history")
    op.drop_column("alerts", "failure_reason")
    op.drop_column("alerts", "retry_count")
    op.drop_column("alerts", "latency_ms")
    op.drop_column("alerts", "worker_id")
    op.drop_column("alerts", "batch_id")
    op.drop_column("alerts", "run_id")
    op.drop_column("alerts", "processing_status")

    # 3. Drop alert_client_states table
    op.drop_index("ix_alert_client_states_client_id", table_name="alert_client_states")
    op.drop_table("alert_client_states")

