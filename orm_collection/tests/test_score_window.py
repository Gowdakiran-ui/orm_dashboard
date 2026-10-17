"""
Scoring windows use the document's published_at, not ingestion time.
An old article that we only ingested today must NOT count as recent.
"""
import os
import sys
import uuid
import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.document import Document
from app.models.risk import RiskEvent
from app.models.alert import Alert
from app.services.intelligence.score_window import in_window


@compiles(PG_UUID, 'sqlite')
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, 'sqlite')
def _jsonb(element, compiler, **kw):
    return "TEXT"


_engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(_engine)
Session = sessionmaker(bind=_engine)

NOW = datetime.datetime.now(datetime.timezone.utc)
LOOKBACK = NOW - datetime.timedelta(days=30)


def _doc(db, published_at):
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", normalized_content="x", published_at=published_at)
    db.add(d)
    return d


def _mention(db, ent, doc, created_at):
    m = EntityMention(document_id=doc.id, entity_id=ent.id, mention_count=1, created_at=created_at)
    db.add(m)
    return m


def _setup(db):
    c = Client(id=uuid.uuid4(), name=f"C-{uuid.uuid4()}")
    e = Entity(id=uuid.uuid4(), client_id=c.id, name="C", entity_type="brand")
    db.add_all([c, e])
    db.flush()
    return c, e


def test_old_article_ingested_today_is_not_recent():
    db = Session()
    c, e = _setup(db)
    old = _doc(db, NOW - datetime.timedelta(days=400))   # published 400 days ago
    new = _doc(db, NOW - datetime.timedelta(days=3))     # published 3 days ago
    _mention(db, e, old, NOW)   # but BOTH ingested today
    _mention(db, e, new, NOW)
    db.commit()

    rows = db.query(EntityMention).filter(
        EntityMention.entity_id == e.id,
        in_window(EntityMention.created_at, EntityMention.document_id, LOOKBACK)
    ).all()
    assert [r.document_id for r in rows] == [new.id]


def test_recent_article_ingested_long_ago_is_still_recent():
    db = Session()
    c, e = _setup(db)
    d = _doc(db, NOW - datetime.timedelta(days=2))
    _mention(db, e, d, NOW - datetime.timedelta(days=90))   # old ingestion row, recent article
    db.commit()
    assert db.query(EntityMention).filter(
        EntityMention.entity_id == e.id,
        in_window(EntityMention.created_at, EntityMention.document_id, LOOKBACK)
    ).count() == 1


def test_missing_published_at_falls_back_to_created_at():
    db = Session()
    c, e = _setup(db)
    undated = _doc(db, None)
    _mention(db, e, undated, NOW - datetime.timedelta(days=1))    # counted
    undated2 = _doc(db, None)
    _mention(db, e, undated2, NOW - datetime.timedelta(days=60))  # not counted
    db.commit()
    rows = db.query(EntityMention).filter(
        EntityMention.entity_id == e.id,
        in_window(EntityMention.created_at, EntityMention.document_id, LOOKBACK)
    ).all()
    assert [r.document_id for r in rows] == [undated.id]


def test_risk_event_and_alert_use_document_date_and_allow_null_document():
    db = Session()
    c, e = _setup(db)
    old = _doc(db, NOW - datetime.timedelta(days=400))
    db.flush()
    db.add(RiskEvent(client_id=c.id, document_id=old.id, risk_score=50.0, risk_level="HIGH", created_at=NOW))
    db.add(RiskEvent(client_id=c.id, document_id=None, risk_score=50.0, risk_level="HIGH", created_at=NOW))
    db.add(Alert(client_id=c.id, document_id=old.id, alert_type="Risk", severity="HIGH", title="a", created_at=NOW))
    db.commit()

    risks = db.query(RiskEvent).filter(RiskEvent.client_id == c.id, in_window(RiskEvent.created_at, RiskEvent.document_id, LOOKBACK)).all()
    assert len(risks) == 1 and risks[0].document_id is None   # old-doc event excluded, no-doc event kept
    assert db.query(Alert).filter(Alert.client_id == c.id, in_window(Alert.created_at, Alert.document_id, LOOKBACK)).count() == 0
