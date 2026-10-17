"""
Scoring-window helper.

The 30-day scoring windows used to filter on the *ingestion* time of an
EntityMention / RiskEvent / Alert (``created_at``). That meant anything we
ingested late (a historical backfill, a slow feed, a manual Run Pipeline after
two weeks of silence) counted as "recent" no matter how old the article was.

``in_window`` filters on the *document's* ``published_at`` instead, and falls
back to the row's own ``created_at`` only when the document has no published
date (or the row has no document), so rows we cannot date are never silently
dropped from the score.

``created_at`` is deliberately left alone everywhere it means "new to us"
(has_recent_risk, entity-discovery, stored-score freshness): only the
"last N days of coverage" windows go through here.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.models.document import Document


def effective_date(created_col, document_id_col):
    """Document published_at, else the row's created_at."""
    d = aliased(Document)
    published = select(d.published_at).where(d.id == document_id_col).scalar_subquery()
    return func.coalesce(published, created_col)


def in_window(created_col, document_id_col, lookback_date):
    """SQL clause: this row's coverage date is on/after lookback_date."""
    return effective_date(created_col, document_id_col) >= lookback_date
