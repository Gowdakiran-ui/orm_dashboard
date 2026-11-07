"""Case-status label (case_status.py) and how the risk stage uses it. No network and no database beyond SQLite:
the LLM call is replaced by a stub, so nothing here reaches OpenRouter or the production database."""
import uuid

import pytest

from app.services.intelligence import case_status as cs
from app.services.intelligence.risk_floor import HIGH_FLOOR_SCORE
from app.core.risk_config import RISK_THRESHOLDS

TITLE = "Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India"   # floor lifts it to HIGH (51); DNA India is not trusted


# ---- parsing: a regex, not strict JSON -------------------------------------------------------------------------
@pytest.mark.parametrize("text,status,event", [
    ('```json\n{"status": "charged", "event": "ed chargesheet nishant pitti mahadev"}\n```', "charged", "ed chargesheet nishant pitti mahadev"),
    ('{"status":"settled","event":"Sebi Settles Adani"}', "settled", "sebi settles adani"),
    ('{"status": "dismissed_or_closed"}', "dismissed_or_closed", None),
    ('status: probe', "probe", None),
    ('Here you go: {"status": "penalty_or_order", "event": "mcd penalty godrej"} hope that helps', "penalty_or_order", "mcd penalty godrej"),
    ('{"status": "unrelated", "event": ""}', "unrelated", None),
])
def test_parse_accepts_fenced_and_loose_answers(text, status, event):
    assert cs.parse_case_status(text) == (status, event)


@pytest.mark.parametrize("text", [None, "", "no idea", '{"status": "guilty"}', '{"label": "SELF"}', '{"status": "Allegation Probe"}'])
def test_parse_rejects_anything_that_is_not_one_of_the_seven_labels(text):
    assert cs.parse_case_status(text)[0] is None


def test_the_seven_labels_are_exactly_the_requested_set():
    assert set(cs.STATUSES) == {"allegation", "probe", "charged", "penalty_or_order", "settled", "dismissed_or_closed", "unrelated"}
    assert set(cs.STATUS_LABELS) == set(cs.STATUSES)


# ---- severity rule ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["unrelated", "dismissed_or_closed", "settled"])
@pytest.mark.parametrize("score", [51.0, 75.0, 88.0, 100.0])
def test_capped_statuses_never_reach_high(status, score):
    out, capped = cs.apply_status_cap(score, status)
    assert capped is True and out == RISK_THRESHOLDS["MEDIUM_TO_HIGH"]      # exactly 50 is still MEDIUM


@pytest.mark.parametrize("status", ["allegation", "probe", "charged", "penalty_or_order", None])
@pytest.mark.parametrize("score", [0.0, 30.0, 51.0, 89.0])
def test_other_statuses_and_missing_labels_keep_today_s_score(status, score):
    assert cs.apply_status_cap(score, status) == (score, False)


@pytest.mark.parametrize("status", sorted(cs.CAPPED_STATUSES))
def test_a_score_at_or_below_the_boundary_is_never_raised_or_flagged(status):
    assert cs.apply_status_cap(50.0, status) == (50.0, False)
    assert cs.apply_status_cap(12.0, status) == (12.0, False)


# ---- cache -------------------------------------------------------------------------------------------------------
def test_cached_label_is_reused_only_from_an_llm_source():
    assert cs.cached_case_status({"case_status": "probe", "case_event": "cbi fir", "case_status_source": "llm"}) == {"status": "probe", "event": "cbi fir"}
    assert cs.cached_case_status({"case_status": "probe"}) is None
    assert cs.cached_case_status({"case_status": "bogus", "case_status_source": "llm"}) is None
    assert cs.cached_case_status(None) is None


# ---- the call ------------------------------------------------------------------------------------------------------
class _Resp:
    def __init__(self, content=None, status=200, usage=None):
        self.status_code = status
        self._c, self._u = content, usage or {"prompt_tokens": 260, "completion_tokens": 25, "cost": 0.0004}

    def json(self):
        return {"choices": [{"message": {"content": self._c}}], "usage": self._u}


def test_classify_sends_headline_only_at_temperature_zero_and_returns_label_and_cost():
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, body=json)
        return _Resp('```json\n{"status": "probe", "event": "ed raids easemytrip"}\n```')

    r = cs.classify_case_status("ED raids EaseMyTrip - Mint", "EaseMyTrip", "key", post=post)
    assert r["status"] == "probe" and r["event"] == "ed raids easemytrip" and r["cost"] == 0.0004
    assert seen["body"]["model"] == "anthropic/claude-haiku-4.5" and seen["body"]["temperature"] == 0
    assert seen["url"].startswith("https://openrouter.ai/")
    user = seen["body"]["messages"][1]["content"]
    assert "ED raids EaseMyTrip - Mint" in user and "Company: EaseMyTrip" in user


def test_classify_returns_none_on_every_failure():
    def boom(*a, **k):
        raise RuntimeError("down")

    assert cs.classify_case_status("t", "E", None, post=boom) is None                                   # no key
    assert cs.classify_case_status("", "E", "k", post=boom) is None                                     # no headline
    assert cs.classify_case_status("t", "E", "k", post=boom) is None                                    # network error
    assert cs.classify_case_status("t", "E", "k", post=lambda *a, **k: _Resp(status=500)) is None       # HTTP error
    assert cs.classify_case_status("t", "E", "k", post=lambda *a, **k: _Resp(content=None)) is None     # null content
    assert cs.classify_case_status("t", "E", "k", post=lambda *a, **k: _Resp(content="maybe")) is None  # unparsable


