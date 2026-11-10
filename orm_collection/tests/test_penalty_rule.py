"""Small-penalty rule (penalty_rule.py): amount and authority from the headline, the cap decision, and how the risk stage uses it.
No network and no real database: the model call is a stub, the engine runs on in-memory SQLite."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services.intelligence import penalty_rule as pr
from app.services.intelligence.case_status import STATUS_CAP_SCORE
from app.services.intelligence.risk_floor import HIGH_FLOOR_SCORE

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
RECENT = NOW - timedelta(days=60)
OLD = NOW - timedelta(days=800)


# ---- amount ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,lakh", [
    ("Hyderabad: EaseMyTrip, Qatar Airways fined ₹3.06L for denying ticket", 3.06),
    ("Qatar Airways, EaseMyTrip ordered to pay Rs 3.06 lakh after denying refund", 3.06),
    ("Godrej Properties Hit With ₹10 Lakh CGRERA Penalty Over Ad Violation", 10.0),
    ("Godrej Properties faces Rs. 10 lakh RERA penalty over Greenvale Estate ads", 10.0),
    ("MCD slaps Rs 5 lakh penalty on Godrej Properties' arm", 5.0),
    ("Godrej Properties fined Rs 30 lakh by MahaRERA", 30.0),
    ("Godrej Properties' subsidiary receives GST demand and penalty order worth Rs 22.54 crore", 2254.0),
    ("Court denies Godrej Properties' plea in Rs 227 crore land deal plea", 22700.0),
    ("ordered to pay ₹14,261 refund, ₹25,000 compensation and ₹4,000 litigation costs", 0.25),      # the largest: 25,000 rupees
    ("fined INR 1.5 crore by the regulator", 150.0),
    ("a 10 lakh penalty", 10.0),
    ("fine of Rs 2 million", 20.0),
])
def test_largest_rupee_amount_in_lakh(text, lakh):
    assert pr.parse_amount_lakh(text) == pytest.approx(lakh)


@pytest.mark.parametrize("text", [
    "MahaRERA Directs Godrej Properties To Refund Senior Citizen Who Canceled Their Booking",
    "Hamirpur Consumer Commission Directs EaseMyTrip To Compensate Groom",
    "Shares fell 11% on the news",
    "Adani settles for -$157K",                    # a dollar figure is not a rupee amount
    "", None,
])
def test_no_amount_is_none(text):
    assert pr.parse_amount_lakh(text) is None


# ---- authority and criminal wording -----------------------------------------------------------------------------------
@pytest.mark.parametrize("text,kind", [
    ("Hamirpur Consumer Commission Directs EaseMyTrip", "small"),
    ("MahaRERA directs Godrej to refund", "small"),
    ("CGRERA slaps penalty on Godrej", "small"),
    ("MCD slaps penalty on Godrej's arm", "small"),
    ("Bombay High Court upholds RERA penalty", "senior"),                  # a senior authority wins over RERA
    ("SEBI fines Adani", "senior"), ("ED attaches shares", "senior"), ("CBI files case", "senior"),
    ("NCLT orders", "senior"), ("CCI imposes penalty", "senior"), ("Supreme Court dismisses plea", "senior"),
    ("Qatar Airways, EaseMyTrip ordered to pay Rs 3.06 lakh", "unknown"),
    ("The ed led the project", "unknown"),                                  # lower-case 'ed' is not the Enforcement Directorate
])
def test_authority_kind(text, kind):
    assert pr.parse_authority_kind(text) == kind


@pytest.mark.parametrize("text,crim", [
    ("FIR registered against the company over cheating", True), ("ED chargesheet", True), ("money laundering probe", True),
    ("MahaRERA fines Godrej Rs 30 lakh", False), ("Consumer commission orders refund", False),
])
def test_criminal_wording(text, crim):
    assert pr.parse_penalty(text)["criminal"] is crim


# ---- the decision -----------------------------------------------------------------------------------------------------------
def p(amount=None, kind="unknown", criminal=False):
    return {"amount_lakh": amount, "kind": kind, "criminal": criminal, "source": "regex"}


@pytest.mark.parametrize("parse,when,cap", [
    (p(3.06), RECENT, True),                       # under 25 lakh, authority not named
    (p(10, "small"), RECENT, True),                # CGRERA Rs 10 lakh
    (p(5, "small"), RECENT, True),                 # MCD Rs 5 lakh
    (p(24.99, "small"), RECENT, True),
    (p(25, "small"), RECENT, False),               # 25 lakh is NOT under 25 lakh
    (p(30, "small"), OLD, False),                  # Rs 30 lakh MahaRERA 2019: 25 lakh or more keeps today's rules, even when old
    (p(2254), OLD, False),                         # Rs 22.54 crore GST demand, 34 months old: amount decides
    (p(22700), OLD, False),
    (p(None, "small"), RECENT, True),              # a refund or compensation order with no amount
    (p(None, "unknown"), RECENT, False),           # nothing known: today's rules
    (p(None, "unknown"), OLD, True),               # older than 24 months
    (p(None, "small"), OLD, True),
    (p(1, "senior"), RECENT, False),               # High Court / SEBI / ED / CBI / NCLT / CCI keep today's rules
    (p(1, "senior"), OLD, False),
    (p(1, "small", criminal=True), RECENT, False), # any order with criminal charges
    (p(1, "small", criminal=True), OLD, False),
    (p(3.06), None, True),                         # no publication date: only the amount rule applies
    (p(None, "unknown"), None, False),
])
def test_cap_decision(parse, when, cap):
    got, reason = pr.penalty_cap_decision(parse, when, NOW)
    assert got is cap and reason


def test_24_months_boundary():
    assert pr.penalty_cap_decision(p(None), NOW - timedelta(days=729), NOW)[0] is False
    assert pr.penalty_cap_decision(p(None), NOW - timedelta(days=731), NOW)[0] is True


def test_naive_datetimes_are_read_as_utc():
    assert pr.penalty_cap_decision(p(None), datetime(2023, 1, 1), NOW)[0] is True


# ---- the twelve real production items ----------------------------------------------------------------------------------------
CASES = [
    ("Hyderabad: EaseMyTrip, Qatar Airways fined ₹3.06L for denying ticket to patient", "2026-10-08", True),
    ("Qatar Airways, EaseMyTrip ordered to pay Rs 3.06 lakh after denying refund to passenger", "2026-10-13", True),
    ("Godrej Properties Hit With ₹10 Lakh CGRERA Penalty Over Ad Violation", "2026-07-03", True),
    ("Godrej Properties faces Rs. 10 lakh RERA penalty over Greenvale Estate ads", "2026-07-04", True),
    ("CGRERA Slaps ₹10 Lakh Penalty on Godrej Properties Under RERA Act Compliance Norms", "2026-07-04", True),
    ("MCD slaps Rs 5 lakh penalty on Godrej Properties' arm for violating NGT construction norms", "2023-10-22", True),
    ("Godrej Properties' subsidiary receives GST demand and penalty order worth Rs 22.54 crore", "2024-01-02", False),
    ("Court denies Godrej Properties' plea in Rs 227 crore land deal plea", "2023-09-05", False),
    ("Godrej Properties fined Rs 30 lakh by MahaRERA", "2019-09-11", False),
]


@pytest.mark.parametrize("title,day,cap", CASES)
def test_real_headlines(title, day, cap):
    when = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    assert pr.penalty_cap_decision(pr.parse_penalty(title), when, NOW)[0] is cap


# ---- the model (only when no amount is found) -----------------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ('```json\n{"amount_lakh": null, "authority": "consumer_commission", "criminal": false}\n```', (None, "small", False)),
    ('{"amount_lakh": 12.5, "authority": "state_rera", "criminal": false}', (12.5, "small", False)),
    ('{"amount_lakh": 40, "authority": "senior", "criminal": true}', (40.0, "senior", True)),
    ('{"amount_lakh": null, "authority": "other", "criminal": false}', (None, "unknown", False)),
])
def test_model_answer_is_read_with_a_regex(text, expected):
    r = pr.parse_penalty_llm_text(text)
    assert (r["amount_lakh"], r["kind"], r["criminal"]) == expected


@pytest.mark.parametrize("text", [None, "", "no idea", '{"authority": "the moon"}'])
def test_unreadable_model_answer_is_none(text):
    assert pr.parse_penalty_llm_text(text) is None


class _Resp:
    def __init__(self, content, status=200):
        self.status_code, self._c = status, content

    def json(self):
        return {"choices": [{"message": {"content": self._c}}], "usage": {"prompt_tokens": 180, "completion_tokens": 20, "cost": 0.0003}}


def test_model_call_sends_the_headline_only_at_temperature_zero_and_fails_safe():
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return _Resp('{"amount_lakh": null, "authority": "state_rera", "criminal": false}')

    r = pr.classify_penalty_llm("MahaRERA directs Godrej to refund", "k", post=post)
    assert r["kind"] == "small" and r["cost"] == 0.0003
    assert seen["body"]["temperature"] == 0 and seen["body"]["model"] == "anthropic/claude-haiku-4.5"
    assert seen["body"]["messages"][1]["content"] == "Headline: MahaRERA directs Godrej to refund"
    assert pr.classify_penalty_llm("t", None, post=post) is None
    assert pr.classify_penalty_llm("t", "k", post=lambda *a, **k: _Resp("x", status=500)) is None
    assert pr.classify_penalty_llm("t", "k", post=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))) is None


def test_merge_fills_only_what_the_regex_could_not_read():
    rx = {"amount_lakh": None, "kind": "unknown", "criminal": False, "source": "regex"}
    llm = {"amount_lakh": 7.0, "kind": "small", "criminal": False, "source": "llm"}
    m = pr.merge_with_regex(rx, llm)
    assert (m["amount_lakh"], m["kind"], m["source"]) == (7.0, "small", "regex+llm")
    keep = pr.merge_with_regex({"amount_lakh": 3.0, "kind": "small", "criminal": False, "source": "regex"}, {"amount_lakh": 99.0, "kind": "senior", "criminal": False, "source": "llm"})
    assert (keep["amount_lakh"], keep["kind"]) == (3.0, "small")                       # the regex reading is not overwritten
    assert pr.merge_with_regex(rx, None) is rx                                         # a failed call changes nothing
    assert pr.merge_with_regex(rx, {**llm, "criminal": True})["criminal"] is True


# ---- risk stage (SQLite; role check and the model stubbed) --------------------------------------------------------------------
def _run(monkeypatch, title, status="penalty_or_order", published=RECENT, flag=True, prior_expl=None, llm_parse=None):
    from test_risk_floor import _engine_scenario
    from app.services.intelligence import risk_engine as re_mod
    from app.models.document import Document
    from app.models.entity import Entity
    from app.models.risk import RiskEvent

    monkeypatch.setenv("RISK_FLOOR_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-real")
    monkeypatch.setattr("app.utils.llm_call_logging.log_llm_call", lambda **k: None)
    if flag:
        monkeypatch.setenv("CASE_STATUS_ENABLED", "1")
    else:
        monkeypatch.delenv("CASE_STATUS_ENABLED", raising=False)
    db, did = _engine_scenario(title)
    db.query(Document).filter(Document.id == did).update({"published_at": published})
    db.commit()
    if prior_expl is not None:
        ent = db.query(Entity).first()
        db.add(RiskEvent(id=uuid.uuid4(), client_id=ent.client_id, document_id=did, entity_id=ent.id, risk_score=51.0, risk_level="HIGH",
                         confidence_score=0.5, explainability=prior_expl))
        db.commit()
    llm_calls = []
    monkeypatch.setattr(re_mod, "classify_penalty_llm", lambda *a, **k: llm_calls.append(1) or llm_parse)
    eng = re_mod.RiskEngine()
    eng._llm_classify_role = lambda *a, **k: "SELF"
    status_calls = []
    eng._llm_classify_case_status = lambda *a, **k: status_calls.append(1) or {"status": status, "event": "x y z"}
    return eng.calculate_document_risk(db, did, persist=False)[0], llm_calls


def test_small_consumer_order_is_held_at_medium(monkeypatch):
    pay, llm = _run(monkeypatch, "Godrej Properties fined Rs 3.06 lakh by consumer commission - X", published=RECENT)
    assert pay["risk_score"] == STATUS_CAP_SCORE and pay["risk_level"] == "MEDIUM"
    e = pay["explainability"]
    assert e["penalty_cap_applied"] is True and e["serious_floor_applied"] is False
    assert e["penalty_parse"]["amount_lakh"] == pytest.approx(3.06) and e["penalty_parse"]["source"] == "regex"
    assert "Held at Medium" in e["decision_reason"] and "under 25 lakh" in e["decision_reason"]
    assert llm == []                                                                    # an amount was found: no model call


def test_amount_of_25_lakh_or_more_keeps_high(monkeypatch):
    pay, llm = _run(monkeypatch, "Godrej Properties fined Rs 30 lakh by MahaRERA - DNA India", published=OLD)
    assert pay["risk_score"] == HIGH_FLOOR_SCORE and pay["explainability"]["penalty_cap_applied"] is False and llm == []


def test_senior_authority_and_criminal_orders_keep_high(monkeypatch):
    assert _run(monkeypatch, "Delhi High Court fined Godrej Properties Rs 5 lakh - X")[0]["risk_score"] == HIGH_FLOOR_SCORE
    assert _run(monkeypatch, "SEBI fined Godrej Properties Rs 2 lakh - X")[0]["risk_score"] == HIGH_FLOOR_SCORE
    assert _run(monkeypatch, "Godrej Properties fined Rs 5 lakh in cheating FIR case - X")[0]["risk_score"] == HIGH_FLOOR_SCORE


def test_old_penalty_is_held_even_without_an_amount(monkeypatch):
    pay, _ = _run(monkeypatch, "Godrej Properties fined by the authority - X", published=OLD)
    assert pay["risk_score"] == STATUS_CAP_SCORE and "older than 24 months" in pay["explainability"]["penalty_cap_reason"]


def test_model_is_called_only_when_no_amount_is_found_and_its_reading_is_used(monkeypatch):
    llm_parse = {"amount_lakh": None, "kind": "small", "criminal": False, "source": "llm", "prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0003, "latency_ms": 5.0}
    pay, llm = _run(monkeypatch, "MahaRERA fines Godrej Properties over refund to buyer - X", published=RECENT, llm_parse=llm_parse)
    assert llm == [1]
    assert pay["risk_score"] == STATUS_CAP_SCORE and pay["explainability"]["penalty_parse"]["source"] == "regex+llm"
    assert set(pay["explainability"]["penalty_parse"]) == {"amount_lakh", "kind", "criminal", "restricts", "source"}     # no token or cost fields stored


def test_failed_model_call_leaves_a_headline_with_nothing_recognised_at_high(monkeypatch):
    pay, llm = _run(monkeypatch, "Godrej Properties fined by the authority - X", published=RECENT, llm_parse=None)
    assert llm == [1] and pay["risk_score"] == HIGH_FLOOR_SCORE and pay["explainability"]["penalty_cap_applied"] is False


def test_probe_charged_and_allegation_items_are_never_touched(monkeypatch):
    for status in ("probe", "charged", "allegation"):
        pay, llm = _run(monkeypatch, "Godrej Properties fined Rs 3 lakh by consumer commission - X", status=status, published=OLD)
        assert pay["risk_score"] == HIGH_FLOOR_SCORE and "penalty_parse" not in pay["explainability"] and llm == []


def test_nothing_changes_when_the_flag_is_off(monkeypatch):
    pay, llm = _run(monkeypatch, "Godrej Properties fined Rs 3.06 lakh by consumer commission - X", flag=False)
    assert pay["risk_score"] == HIGH_FLOOR_SCORE and "penalty_parse" not in pay["explainability"] and llm == []


def test_cached_parse_is_reused_without_a_model_call(monkeypatch):
    prior = {"case_status": "penalty_or_order", "case_event": "x y z", "case_status_source": "llm", "role_classification": "SELF",
             "role_classification_source": "llm", "penalty_parse": {"amount_lakh": 4.0, "kind": "small", "criminal": False, "source": "regex+llm"}}
    pay, llm = _run(monkeypatch, "Godrej Properties fined by the authority - X", published=RECENT, prior_expl=prior)
    assert llm == [] and pay["risk_score"] == STATUS_CAP_SCORE
    assert pay["explainability"]["penalty_parse"]["source"] == "regex+llm"


# ---- orders that revoke a registration, ban sales or stop a project (never capped, with or without an amount) ----------------------
@pytest.mark.parametrize("text,restricts", [
    ("MahaRERA revokes registration of Godrej Properties project in Pune", True),
    ("RERA cancels Godrej Properties' project registration over delays", True),
    ("Godrej Properties' licence suspended by the municipal body", True),
    ("registration of the Godrej project has been revoked", True),
    ("Authority bans Godrej Properties from selling flats in the project", True),
    ("RERA bars Godrej Properties from booking units until the project is registered", True),
    ("Godrej Properties barred from advertising its Thane project", True),
    ("Stop-work order issued to Godrej Properties site in Gurugram", True),
    ("Authority halts construction of Godrej Properties tower", True),
    ("civic body stops work on Godrej Properties project", True),
    ("NGT stalls Godrej Properties project over clearances", True),
    ("Godrej Properties fined Rs 10 lakh by CGRERA over ad violation", False),
    ("MahaRERA directs Godrej Properties to refund booking amount to buyer", False),
    ("Godrej Properties launches registration for new Pune project", False),            # "registration" alone is not an order
    ("Godrej Properties bank account frozen? No, company says rumour is false", False),   # no project / construction named
    ("Cancel culture hits ad campaign; Godrej Properties unharmed", False),
    ("Consumer commission orders EaseMyTrip to refund cancelled flight ticket", False),   # a cancelled ticket is not a revoked registration
    ("MCD slaps Rs 5 lakh penalty on Godrej Properties' arm", False),
])
def test_restricting_wording(text, restricts):
    assert pr.parse_penalty(text)["restricts"] is restricts


def test_restricting_order_is_never_capped_even_without_an_amount_or_with_a_small_one():
    keep = lambda **kw: pr.penalty_cap_decision({"amount_lakh": None, "kind": "unknown", "criminal": False, "restricts": True, "source": "regex", **kw}, RECENT, NOW)
    for kw in ({"kind": "small"}, {"kind": "unknown"}, {"amount_lakh": 3.0, "kind": "small"}, {"amount_lakh": 3.06}):
        got, reason = keep(**kw)
        assert got is False and "revokes a registration, bans sales or stops a project" in reason
    # not even when the story is older than 24 months
    assert pr.penalty_cap_decision({"amount_lakh": 3.0, "kind": "small", "criminal": False, "restricts": True}, OLD, NOW)[0] is False
    # the same readings without the restricting wording are still capped
    assert pr.penalty_cap_decision({"amount_lakh": None, "kind": "small", "criminal": False, "restricts": False}, RECENT, NOW)[0] is True
    assert pr.penalty_cap_decision({"amount_lakh": 3.0, "kind": "small", "criminal": False, "restricts": False}, RECENT, NOW)[0] is True
    # a reading without the key (cached earlier) behaves as before
    assert pr.penalty_cap_decision({"amount_lakh": 3.0, "kind": "small", "criminal": False}, RECENT, NOW)[0] is True


def test_model_reads_the_restricting_question_and_either_reading_keeps_the_order():
    r = pr.parse_penalty_llm_text('{"amount_lakh": null, "authority": "state_rera", "criminal": false, "restricts": true}')
    assert r["restricts"] is True
    assert pr.parse_penalty_llm_text('{"amount_lakh": 2, "authority": "state_rera", "criminal": false}')["restricts"] is False   # absent = false
    rx = {"amount_lakh": None, "kind": "small", "criminal": False, "restricts": False, "source": "regex"}
    assert pr.merge_with_regex(rx, r)["restricts"] is True
    assert pr.merge_with_regex({**rx, "restricts": True}, {**r, "restricts": False})["restricts"] is True
    assert "restricts" in pr._LLM_SYSTEM


def test_an_old_cached_reading_gets_the_regex_answer_for_the_new_question():
    old = {"amount_lakh": 4.0, "kind": "small", "criminal": False, "source": "regex"}
    assert pr.with_restricts(old, "RERA revokes registration of Godrej project")["restricts"] is True
    assert pr.with_restricts(old, "Godrej fined Rs 4 lakh by RERA")["restricts"] is False
    assert "restricts" not in old                                                      # the cached dict itself is not changed
    new = {**old, "restricts": False}
    assert pr.with_restricts(new, "RERA revokes registration of Godrej project") is new   # a reading that has the key is kept as it is


def test_engine_keeps_a_registration_revocation_at_high_with_no_amount_and_a_small_authority(monkeypatch):
    llm_parse = {"amount_lakh": None, "kind": "small", "criminal": False, "restricts": False, "source": "llm", "prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0003, "latency_ms": 5.0}
    pay, llm = _run(monkeypatch, "MahaRERA revokes registration of Godrej Properties project - X", published=RECENT, llm_parse=llm_parse)
    assert pay["risk_score"] == HIGH_FLOOR_SCORE and pay["explainability"]["penalty_cap_applied"] is False
    assert pay["explainability"]["penalty_parse"]["restricts"] is True
    # the same authority and no amount, but a plain refund order: still capped
    pay2, _ = _run(monkeypatch, "MahaRERA directs Godrej Properties to refund booking amount - X", published=RECENT, llm_parse=llm_parse)
    assert pay2["risk_score"] == STATUS_CAP_SCORE and pay2["explainability"]["penalty_parse"]["restricts"] is False


def test_engine_keeps_a_small_fine_that_comes_with_a_stop_work_order(monkeypatch):
    pay, llm = _run(monkeypatch, "Godrej Properties fined Rs 5 lakh and told to stop work on Gurugram project - X", published=RECENT)
    assert llm == [] and pay["risk_score"] == HIGH_FLOOR_SCORE and pay["explainability"]["penalty_parse"]["restricts"] is True


def test_engine_adds_the_new_question_to_a_reading_cached_before_it_existed(monkeypatch):
    prior = {"case_status": "penalty_or_order", "case_event": "x y z", "case_status_source": "llm", "role_classification": "SELF",
             "role_classification_source": "llm", "penalty_parse": {"amount_lakh": 4.0, "kind": "small", "criminal": False, "source": "regex+llm"}}
    pay, llm = _run(monkeypatch, "RERA cancels Godrej Properties project registration - X", published=RECENT, prior_expl=prior)
    assert llm == [] and pay["risk_score"] == HIGH_FLOOR_SCORE and pay["explainability"]["penalty_parse"]["restricts"] is True
