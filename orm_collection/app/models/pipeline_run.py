"""
pipeline_run.py — Phase 13

Single source of truth for every pipeline execution.
The status endpoint reads this table exclusively.
No AsyncResult. No Redis parsing.

FSM States (ordered):
    QUEUED → COLLECTING → PROCESSING → TREND → RISK →
    ALERT → NARRATIVE → REPUTATION → EXECUTIVE → BENCHMARK →
    FINALIZING → SUCCESS
                        ↘ FAILED (from any state)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, String, Integer, DateTime, Text, Float
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


# ---------------------------------------------------------------------------
# Allowed FSM transitions
# ---------------------------------------------------------------------------
_STAGE_ORDER = [
    "QUEUED",
    "COLLECTING",
    "PROCESSING",
    "TREND",
    "RISK",
    "ALERT",
    "NARRATIVE",
    "REPUTATION",
    "EXECUTIVE",
    "BENCHMARK",
    "FINALIZING",
    "SUCCESS",
]

_TERMINAL_STATES = {"SUCCESS", "FAILED"}

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {}
for _i, _s in enumerate(_STAGE_ORDER[:-1]):
    _ALLOWED_TRANSITIONS[_s] = {_STAGE_ORDER[_i + 1], "FAILED"}
_ALLOWED_TRANSITIONS["SUCCESS"] = set()
_ALLOWED_TRANSITIONS["FAILED"] = set()

# Progress percentages associated with entering each stage
STAGE_PROGRESS: dict[str, int] = {
    "QUEUED":      0,
    "COLLECTING":  5,
    "PROCESSING":  20,
    "TREND":       40,
    "RISK":        50,
    "ALERT":       60,
    "NARRATIVE":   70,
    "REPUTATION":  80,
    "EXECUTIVE":   85,
    "BENCHMARK":   90,
    "FINALIZING":  95,
    "SUCCESS":     100,
    "FAILED":      0,   # progress stays at whatever it was
}


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Correlation identifiers
    client_id = Column(String(64), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)

    # FSM state
    status = Column(String(20), nullable=False, default="QUEUED")
    stage = Column(String(30), nullable=False, default="QUEUED")
    progress_pct = Column(Integer, nullable=False, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    # Item 18 (Phase 4): started_at is set at row-creation time (QUEUED, via
    # the API endpoint) — before a worker has necessarily picked the task
    # up. duration_s (below) is therefore queue-wait + actual execution
    # combined, which the audit found silently conflated (one historical
    # row: 843s of pure queue wait inside a reported 1262s "duration").
    # processing_started_at is set separately, once a worker actually
    # acquires the pipeline lock and begins running stages, so
    # execution_duration_s can be computed as execution-only.
    processing_started_at = Column(DateTime(timezone=True), nullable=True)

    # Execution metadata
    current_worker = Column(String(100), nullable=True)
    execution_mode = Column(String(20), nullable=False, default="async")
    celery_task_id = Column(String(100), nullable=True)

    # Observability
    error_detail = Column(Text, nullable=True)
    log_tail = Column(Text, nullable=True)

    # Perf
    duration_s = Column(Float, nullable=True)  # queue-wait + execution (wall clock since started_at)
    execution_duration_s = Column(Float, nullable=True)  # execution only, since processing_started_at

    # ---------------------------------------------------------------------------
    # FSM helpers
    # ---------------------------------------------------------------------------

    def transition(self, new_stage: str, log_line: Optional[str] = None) -> None:
        """
        Advance the FSM to new_stage.

        Raises ValueError on illegal transitions so bad state never silently
        propagates. FAILED is always reachable from any non-terminal state.
        """
        current = self.status

        if current in _TERMINAL_STATES:
            raise ValueError(
                f"PipelineRun {self.run_id}: cannot transition from terminal "
                f"state {current!r} to {new_stage!r}"
            )

        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if new_stage not in allowed:
            raise ValueError(
                f"PipelineRun {self.run_id}: illegal transition "
                f"{current!r} → {new_stage!r}. Allowed: {allowed}"
            )

        self.status = new_stage
        self.stage = new_stage

        # Only override progress for FAILED if no progress set yet
        if new_stage == "FAILED":
            # Keep current progress — just mark status as FAILED
            pass
        else:
            self.progress_pct = STAGE_PROGRESS[new_stage]

        if log_line:
            self.log_tail = log_line[:2000]

        if new_stage in _TERMINAL_STATES:
            now = datetime.now(timezone.utc)
            self.finished_at = now
            if self.started_at:
                self.duration_s = (now - self.started_at).total_seconds()
            if self.processing_started_at:
                self.execution_duration_s = (now - self.processing_started_at).total_seconds()

    @property
    def is_active(self) -> bool:
        """True while the run has not reached a terminal state."""
        return self.status not in _TERMINAL_STATES

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATES
