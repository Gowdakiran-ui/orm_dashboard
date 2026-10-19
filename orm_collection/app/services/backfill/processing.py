"""
Feeding backfilled documents to NLP: priority order, per-client cap, resumable on request.

Backfilled documents stay PENDING under a per-client `backfill://<client_id>/<source>` source (the live
pipeline's PENDING sweep never sees them). They are handed to the NLP queue here, in this order:
  1. documents whose title/summary contain a risk keyword (complaint, RERA, court, refund, ...)
  2. then newest first
and only until BACKFILL_MAX_PROCESS_DOCS_PER_CLIENT documents per client have been handed over. The rest stay
PENDING until `python -m app.services.backfill.cli --client X --continue-processing`.
"""
from typing import Callable, Dict, List, Optional

import datetime as dt
import structlog
from sqlalchemy import case, or_

from app.services.backfill import settings as bf_settings
from app.services.backfill.queries import RISK_TERMS

logger = structlog.get_logger()

NLP_TASK = "app.workers.intelligence_tasks.process_document_intelligence"


def _source_like(client_id) -> str:
    return f"backfill://{client_id}/%"


def processed_count(db, client_id) -> int:
    """Documents of this client's backfill already handed to NLP (anything that is no longer PENDING)."""
    from app.models.document import Document
    from app.models.source import Source
    return db.query(Document.id).join(Source, Source.id == Document.source_id).filter(
        Source.url.like(_source_like(client_id)), Document.processing_status != "PENDING",
    ).count()


def pending_count(db, client_id) -> int:
    from app.models.document import Document
    from app.models.source import Source
    return db.query(Document.id).join(Source, Source.id == Document.source_id).filter(
        Source.url.like(_source_like(client_id)), Document.processing_status == "PENDING",
    ).count()


def clients_with_pending(db) -> List[str]:
    from app.models.document import Document
    from app.models.source import Source
    urls = db.query(Source.url).join(Document, Document.source_id == Source.id).filter(
        Source.url.like("backfill://%"), Document.processing_status == "PENDING",
    ).distinct().all()
    return sorted({u[0].split("/")[2] for u in urls if u[0].count("/") >= 3})


def next_batch(db, client_id, limit: int) -> List:
    """PENDING documents in priority order: risk-keyword hits first, then newest published first."""
    from app.models.document import Document
    from app.models.source import Source
    risk_hit = or_(*[Document.title.ilike(f"%{t}%") for t in RISK_TERMS],
                   *[Document.normalized_content.ilike(f"%{t}%") for t in RISK_TERMS])
    return db.query(Document.id).join(Source, Source.id == Document.source_id).filter(
        Source.url.like(_source_like(client_id)), Document.processing_status == "PENDING",
    ).order_by(case((risk_hit, 0), else_=1), Document.published_at.desc().nullslast()).limit(limit).all()


def _default_send(doc_id: str, client_id: str) -> None:
    from app.core.celery_app import celery_app
    celery_app.send_task(NLP_TASK, args=[doc_id, client_id], queue="nlp_queue")


def dispatch(db, client_id, limit: int, respect_cap: bool = True, cap: Optional[int] = None,
             send: Optional[Callable[[str, str], None]] = None) -> Dict[str, int]:
    """
    Hand up to `limit` PENDING documents of this client's backfill to NLP, in priority order.
    With respect_cap, never lets the client's handed-over total pass the cap.
    Returns {"dispatched", "cap_remaining", "pending_left"}.
    """
    from app.models.document import Document
    cap = bf_settings.MAX_PROCESS_DOCS_PER_CLIENT if cap is None else cap
    room = max(0, cap - processed_count(db, client_id)) if respect_cap else limit
    n = min(limit, room)
    ids = [r[0] for r in next_batch(db, client_id, n)] if n > 0 else []
    if ids:
        now = dt.datetime.now(dt.timezone.utc)
        db.query(Document).filter(Document.id.in_(ids)).update(
            {"processing_status": "PROCESSING", "processing_started_at": now}, synchronize_session=False)
        db.commit()
        send = send or _default_send
        for doc_id in ids:
            send(str(doc_id), str(client_id))
    return {"dispatched": len(ids), "cap_remaining": max(0, room - len(ids)) if respect_cap else -1,
            "pending_left": pending_count(db, client_id)}
