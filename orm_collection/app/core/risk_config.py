# Configurable weights for the Weighted Risk Engine

# Keys MUST be the exact `topics.name` strings seeded in database/seed_dev.sql
# (the 17-label taxonomy). Until 2026-09-30 this dict was keyed on a different,
# generic taxonomy (General News, Layoffs, Data Breach, Fraud, ...) written in
# the initial commit, so only "Cybersecurity" ever matched and topic_weight was
# 0 for every other label (TOPIC_WEIGHTS.get(name, 0) in risk_engine.py).
#
# A weight > 0 also makes a document "risk-relevant" regardless of sentiment
# (risk_engine.py: is_risk_relevant = Negative OR topic_weight > 0), so weights
# are assigned ONLY to labels that are inherently risky on their own. Labels
# with ambiguous polarity or a neutral business subject are deliberately 0 --
# their risk comes from sentiment/trend instead; weighting them re-creates the
# LOW-severity noise from routine positive news that gate exists to prevent.
TOPIC_WEIGHTS = {
    # Inherently risky
    "Regulatory Risk": 100,
    "Legal Risk": 90,
    "Cybersecurity": 60,
    "Safety Recall": 60,
    "Labor Relations": 35,
    # Deliberately 0: ambiguous polarity (sentiment decides)
    "Customer Satisfaction": 0,
    "Environmental": 0,
    "Full Self-Driving / Autopilot": 0,
    # Deliberately 0: neutral business subject
    "Executive Leadership": 0,
    "Mergers & Acquisitions": 0,
    "Innovation": 0,
    "Financial Results": 0,
    "Competition": 0,
    "Market Share": 0,
    "Product Launch": 0,
    "Electric Vehicles": 0,
    "Energy Storage": 0,
}

SENTIMENT_WEIGHTS = {
    "Positive": 0,
    "Neutral": 10,
    "Negative": 40
}

# Trend detection was removed from the risk formula (2026-10-01): the old
# TREND_WEIGHTS table fed a client-wide, direction-less coverage-volume signal
# into every RiskEvent. The risk score is now (topic + sentiment) / divisor.
# The divisor is the maximum achievable topic + sentiment weight, derived from
# the tables above so the 0-100 scale stays correct if either table changes
# (140 today = 100 + 40). Keeping the old 240 (= 140 + max trend 100) would
# compress every score by ~42% and push negative-only documents below
# RISK_ROLE_CLASSIFICATION_MIN_SCORE (25), disabling the LLM bystander gate.
RISK_SCORE_DIVISOR = float(max(TOPIC_WEIGHTS.values()) + max(SENTIMENT_WEIGHTS.values()))

# Example mappings. If source not found, defaults to 50
SOURCE_RELIABILITY_MAP = {
    "Reuters": 95,
    "BBC": 90,
    "Reddit": 60,
    "YouTube": 70
}

def get_source_reliability_modifier(source_name: str) -> float:
    # Convert score (0-100) to modifier (0.0 to 1.0)
    score = SOURCE_RELIABILITY_MAP.get(source_name, 80) # Default to 80 if unknown
    return score / 100.0


# --- Phase 5.2 Configurable Dynamic Source Reliability Mappings ---
DYNAMIC_SOURCE_RELIABILITY_MAP = {
    "government": 1.20,
    "regulatory": 1.20,
    "court": 1.20,
    "company": 1.10,
    "news": 1.00,
    "blog": 0.85,
    "social": 0.70,
    "forum": 0.70,
    "default": 1.00
}

# --- Phase 5.2 Configurable Severity Thresholds ---
RISK_THRESHOLDS = {
    "LOW_TO_MEDIUM": 25.0,    # Scores <= 25.0 are LOW
    "MEDIUM_TO_HIGH": 50.0,   # Scores <= 50.0 are MEDIUM
    "HIGH_TO_CRITICAL": 75.0, # Scores <= 75.0 are HIGH, > 75.0 are CRITICAL
}

