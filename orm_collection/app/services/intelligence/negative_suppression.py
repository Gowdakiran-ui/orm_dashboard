import re
from typing import List, Set

def apply_negative_suppression(text: str, detected_topics: List[str]) -> List[str]:
    """
    Apply deterministic rules to suppress false positive topics based on context.
    No AI, no LLM, no embeddings. Purely deterministic rules.
    """
    if not text or not detected_topics:
        return detected_topics

    text_lower = text.lower()
    suppressed = set()

    # Rule 1: Nikola Tesla (historical/physics context) -> Suppress Electric Vehicles / Full Self-Driving / Autopilot
    if "nikola tesla" in text_lower or "tesla coil" in text_lower:
        # Check if it's about the company or the person. If it mentions "Nikola Tesla" but NOT "Elon Musk", "EV", "stock", "TSLA", "car", or "battery"
        # NS8-F3: added "battery" -- e.g. "The Nikola Tesla Award for Battery
        # Innovation Goes to Tesla Inc." previously had no company keyword to
        # match on, so a genuine Tesla battery-technology article got its EV
        # classification stripped just for referencing "Nikola Tesla".
        company_keywords = ["musk", "ev", "stock", "tsla", "car", "vehicle", "model 3", "model y", "model s", "model x", "gigafactory", "quarterly", "battery"]
        if not any(kw in text_lower for kw in company_keywords):
            suppressed.add("Electric Vehicles")
            suppressed.add("Full Self-Driving / Autopilot")

    # Rule 2: Apple Pie -> Suppress Consumer Electronics
    if "apple pie" in text_lower or "baked apple" in text_lower:
        suppressed.add("Consumer Electronics")

    # Rule 3: Meta-analysis -> Suppress Social Media
    if "meta-analysis" in text_lower or "meta-analyses" in text_lower or "meta analysis" in text_lower:
        # If it's about a scientific meta-analysis and not the company Meta
        company_keywords = ["zuckerberg", "instagram", "whatsapp", "facebook", "quest", "threads", "social network", "ad revenue"]
        if not any(kw in text_lower for kw in company_keywords):
            suppressed.add("Social Media")

    # Rule 4: Ford (Actor/Harrison) -> Suppress Automotive / Electric Vehicles
    if "ford" in text_lower:
        actor_keywords = ["harrison", "actor", "movie", "star", "film", "hollywood", "indiana jones", "star wars"]
        # NS8-F2: "star" alone is a bare substring match that also fires
        # inside ordinary words ("startup", "restart", "Ford's EV lineup
        # starts...") and was suppressing genuine Ford EV coverage. Gate on
        # the same pattern Rule 1 (Nikola Tesla) already uses: only suppress
        # if no automotive/EV context is present alongside the actor cue.
        automotive_keywords = ["ev", "electric", "car", "vehicle", "motor", "truck", "suv", "mustang", "f-150", "bronco", "quarterly", "stock"]
        if any(kw in text_lower for kw in actor_keywords) and not any(kw in text_lower for kw in automotive_keywords):
            suppressed.add("Automotive")
            suppressed.add("Electric Vehicles")
            suppressed.add("Full Self-Driving / Autopilot")

    # Rule 5: NLP audit Part 2 -- "Full Self-Driving / Autopilot" (formerly
    # "Autonomous Driving") still over-triggers on two recurring, structurally
    # identifiable real-world publisher patterns even after the label rename
    # and threshold raise (verified live against a real 110-doc Tesla corpus,
    # see NLP_AUDIT_FIX_VERIFICATION.md): (a) MarketBeat-style automated
    # share-transaction wire briefs ("X Acquires/Purchases/Invests ... Shares
    # in Tesla"), which mention nothing about driving at all, and (b)
    # test-drive/ownership-review pieces ("Test drove...", "My experience...",
    # "...km with my Tesla"), which are about a human driving the car, not
    # the car driving itself. Both suppress only when no genuine FSD/Autopilot/
    # robotaxi keyword is present, so real self-driving coverage from the same
    # publishers (e.g. "Tesla's Cybercab Launch...") is untouched.
    fsd_keywords = ["self-driving", "self driving", "full self-driving", "fsd", "autopilot", "robotaxi", "cybercab", "autonomous", "driverless"]
    if not any(kw in text_lower for kw in fsd_keywords):
        marketbeat_patterns = ["position in tesla", "shares in tesla", "invests $", "purchases shares", "makes new investment"]
        testdrive_patterns = ["test drove", "test driving", "first impressions", "ownership costs"]
        if any(p in text_lower for p in marketbeat_patterns) or any(p in text_lower for p in testdrive_patterns):
            suppressed.add("Full Self-Driving / Autopilot")

    # Filter out suppressed topics
    final_topics = [t for t in detected_topics if t not in suppressed]
    return final_topics
