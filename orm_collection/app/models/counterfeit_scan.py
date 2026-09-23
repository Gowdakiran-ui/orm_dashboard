import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base


class CounterfeitScan(Base):
    """
    Status/history row for the Counterfeit Detection page's two on-demand
    tools (deepfake image scan via Reality Defender, counterfeit/typosquat
    domain scan via WhoisFreaks + Bolster.ai). One row per user-triggered
    scan -- this IS the source of truth the status-poll endpoint reads
    (same PipelineRun convention: no AsyncResult, no Redis parsing).

    A scan that produces a live/malicious domain or a genuinely
    deepfake-flagged image also gets a RiskEvent (via a synthetic Document
    row -- see counterfeit_detection.py -- so it doesn't collide with the
    uq_risk_events_daily unique index, which collapses to one row per
    client when document_id and entity_id are both null). risk_event_id is
    nullable because a clean result never creates one.
    """
    __tablename__ = "counterfeit_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)

    scan_type = Column(String(20), nullable=False)  # 'deepfake' | 'domain'
    status = Column(String(20), nullable=False, default="QUEUED")  # QUEUED | PROCESSING | COMPLETE | FAILED

    # Deepfake: original filename. Domain: the brand keyword/domain searched.
    input_summary = Column(String(255), nullable=True)

    # Structured result once COMPLETE: deepfake -> {verdict, confidence_score, ...};
    # domain -> {candidates: [{domain, registrar, registered_at, live, malicious}, ...]}.
    result = Column(JSON, nullable=True)

    error_message = Column(Text, nullable=True)

    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    risk_event_id = Column(UUID(as_uuid=True), ForeignKey("risk_events.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
