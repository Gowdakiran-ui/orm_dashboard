"""Serious-coverage HIGH floor: which real Godrej titles it covers and which it must leave alone."""
import pytest
from app.services.intelligence.risk_floor import serious_floor_applies, HIGH_FLOOR_SCORE, noise_cap_reason, LOW_CAP_SCORE

NAME = "Godrej Properties"


@pytest.fixture(autouse=True)
def _floor_on(monkeypatch):
    monkeypatch.setenv("RISK_FLOOR_ENABLED", "1")


def f(title, doc="rss", sent="Neutral", role=None):
    return serious_floor_applies(title, doc, sent, role, NAME)


@pytest.mark.parametrize("title", [
    "Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India",
    "Godrej Properties denies allegations amid ED probe into fraud, money laundering claims - CNBC TV18",
    "Godrej Properties 'surprised' by CBI FIR over alleged environmental rule violations - Telegraph India",
    "Why NCDRC ordered Godrej Projects to refund Rs 4 crore to homebuyers - Bar & Bench",
    "Court denies Godrej Properties' plea in Rs 227 crore land deal plea - Prop News Time",
    "Godrej Air project: Home buyers protest delayed flats delivery - Hindustan Times",
])
def test_serious_items_get_the_floor(title):
    assert f(title) is True


@pytest.mark.parametrize("title", [
    "Godrej Properties gets RERA approval for Worli residential project - Business Standard",      # approval
    "Godrej Samaris RERA Approved | Luxury Homes",                                                  # marketing
    "Orris, Godrej Properties reach settlement over Gurugram project dispute - ET Realty",          # settled
    "NCLT Mumbai approves merger of subsidiary into Godrej Properties",                             # merger
    "Godrej Properties Alleges Rs 110 Crore Fraud; EOW Registers Case Against Builder",             # Godrej is the complainant
    "MD of infra firm held in forgery case filed by Godrej Properties - The Times of India",        # Godrej is the complainant
    "Bombay High Court Restrains 'Sprouts News' From Publishing Defamatory Articles Against Godrej Properties",
    "Godrej Properties Crisis: RERA Delay Traps 740 Families. - Sprouts News",                      # excluded outlet
    "Emaar Properties faces FIR on MGF's complaint after Gurugram court order",                     # does not name the entity
    "Godrej Properties shares gain post Q1 results - Business Standard",                            # no serious term
])
def test_non_serious_or_excluded_items_do_not(title):
    assert f(title) is False


def test_positive_sentiment_bystander_and_social_are_excluded():
    t = "Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India"
    assert f(t, sent="Positive") is False
    assert f(t, role="BYSTANDER") is False and f(t, role="EXONERATED") is False
    assert f(t, role="SELF") is True
    assert f(t, doc="youtube") is False and f(t, doc="instagram") is False and f(t, doc="reddit") is False
    assert f(t, doc="gdelt") is True and f(t, doc="hn_algolia") is True


def test_floor_is_the_first_score_above_the_medium_high_boundary():
    from app.core.risk_config import RISK_THRESHOLDS
    assert RISK_THRESHOLDS["MEDIUM_TO_HIGH"] < HIGH_FLOOR_SCORE <= RISK_THRESHOLDS["HIGH_TO_CRITICAL"]


# ---- engine integration (SQLite, LLM role check stubbed so no network / paid call) ----
def _engine_scenario(title, doc_type="rss", sentiment="Neutral", brand="Godrej Properties", entity_type="brand"):
    import uuid
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
    from app.core.db import Base
    from app.models.client import Client
    from app.models.entity import Entity, EntityMention
    from app.models.document import Document
    from app.models.sentiment import EntitySentiment, DocumentSentiment

    compiles(PG_UUID, "sqlite")(lambda e, c, **kw: "CHAR(32)")
    compiles(JSONB, "sqlite")(lambda e, c, **kw: "TEXT")
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    cid, eid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db.add(Client(id=cid, name="C"))
    db.add(Entity(id=eid, client_id=cid, name=brand, entity_type=entity_type))
    db.add(Document(id=did, url=f"http://x/{did}", title=title, normalized_content="x", document_type=doc_type))
    db.add(EntityMention(document_id=did, entity_id=eid, mention_count=1))
    db.add(DocumentSentiment(document_id=did, sentiment_label=sentiment, sentiment_score=0.0, confidence_score=0.9, weighted_sentiment_score=0.0))
    db.add(EntitySentiment(document_id=did, entity_id=eid, sentiment_label=sentiment, sentiment_score=0.0, confidence_score=0.9))
    db.commit()
    return db, did


