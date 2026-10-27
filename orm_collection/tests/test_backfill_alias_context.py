"""Backfill relevance: an item that matches only the bare stripped-name alias ("Sobha" for "Sobha Limited") needs a
context term; YouTube is stricter. Backfill filter only: the live matcher and keyword generation are untouched."""
import json
import os
import sys
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityAlias, EntityKeyword
from app.services.backfill.relevance import is_relevant, relevance_rules, RelevanceRules


@compiles(PG_UUID, 'sqlite')
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, 'sqlite')
def _jsonb(element, compiler, **kw):
    return "TEXT"


def Session():
    """A fresh in-memory database per call: client names are unique and the per-client config is keyed by name."""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()

SOBHA_CFG = {"Sobha Limited": {"exclude": ["dubai", "uae", "abu dhabi", "sobha realty", "hartland", "sobha sanctuary"]}}


def _sobha(db, name="Sobha Limited", extra_entities=()):
    c = Client(id=uuid.uuid4(), name=name)
    db.add(c)
    db.flush()
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name=name, entity_type="brand")
    db.add(brand)
    for n, t in extra_entities:
        db.add(Entity(id=uuid.uuid4(), client_id=c.id, name=n, entity_type=t))
    db.flush()
    for kw in (name, name.lower(), name.replace(" ", ""), "Sobha"):
        db.add(EntityKeyword(entity_id=brand.id, keyword_text=kw, category="PRIMARY" if kw == name else "ALIAS"))
    db.commit()
    return c


def test_bare_alias_is_split_from_full_names():
    db = Session()
    r = relevance_rules(db, _sobha(db).id)
    assert [t.strip() for t in r.bare] == ["sobha"]
    assert "sobha limited" in [t.strip() for t in r.full] and "sobhalimited" in [t.strip() for t in r.full]


def test_google_news_bare_alias_needs_a_context_term_but_the_full_name_does_not():
    db = Session()
    r = relevance_rules(db, _sobha(db).id)
    assert is_relevant("Sobha Limited Q2 profit plunges", "", r, "google_news")                         # full legal name
    assert is_relevant("Sobha launches the tallest residential building in GIFT City", "", r, "google_news") is False   # no context term
    assert is_relevant("Sobha shares fall 4% after Q2 results - NDTV Profit", "", r, "google_news")      # listed-company wording is context
    assert is_relevant("Sobha villas open for booking", "", r, "google_news") is False
    assert is_relevant("Sobha faces Rs 29.75 crore tax demand", "", r, "google_news")                    # 'crore'
    assert is_relevant("Sobha Royal Crest, Banashankari Bangalore", "", r, "google_news")               # city
    assert is_relevant("Sobha Realty names Ravi Menon chairman", "Dubai developer", r, "google_news") is False
    assert is_relevant("Sobha Ltd on a strong footing", "", r, "google_news")                            # 'ltd'


def test_youtube_is_stricter_context_must_be_in_the_title_and_exclude_terms_reject(monkeypatch):
    monkeypatch.setenv("BACKFILL_ALIAS_CONTEXT_JSON", json.dumps(SOBHA_CFG))
    db = Session()
    r = relevance_rules(db, _sobha(db).id)
    assert is_relevant("Sobha Ayana 3BHK Bangalore | Panathur Road", "", r, "youtube")
    assert is_relevant("Sobha interview", "works at Sobha in Bangalore", r, "youtube") is False        # context only in the description
    assert is_relevant("Sobha Central Dubai Fly Through", "", r, "youtube") is False                   # no context, Dubai
    assert is_relevant("Sobha Hartland Dubai villas in India", "", r, "youtube") is False              # exclude term beats a stray 'india'
    assert is_relevant("Sobha Limited Bangalore results", "", r, "youtube")                             # full name always passes
    assert is_relevant("Sobha Hartland launch", "", r, "google_news") is False                          # news: exclude applies without context


def test_context_and_exclude_terms_are_configurable_per_client(monkeypatch):
    monkeypatch.setenv("BACKFILL_ALIAS_CONTEXT_JSON", json.dumps({"sobha limited": {"context": ["palm jumeirah"], "exclude": []}}))
    db = Session()
    r_client = _sobha(db)
    r = relevance_rules(db, r_client.id)
    assert is_relevant("Sobha villas on Palm Jumeirah", "", r, "google_news")        # replaced list
    assert is_relevant("Sobha Bangalore", "", r, "google_news") is False
    monkeypatch.setenv("BACKFILL_ALIAS_CONTEXT_JSON", "{not json")
    assert is_relevant("Sobha Bangalore", "", relevance_rules(db, r_client.id), "google_news")       # bad value -> defaults


def test_a_client_with_no_stripped_alias_behaves_exactly_as_before():
    db = Session()
    c = Client(id=uuid.uuid4(), name="Godrej Properties")
    db.add(c)
    db.flush()
    b = Entity(id=uuid.uuid4(), client_id=c.id, name="Godrej Properties", entity_type="brand")
    db.add(b)
    db.add(Entity(id=uuid.uuid4(), client_id=c.id, name="Pirojsha Godrej", entity_type="person"))
    db.flush()
    db.add(EntityKeyword(entity_id=b.id, keyword_text="Godrej Properties", category="PRIMARY"))
    db.commit()
    r = relevance_rules(db, c.id)
    assert r.bare == []
    assert is_relevant("Godrej Properties launches", "", r, "youtube")
    assert is_relevant("Pirojsha Godrej steps up", "", r, "google_news")
    assert is_relevant("Tata Sons board row", "", r, "google_news") is False


def test_legacy_list_terms_still_work_and_rules_are_truthy_only_with_terms():
    assert is_relevant("Acme Corp results", "", [" acme corp "])
    assert not RelevanceRules([], [], [], [])
    assert RelevanceRules([" a "], [], [], [])
