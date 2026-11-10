"""User-generated / video allegations under 100,000 views that are not from a news outlet are held at Medium (ugc_cap.py). No network and no real
database: the model calls are stubs and the engine runs on in-memory SQLite."""
import pytest

from app.services.intelligence import ugc_cap
from app.services.intelligence.case_status import STATUS_CAP_SCORE
from app.services.intelligence.risk_floor import HIGH_FLOOR_SCORE


# ---- the decision ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("doc_type,views,author,status,cap", [
    ("youtube", 16337, "Freedom TV Kannada", "allegation", True),         # the Godrej "Vanantara scam" video
    ("youtube", 99999, "Some Channel", "allegation", True),
    ("youtube", 100000, "Some Channel", "allegation", False),             # 100,000 is not under 100,000
    ("youtube", 114663, "Live Hindi Facts", "allegation", False),
    ("youtube", None, "Some Channel", "allegation", True),                # no view count shown: reach not proven
    ("youtube", 0, "Some Channel", "allegation", True),
    ("instagram", 500, "someone", "allegation", True),
    ("reddit", None, "u/someone", "allegation", True),
    ("hn_algolia", None, "toomuchtodo", "allegation", True),
    ("youtube", 5000, "Zee Business", "allegation", False),               # a news outlet keeps today's score
    ("youtube", 5000, "NDTV Profit", "allegation", False),
    ("youtube", 5000, "CNBC-TV18", "allegation", False),
    ("youtube", 5000, "Bloomberg Markets and Finance", "allegation", False),
    ("rss", 10, "Reporter", "allegation", False),                         # press is never touched
    ("gdelt", None, None, "allegation", False),
    ("youtube", 100, "Some Channel", "probe", False),                     # only allegations
    ("youtube", 100, "Some Channel", "charged", False),
    ("youtube", 100, "Some Channel", "penalty_or_order", False),
    ("youtube", 100, "Some Channel", None, False),
    ("YouTube", 100, "Some Channel", "allegation", True),                 # type compare ignores case
    (None, 100, "Some Channel", "allegation", False),
])
def test_ugc_cap_decision(doc_type, views, author, status, cap):
    got, reason = ugc_cap.ugc_cap_decision(doc_type, views, author, status)
    assert got is cap and reason


def test_the_reason_says_what_was_seen():
    assert ugc_cap.ugc_cap_decision("youtube", 16337, "Freedom TV Kannada", "allegation")[1] == \
        "an allegation from a user-generated or video source (16,337 views, under 100,000) that is not a news outlet"
    assert "no view count shown" in ugc_cap.ugc_cap_decision("hn_algolia", None, "x", "allegation")[1]


@pytest.mark.parametrize("name,expected", [
    ("Zee Business", True), ("ZEE BUSINESS", True), ("NDTV Profit", True), ("CNBC-TV18", True), ("India Today Live", True),
    ("The Hindu", True), ("Reuters", True), ("Bloomberg Television", True),
    ("Freedom TV Kannada", False), ("Live Hindi Facts", False), ("Sahil Khanna", False), ("Sarthak Bazar Se", False),
    ("Minty fresh news lovers", False),              # whole words only, not a substring
    ("", False), (None, False),
])
def test_news_outlet_names(name, expected):
    assert ugc_cap.is_news_outlet(name) is expected


# ---- in the risk stage ---------------------------------------------------------------------------------------------------------------------
TITLE = "Godrej Properties accused of fraud in Vanantara apartment scam"


def _run(monkeypatch, doc_type="hn_algolia", views=None, author="someone", status="allegation", flag=True, title=TITLE):
    from test_risk_floor import _engine_scenario
    from app.services.intelligence import risk_engine as re_mod
    from app.models.document import Document

    monkeypatch.setenv("RISK_FLOOR_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-real")
    monkeypatch.setattr("app.utils.llm_call_logging.log_llm_call", lambda **k: None)
    if flag:
        monkeypatch.setenv("CASE_STATUS_ENABLED", "1")
    else:
        monkeypatch.delenv("CASE_STATUS_ENABLED", raising=False)
    db, did = _engine_scenario(title, doc_type=doc_type)
    db.query(Document).filter(Document.id == did).update({"view_count": views, "author": author})
    db.commit()
    eng = re_mod.RiskEngine()
    eng._llm_classify_role = lambda *a, **k: "SELF"
    eng._llm_classify_case_status = lambda *a, **k: {"status": status, "event": "x y z"}
    return eng.calculate_document_risk(db, did, persist=False)[0]


def test_low_reach_user_generated_allegation_is_held_at_medium(monkeypatch):
    base = _run(monkeypatch, flag=False)
    assert base["risk_score"] == HIGH_FLOOR_SCORE and "ugc_cap_applied" not in base["explainability"]       # today's score, flag off
    p = _run(monkeypatch)
    ex = p["explainability"]
    assert p["risk_score"] == STATUS_CAP_SCORE and p["risk_level"] == "MEDIUM"
    assert ex["ugc_cap_applied"] is True and "no view count shown" in ex["ugc_cap_reason"] and ex["serious_floor_applied"] is False
    assert "Held at Medium: an allegation from a user-generated or video source" in ex["decision_reason"]


def test_reach_or_a_news_outlet_or_another_status_or_press_keeps_the_score(monkeypatch):
    for kw in ({"views": 150000}, {"author": "NDTV Profit"}, {"status": "probe"}, {"status": "charged"}, {"doc_type": "rss", "author": "Reporter"}):
        p = _run(monkeypatch, **kw)
        assert p["risk_score"] == HIGH_FLOOR_SCORE and p["explainability"].get("ugc_cap_applied", False) is False, kw
    # an allegation that reaches 100,000 or more records why it was not held
    ex = _run(monkeypatch, views=150000)["explainability"]
    assert ex["ugc_cap_applied"] is False and ex["ugc_cap_reason"] == "100,000 views or more"
    assert "ugc_cap_applied" not in _run(monkeypatch, status="probe")["explainability"]


def test_nothing_changes_when_the_case_status_flag_is_off(monkeypatch):
    p = _run(monkeypatch, flag=False)
    assert p["risk_score"] == HIGH_FLOOR_SCORE and "ugc_cap_applied" not in p["explainability"] and "case_status" not in p["explainability"]
