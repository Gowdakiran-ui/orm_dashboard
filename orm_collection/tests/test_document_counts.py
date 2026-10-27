"""/documents/client/{id}/counts: true totals over every visible document, not the newest-500 window."""
import os
import sys
import uuid

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

import app.api.endpoints.client_intelligence  # imports every model so create_all sees every table
import app.api.endpoints.documents as docs_ep
from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity
from app.models.document import Document, DocumentMatch
from app.models.sentiment import DocumentSentiment
from app.models.topic import Topic, DocumentTopic


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _setup(db, n_docs):
    c = Client(id=uuid.uuid4(), name="Acme")
    db.add(c)
    db.commit()
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name="Acme", entity_type="brand")
    db.add(brand)
    db.commit()
    topic_a, topic_b = Topic(id=uuid.uuid4(), name="Legal"), Topic(id=uuid.uuid4(), name="Product")
    db.add_all([topic_a, topic_b])
    db.commit()
    docs = []
    for i in range(n_docs):
        d = Document(id=uuid.uuid4(), url=f"http://t.test/{i}", normalized_content="x", title=f"t{i}")
        db.add(d)
        db.add(DocumentMatch(document_id=d.id, matched_entity_id=brand.id))
        docs.append(d)
    db.commit()
    return c, docs, topic_a, topic_b


def _sent(db, d, score):
    db.add(DocumentSentiment(document_id=d.id, sentiment_score=score, sentiment_label="x", confidence_score=0.9, weighted_sentiment_score=score))
    db.commit()


def test_counts_cover_every_visible_document_not_just_the_listed_500(db):
    c, docs, ta, tb = _setup(db, 503)
    for d in docs[:3]:
        _sent(db, d, 0.8)         # positive
    for d in docs[3:5]:
        _sent(db, d, -0.8)        # negative
    _sent(db, docs[5], 0.1)       # neutral
    db.add(DocumentTopic(document_id=docs[0].id, topic_id=ta.id, confidence_score=0.4))
    db.add(DocumentTopic(document_id=docs[0].id, topic_id=tb.id, confidence_score=0.9))   # the higher-confidence one wins
    db.add(DocumentTopic(document_id=docs[1].id, topic_id=ta.id, confidence_score=0.7))
    db.commit()
    out = docs_ep.read_client_document_counts(c.id, db)
    assert out["total_documents"] == 503 and out["listed_documents"] == 500
    assert out["sentiment"] == {"positive": 3, "neutral": 1, "negative": 2, "unscored": 497}
    assert out["topics"] == {"Product": 1, "Legal": 1, "General": 501}


def test_counts_for_a_client_without_documents_and_unknown_client(db):
    c, _, _, _ = _setup(db, 0)
    assert docs_ep.read_client_document_counts(c.id, db) == {
        "total_documents": 0, "listed_documents": 0,
        "sentiment": {"positive": 0, "neutral": 0, "negative": 0, "unscored": 0}, "topics": {}}
    with pytest.raises(HTTPException) as e:
        docs_ep.read_client_document_counts(uuid.uuid4(), db)
    assert e.value.status_code == 404
