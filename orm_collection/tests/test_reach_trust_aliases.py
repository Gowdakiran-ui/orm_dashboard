"""Outlet trust list, Part A only (audit/outlet-trust-proposal.md, 2026-10-03): five spellings of outlets that were already trusted.
Nothing else on the list changed; stored scores are not rescored (the change affects events scored from now on)."""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.core.reach_trust_config import TRUSTED_OUTLETS, get_trust_tier, is_rss_trust_eligible

PART_A = {
    "the business standard": "high",
    "business-standard.com": "high",
    "realty.economictimes.indiatimes.com": "high",
    "economictimes.indiatimes.com": "high",
    "thehindu.com": "medium",
}

# The list as it was before Part A (21 entries), pinned so any other change is a visible decision.
BEFORE = {
    "the economic times": "high", "economictimes.com": "high", "moneycontrol.com": "high", "moneycontrol": "high", "business standard": "high",
    "livemint": "high", "mint": "high", "reuters": "high", "reuters.com": "high", "bloomberg": "high", "bloomberg.com": "high",
    "the hindu": "medium", "hindustan times": "medium", "the times of india": "medium", "times of india": "medium", "ndtv": "medium",
    "ndtv profit": "medium", "the indian express": "medium", "indian express": "medium",
    "bw businessworld": "low", "construction week india": "low", "devdiscourse": "low", "realty plus magazine": "low",
}


@pytest.mark.parametrize("outlet,tier", sorted(PART_A.items()))
def test_each_part_a_spelling_is_trusted_and_eligible(outlet, tier):
    title = f"Godrej Properties falls 5% despite strong Q4 - {outlet}"
    assert get_trust_tier(title) == tier
    assert is_rss_trust_eligible(title) is True


@pytest.mark.parametrize("outlet,tier", sorted(PART_A.items()))
def test_spelling_matches_case_insensitively(outlet, tier):
    assert get_trust_tier("Headline - " + outlet.upper()) == tier


def test_the_list_is_exactly_before_plus_part_a_nothing_else():
    assert TRUSTED_OUTLETS == {**BEFORE, **PART_A}
    assert len(TRUSTED_OUTLETS) == len(BEFORE) + 5


@pytest.mark.parametrize("outlet", ["CNBC TV18", "Business Today", "BusinessLine", "ThePrint", "The New Indian Express", "The Tribune", "Fortune India",
                                    "TheWire.in", "ETLegalWorld.com", "TradingView", "Univest", "Yahoo Finance"])
def test_part_b_outlets_are_still_not_trusted(outlet):
    assert get_trust_tier(f"Some headline - {outlet}") == "unknown"
    assert is_rss_trust_eligible(f"Some headline - {outlet}") is False


@pytest.mark.parametrize("outlet", ["BW Businessworld", "Construction Week India"])
def test_low_tier_outlets_stay_low_and_gated(outlet):
    assert get_trust_tier(f"Some headline - {outlet}") == "low"
    assert is_rss_trust_eligible(f"Some headline - {outlet}") is False