def _score(title, role="SELF", **kw):
    from app.services.intelligence.risk_engine import RiskEngine
    db, did = _engine_scenario(title, **kw)
    eng = RiskEngine()
    eng._llm_classify_role = lambda *a, **k: role
    payloads = eng.calculate_document_risk(db, did, persist=False)
    return payloads[0]


def test_engine_floors_unknown_outlet_legal_story_to_high():
    p = _score("Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India")   # DNA India is not a trusted outlet
    assert p["risk_score"] == HIGH_FLOOR_SCORE and p["risk_level"] == "HIGH"
    assert p["explainability"]["serious_floor_applied"] is True


def test_engine_llm_bystander_still_zeroes_the_floor():
    p = _score("Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India", role="BYSTANDER")
    assert p["risk_score"] == 0.0 and p["explainability"]["serious_floor_applied"] is False


def test_engine_leaves_routine_and_social_and_person_scores_alone():
    assert _score("Godrej Properties gets RERA approval for Worli project - DNA India")["risk_score"] == 0.0
    assert _score("Godrej Properties fined by MahaRERA", doc_type="youtube")["risk_score"] == 0.0
    assert _score("Godrej Properties fined by MahaRERA - DNA India", entity_type="person")["risk_score"] == 0.0


# ---- flag, keyword boundaries, source-name exclusion ----
def test_floor_is_off_unless_the_flag_is_set(monkeypatch):
    t = "Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India"
    monkeypatch.delenv("RISK_FLOOR_ENABLED", raising=False)
    assert f(t) is False
    for off in ("", "0", "false", "no"):
        monkeypatch.setenv("RISK_FLOOR_ENABLED", off)
        assert f(t) is False
    monkeypatch.setenv("RISK_FLOOR_ENABLED", "true")
    assert f(t) is True


@pytest.mark.parametrize("title", [
    "Ed Sheeran to perform at Godrej BKC",                                  # "Ed" the name
    "Godrej Properties launches fine dining and a food court at Godrej One", # "fine", "court" as plain words
    "Godrej Court apartments in Pune - Magicbricks",                         # building name
    "Godrej Properties refund policy for early bird bookings",              # "refund" with no order/direction
    "Godrej Properties hc loan rate",                                        # lowercase hc
    "Godrej Properties firm gets new CEO",                                   # "firm" is not "fir"
    "Godrej Properties will probe new markets in Pune",                      # "probe" as a verb for markets
    "Godrej Properties dispute resolution app launched",                     # bare "dispute"
])
def test_ordinary_uses_of_loose_words_do_not_trigger(title):
    assert f(title) is False


@pytest.mark.parametrize("title", [
    "ED raids Godrej Properties offices - Mint",                              # capital ED
    "FIR against Godrej Properties over land - Mint",
    "Bombay HC pulls up Godrej Properties - Mint",
    "Godrej Properties faces CBI probe - Mint",
    "Godrej Properties ordered to refund buyers Rs 4 crore - Mint",
    "Godrej Properties in land dispute with farmers - Mint",
    "Godrej Properties dragged to court by homebuyers - Mint",
    "Court directs Godrej Properties to pay compensation - Mint",
    "Godrej Properties fined Rs 5 lakh - Mint",
])
def test_serious_wording_with_context_still_triggers(title):
    assert f(title) is True


def test_sprouts_exclusion_reads_the_source_name_too():
    t = "Godrej Properties fined Rs 30 lakh by MahaRERA"
    assert serious_floor_applies(t, "rss", "Neutral", None, NAME, "Google News (history) backfill://x") is True
    assert serious_floor_applies(t, "rss", "Neutral", None, NAME, "Sprouts News https://sproutsnews.com/feed") is False


def test_engine_scores_are_unchanged_when_the_flag_is_off(monkeypatch):
    monkeypatch.delenv("RISK_FLOOR_ENABLED", raising=False)
    p = _score("Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India")
    assert p["risk_score"] == 0.0 and p["explainability"]["serious_floor_applied"] is False


def test_inventiva_and_dismissed_complaints_are_excluded():
    assert f("Godrej Properties Land Dispute: Allegations of Cheating and Breach of Trust - Inventiva") is False
    assert f("Why No Action By ED & CBI On Real Estate Fraud Involving Godrej Properties - inventiva.co.in") is False
    assert serious_floor_applies("Godrej Properties fined Rs 30 lakh by MahaRERA", "rss", "Neutral", None, NAME, "Inventiva https://inventiva.co.in/feed") is False
    assert f("Karnataka RERA Dismisses Real Estate Agent's Complaint Against Godrej Properties - Live Law") is False
    assert f("RERA dismisses Godrej Properties' appeal; orders refund to buyers - Live Law") is True   # Godrej lost


