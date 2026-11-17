"""scripts/new_client_acceptance.py: the PASS / WARN / FAIL tiers, checked on plain dicts (no database, no Redis)."""
import datetime as dt
import importlib.util
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "new_client_acceptance.py"


def _load():
    if not SCRIPT.exists():
        pytest.skip("scripts/ not available (tests run outside the repo checkout)")
    spec = importlib.util.spec_from_file_location("new_client_acceptance", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NOW = dt.datetime(2026, 11, 17, 10, 0, tzinfo=dt.timezone.utc)


def _good(**over):
    f = {"default_queue_len": 0, "seeded_rows": 12, "backfill_slices": 400, "pending_slices": 0, "documents": 500,
         "documents_by_source": "rss=400", "risk_events": 300, "risk_by_level": "LOW=300", "active_feeds": 24,
         "reputation_rows": 1, "active_executives": 5, "active_competitors": 5, "rows_executives": 6, "rows_competitors": 5,
         "review_executives": 1, "review_competitors": 0, "active_rows_incomplete": 0, "latest_run_status": "SUCCESS",
         "latest_run_finished": NOW, "reputation_created": NOW, "reputation_text": "72.7 grade B", "reputation_docs": 500,
         "executive_scored": 5, "grants": 0, "super_admins": 3, "token": None}
    f.update(over)
    return f


def _statuses(mod, **over):
    res = mod.evaluate(_good(**over))
    return res, mod.result_of(res)


def test_a_fully_set_up_client_passes_with_no_warning():
    mod = _load()
    res, (verdict, nfail, nwarn) = _statuses(mod)
    assert (verdict, nfail, nwarn) == ("PASS", 0, 0), res


def test_fewer_than_five_executives_or_competitors_is_a_warn_with_the_reason_not_a_fail():
    mod = _load()
    res, (verdict, nfail, nwarn) = _statuses(mod, active_competitors=2, rows_competitors=2, review_competitors=0)
    assert verdict == "PASS" and nfail == 0 and nwarn == 1
    warn = [r for r in res if r[0] == "WARN"][0]
    assert "competitors: 5 wanted, 2 active" in warn[1] and "held for review" in warn[2]
    _, (v2, f2, w2) = _statuses(mod, active_executives=4)
    assert (v2, f2, w2) == ("PASS", 0, 1)


def test_setup_that_never_ran_fails():
    mod = _load()
    res, (verdict, nfail, _) = _statuses(mod, seeded_rows=0, backfill_slices=0, active_executives=0, active_competitors=0)
    assert verdict == "FAIL" and nfail >= 1
    assert any(r[0] == "FAIL" and r[1].startswith("setup ran") for r in res)


def test_a_stale_message_in_the_default_queue_fails():
    mod = _load()
    res, (verdict, nfail, _) = _statuses(mod, default_queue_len=1)
    assert verdict == "FAIL" and nfail == 1
    assert any(r[0] == "FAIL" and "stale message" in r[1] for r in res)


@pytest.mark.parametrize("field", ["documents", "risk_events", "active_feeds", "reputation_rows", "active_executives", "active_competitors"])
def test_a_required_count_of_zero_fails(field):
    mod = _load()
    _, (verdict, nfail, _) = _statuses(mod, **{field: 0})
    assert verdict == "FAIL" and nfail >= 1


def test_a_score_older_than_the_latest_run_warns_and_a_failed_latest_run_warns():
    mod = _load()
    old = NOW - dt.timedelta(minutes=100)
    res, (verdict, nfail, nwarn) = _statuses(mod, reputation_created=old, reputation_docs=29, documents=515)
    assert verdict == "PASS" and nfail == 0 and nwarn == 1
    assert "computed from 29 document(s) while 515 are now matched" in [r for r in res if r[0] == "WARN"][0][2]
    _, (v2, f2, w2) = _statuses(mod, latest_run_status="FAILED")
    assert (v2, f2, w2) == ("PASS", 0, 1)


def test_nobody_able_to_see_the_client_warns_and_a_bad_token_warns_only_when_checked():
    mod = _load()
    _, (_, nfail, nwarn) = _statuses(mod, grants=0, super_admins=0)
    assert nfail == 0 and nwarn == 1
    _, (_, nfail2, nwarn2) = _statuses(mod, token=(False, "HTTP 401"))
    assert nfail2 == 0 and nwarn2 == 1
