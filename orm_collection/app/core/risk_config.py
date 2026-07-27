# Configurable weights for the Weighted Risk Engine

TOPIC_WEIGHTS = {
    "General News": 5,
    "Partnership": 10,
    "Funding": 15,
    "Executive Changes": 20,
    "Customer Complaints": 30,
    "Employee Complaints": 35,
    "Layoffs": 40,
    "Cybersecurity": 60,
    "Data Breach": 80,
    "Legal": 90,
    "Fraud": 95,
    "Regulatory Action": 100
}

SENTIMENT_WEIGHTS = {
    "Positive": 0,
    "Neutral": 10,
    "Negative": 40
}

TREND_WEIGHTS = {
    "LOW": 10,
    "MEDIUM": 25,
    "HIGH": 50,
    "CRITICAL": 100
}

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

