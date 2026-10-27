"""Run Pipeline catch-up: PENDING documents from the shared social search sources (search://youtube ...) are picked up."""
import datetime as dt
import os
import sys
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.document import Document
from app.models.source import Source, SourceCategory
from app.workers.aggregation_tasks import _stale_pending_search_doc_ids, SEARCH_PENDING_STALE_HOURS

NOW = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)


@compiles(PG_UUID, 'sqlite')
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, 'sqlite')
def _jsonb(element, compiler, **kw):
    return "TEXT"


def _db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _source(db, url, stype="youtube"):
    cat = db.query(SourceCategory).first()
    if cat is None:
        cat = SourceCategory(id=uuid.uuid4(), name="Video Search")
        db.add(cat)
        db.flush()
    s = Source(id=uuid.uuid4(), category_id=cat.id, name=url, source_type=stype, url=url, schedule_cron="* * * * *")
    db.add(s)
    db.flush()
    return s


def _doc(db, source, status="PENDING", age_hours=48, title="Godrej Blue | South Kolkata"):
    d = Document(id=uuid.uuid4(), url=f"http://x/{uuid.uuid4()}", title=title, normalized_content="x", document_type=source.source_type,
                 source_id=source.id, processing_status=status)
    db.add(d)
    db.flush()
    db.query(Document).filter(Document.id == d.id).update({"collected_at": NOW - dt.timedelta(hours=age_hours)})
    db.commit()
    return d


def test_old_pending_documents_of_the_shared_search_sources_are_picked_up():
    db = _db()
    yt, ig, feed = _source(db, "search://youtube"), _source(db, "search://instagram", "instagram"), _source(db, "https://news.example/rss", "rss")
    old_yt, old_ig = _doc(db, yt, age_hours=72), _doc(db, ig, age_hours=5)
    fresh = _doc(db, yt, age_hours=SEARCH_PENDING_STALE_HOURS - 0.5)      # a collection may still be working on it
    done = _doc(db, yt, status="MATCHED", age_hours=72)
    feed_doc = _doc(db, feed, age_hours=72)                                # feed sources keep their own pickup path
    ids = _stale_pending_search_doc_ids(db, now=NOW)
    assert ids == [str(old_yt.id), str(old_ig.id)]                         # oldest first
    assert str(fresh.id) not in ids and str(done.id) not in ids and str(feed_doc.id) not in ids


def test_the_catch_up_is_bounded_by_the_limit():
    db = _db()
    yt = _source(db, "search://youtube")
    for i in range(5):
        _doc(db, yt, age_hours=10 + i)
    assert len(_stale_pending_search_doc_ids(db, now=NOW, limit=3)) == 3


def test_nothing_pending_means_nothing_added():
    db = _db()
    _source(db, "search://youtube")
    assert _stale_pending_search_doc_ids(db, now=NOW) == []