# ---- market-move / results / promotional wording, dropped charges ----
@pytest.mark.parametrize("title,reason", [
    ("Godrej Properties Crashes Nearly 4% On Posting Loss In March Quarter - NDTV Profit", "financial_results"),
    ("Godrej Properties Ltd Falls 2.55%, BSE Realty index Drops 1.81% - Business Standard", "market_move"),
    ("Godrej Properties share price falls 7%: What triggered the sudden sell-off in trade today? - Livemint", "market_move"),
    ("Godrej Properties - Negative Breakout: These 5 stocks cross below their 200 DMAs - The Economic Times", "market_move"),
    ("Top stock picks: Analysts recommend buying Cyient DLM; cautious on PNB, Godrej Properties", "market_move"),
    ("Adani Group stocks rise after US drops fraud charges against Gautam Adani - Reuters", None),     # 'fraud' is serious: handled by the floor exclusion
    ("Godrej Properties Q1 net profit falls 42%; booking value rises 22% - Business Standard", "financial_results"),
    ("Godrej Properties Q1 PAT Slips 46 % QoQ , Revenue Down 85 %", "financial_results"),
    ("Sobha Q2 profit plunges 54.5% to 33 crore even as H1 sales hit record - Business Standard", "financial_results"),
    ("Sobha Shares Fall Over 4% After Q2 Results - NDTV Profit", "financial_results"),
])
def test_market_and_results_titles_are_capped_as_noise(title, reason):
    assert noise_cap_reason(title, "rss") == reason


@pytest.mark.parametrize("title", [
    "Godrej Properties shares fall after SEBI orders probe into disclosures",   # serious term wins
    "Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India",
    "Godrej Properties shares crash 5% as ED raids offices",
    "Bengaluru-based Sobha Limited hit with ransomware attack, company says no impact observed",
    "Godrej Vanantara Apartment Scam: Duplicate NOC",
    "Godrej Properties pulls out of Rs 700 cr deal with DB Realty - Livemint",   # deal wording is NOT capped (decision pending)
])
def test_serious_or_unrelated_titles_are_not_capped(title):
    assert noise_cap_reason(title, "rss") is None


def test_promotional_video_titles_are_capped_only_on_video_and_image_posts():
    t = "Why is SOBHA so Expensive? The Truth About 1456 Quality Checks."
    assert noise_cap_reason(t, "youtube") == "promotional"
    assert noise_cap_reason(t, "instagram") == "promotional"
    assert noise_cap_reason(t, "rss") is None
    assert noise_cap_reason("Sobha Ayana 3BHK Bangalore | Panathur Road Luxury Apartments", "youtube") == "promotional"
    assert noise_cap_reason("Godrej Vanantara Apartment Scam: Duplicate NOC", "youtube") is None      # a real complaint video keeps scoring
    assert noise_cap_reason("Godrej Air project: Home buyers protest delayed flats delivery", "youtube") is None


def test_floor_skips_market_move_results_and_dropped_charges():
    assert f("Adani Properties stocks rise after US drops fraud charges against Gautam Adani - Reuters") is False
    assert serious_floor_applies("Adani Group stocks rise after US drops fraud charges against Gautam Adani - Reuters", "rss", "Neutral", None, "Adani Group") is False
    assert f("Godrej Properties shares jump 3% after court rejects plea - Mint") is False      # share-price headline
    assert f("CBI drops case against Godrej Properties - Mint") is False
    assert f("Godrej Properties Q1 profit falls after RERA penalty - Mint") is False             # results headline


def test_engine_caps_a_results_story_at_low_when_the_flag_is_on_and_leaves_it_when_off(monkeypatch):
    title = "Godrej Properties Q1 net profit falls 42%; booking value rises 22% - Business Standard"
    off = None
    monkeypatch.delenv("RISK_FLOOR_ENABLED", raising=False)
    off = _score(title, sentiment="Negative")
    assert off["risk_score"] > LOW_CAP_SCORE                       # today's behaviour is unchanged while the flag is off
    monkeypatch.setenv("RISK_FLOOR_ENABLED", "1")
    on = _score(title, sentiment="Negative")
    assert on["risk_score"] == LOW_CAP_SCORE and on["risk_level"] == "LOW"
    assert on["explainability"]["noise_cap_applied"] == "financial_results"
    # a serious story is not capped
    fine = _score("Godrej Properties fined Rs 30 lakh by MahaRERA - Business Standard", sentiment="Negative")
    assert fine["risk_score"] > LOW_CAP_SCORE and fine["explainability"]["noise_cap_applied"] is None
