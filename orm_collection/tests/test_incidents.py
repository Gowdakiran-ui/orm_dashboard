"""Incident grouping (incidents.py): real headlines from the production corpus, 2026-11-07."""
import datetime as dt

from app.services.intelligence.incidents import group_incidents, outlet_of, title_tokens, event_tokens

UTC = dt.timezone.utc


def D(y, m, d):
    return dt.datetime(y, m, d, tzinfo=UTC)


def item(title, when, event=None, entity="e1", name="EaseMyTrip"):
    return {"entity_id": entity, "entity_name": name, "title": title, "published_at": when, "event": event}


def sizes(items):
    return [len(g) for g in group_incidents(items)]


CHARGESHEET = [
    ("ED chargesheets EaseMyTrip promoter Nishant Pitti in Mahadev betting app case - ThePrint", D(2026, 9, 21), "ed chargesheet nishant pitti mahadev betting"),
    ("ED Chargesheets EaseMyTrip Cofounder Nishant Pitti In Mahadev Betting Case - Inc42", D(2026, 9, 22), "ed chargesheet easemytrip cofounder mahadev betting"),
    ("India’s Enforcement Directorate charges EaseMyTrip co-founder in Mahadev betting case - Focus Gaming News", D(2026, 9, 22), "enforcement directorate charges cofounder mahadev betting"),
    ("ED files chargesheet against EaseMyTrip Nishant Pitti in Mahadev betting case", D(2026, 9, 23), "ed chargesheet pitti mahadev betting"),
]


def test_the_same_chargesheet_story_from_different_outlets_is_one_incident():
    assert sizes([item(*c) for c in CHARGESHEET]) == [4]


def test_event_phrase_joins_a_headline_in_another_language():
    hindi = item("ईज़माईट्रिप के सह-संस्थापक पर ईडी की चार्जशीट, महादेव बेटिंग केस - Jagran", D(2026, 9, 22), "ed chargesheet nishant pitti mahadev betting")
    assert sizes([item(*CHARGESHEET[0]), hindi]) == [2]


def test_without_an_event_phrase_a_foreign_language_headline_stays_separate():
    hindi = item("ईज़माईट्रिप के सह-संस्थापक पर ईडी की चार्जशीट - Jagran", D(2026, 9, 22), None)
    assert sizes([item(*CHARGESHEET[0]), hindi]) == [1, 1]


def test_a_raid_and_a_chargesheet_seventeen_months_apart_are_two_incidents():
    raid = item("Mahadev app case: ED searches premises of EaseMyTrip co-founder Pitti in fresh raids - The Tribune", D(2025, 4, 16), "ed searches easemytrip cofounder pitti mahadev app")
    assert sizes([raid, item(*CHARGESHEET[0])]) == [1, 1]


def test_different_entities_are_never_one_incident():
    a, b = item(*CHARGESHEET[0]), item(*CHARGESHEET[1], entity="e2")
    assert sizes([a, b]) == [1, 1]


def test_unrelated_stories_stay_apart_even_for_the_same_company_and_week():
    fine = item("Hyderabad: EaseMyTrip, Qatar Airways fined ₹3.06L for denying ticket to patient - NewsMeter", D(2026, 9, 21), "easemytrip qatar airways fined denying ticket patient")
    assert sizes([fine, item(*CHARGESHEET[0])]) == [1, 1]


def test_rera_penalty_reported_with_different_wording_groups():
    items = [
        item("Godrej Properties Hit With ₹10 Lakh CGRERA Penalty Over Ad Violation - scanx.trade", D(2026, 7, 3), "godrej properties cgrera penalty advertisement violation", name="Godrej Properties"),
        item("CGRERA Slaps ₹10 Lakh Penalty on Godrej Properties Under RERA Act Compliance Norms - sahi.com", D(2026, 7, 4), "cgrera penalty godrej properties rera compliance", name="Godrej Properties"),
        item("Godrej Properties faces Rs. 10 lakh RERA penalty over Greenvale Estate ads - The Globe and Mail", D(2026, 7, 4), "godrej properties rera penalty greenvale estate ads", name="Godrej Properties"),
    ]
    assert sizes(items) == [3]


def test_links_chain_and_every_item_lands_in_exactly_one_group():
    items = [item(*c) for c in CHARGESHEET] + [item("Unrelated airline fine - X", D(2026, 9, 21), "airline fine")]
    groups = group_incidents(items)
    assert sorted(i for g in groups for i in g) == list(range(len(items)))
    assert [len(g) for g in groups] == [4, 1]                      # largest first


def test_missing_dates_and_mixed_naive_aware_dates_do_not_crash():
    a = item(*CHARGESHEET[0])
    b = item(*CHARGESHEET[1])
    b["published_at"] = None
    c = item(*CHARGESHEET[2])
    c["published_at"] = dt.datetime(2026, 9, 22)                    # naive
    assert sizes([a, b, c]) == [3]


def test_empty_input_and_untitled_items():
    assert group_incidents([]) == []
    assert sizes([item(None, None), item(None, None)]) == [1, 1]


def test_outlet_and_tokens():
    assert outlet_of("ED raids EaseMyTrip - The Times of India") == "the times of india"
    assert outlet_of("A headline with no outlet") is None
    assert outlet_of("A headline - " + "x" * 60) is None            # a long tail is not an outlet name
    assert "easemytrip" not in title_tokens("ED raids EaseMyTrip - Mint", "EaseMyTrip")
    assert "easemytrip" not in event_tokens("ed raids easytrip founder", "EaseMyTrip")     # spelling variants of the entity are dropped too
    assert {"chargesheet"} <= title_tokens("ED charges co-founder") and {"chargesheet"} <= title_tokens("ED chargesheets co-founder")