def test_flag_is_off_unless_set(monkeypatch):
    monkeypatch.delenv("CASE_STATUS_ENABLED", raising=False)
    assert cs.case_status_enabled() is False
    for off in ("0", "", "no", "false"):
        monkeypatch.setenv("CASE_STATUS_ENABLED", off)
        assert cs.case_status_enabled() is False
    for on in ("1", "true", "YES", "on"):
        monkeypatch.setenv("CASE_STATUS_ENABLED", on)
        assert cs.case_status_enabled() is True


# ---- risk stage (SQLite; role check and status call stubbed) ----------------------------------------------------------
def _run(monkeypatch, result, *, role="SELF", flag=True, title=TITLE, prior_expl=None):
    from test_risk_floor import _engine_scenario
    from app.services.intelligence.risk_engine import RiskEngine
    from app.models.risk import RiskEvent
    from app.models.entity import Entity

    monkeypatch.setenv("RISK_FLOOR_ENABLED", "1")
    if flag:
        monkeypatch.setenv("CASE_STATUS_ENABLED", "1")
    else:
        monkeypatch.delenv("CASE_STATUS_ENABLED", raising=False)
    db, did = _engine_scenario(title)
    if prior_expl is not None:
        ent = db.query(Entity).first()
        db.add(RiskEvent(id=uuid.uuid4(), client_id=ent.client_id, document_id=did, entity_id=ent.id, risk_score=51.0,
                         risk_level="HIGH", confidence_score=0.5, explainability=prior_expl))
        db.commit()
    calls = []
    eng = RiskEngine()
    eng._llm_classify_role = lambda *a, **k: role
    eng._llm_classify_case_status = lambda *a, **k: calls.append(1) or result
    return eng.calculate_document_risk(db, did, persist=False)[0], calls


@pytest.mark.parametrize("status", ["settled", "dismissed_or_closed", "unrelated"])
def test_engine_holds_settled_dismissed_and_unrelated_at_medium(monkeypatch, status):
    p, calls = _run(monkeypatch, {"status": status, "event": "x y z"})
    assert calls == [1]
    assert p["risk_score"] == 50.0 and p["risk_level"] == "MEDIUM"
    e = p["explainability"]
    assert e["case_status"] == status and e["case_event"] == "x y z" and e["case_status_source"] == "llm"
    assert e["case_status_cap_applied"] is True and e["serious_floor_applied"] is False
    assert "Held at Medium" in e["decision_reason"]


@pytest.mark.parametrize("status", ["allegation", "probe", "charged", "penalty_or_order"])
def test_engine_keeps_todays_score_for_the_other_four(monkeypatch, status):
    p, _ = _run(monkeypatch, {"status": status, "event": "x"})
    assert p["risk_score"] == HIGH_FLOOR_SCORE and p["risk_level"] == "HIGH"
    assert p["explainability"]["case_status"] == status and p["explainability"]["case_status_cap_applied"] is False
    assert p["explainability"]["serious_floor_applied"] is True


def test_engine_makes_no_call_and_changes_nothing_when_the_flag_is_off(monkeypatch):
    p, calls = _run(monkeypatch, {"status": "settled", "event": "x"}, flag=False)
    assert calls == [] and p["risk_score"] == HIGH_FLOOR_SCORE
    assert "case_status" not in p["explainability"]


def test_a_failed_label_leaves_the_score_unchanged_and_writes_no_status_keys(monkeypatch):
    p, calls = _run(monkeypatch, None)
    assert calls == [1] and p["risk_score"] == HIGH_FLOOR_SCORE
    assert "case_status" not in p["explainability"]          # so a later successful run is not blocked, and nothing stale is merged


def test_role_gate_zero_means_no_status_call(monkeypatch):
    p, calls = _run(monkeypatch, {"status": "charged", "event": "x"}, role="BYSTANDER")
    assert calls == [] and p["risk_score"] == 0.0


def test_a_low_scoring_item_makes_no_status_call(monkeypatch):
    p, calls = _run(monkeypatch, {"status": "charged", "event": "x"}, title="Godrej Properties launches new tower in Pune - DNA India")
    assert calls == [] and p["risk_score"] == 0.0


def test_cached_label_is_reused_without_a_call(monkeypatch):
    prior = {"case_status": "settled", "case_event": "godrej fined", "case_status_source": "llm", "role_classification": "SELF",
             "role_classification_source": "llm"}
    p, calls = _run(monkeypatch, {"status": "charged", "event": "different"}, prior_expl=prior)
    assert calls == []
    e = p["explainability"]
    assert e["case_status"] == "settled" and e["case_status_cache_hit"] is True and p["risk_score"] == 50.0


def test_decision_reason_is_unchanged_when_nothing_was_capped(monkeypatch):
    p, _ = _run(monkeypatch, {"status": "probe", "event": "x"})
    assert "Held at Medium" not in p["explainability"]["decision_reason"]
