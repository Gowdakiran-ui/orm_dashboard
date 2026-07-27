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

    # Rule 1: Nikola Tesla (historical/physics context) -> Suppress Electric Vehicles / Autonomous Driving
    if "nikola tesla" in text_lower or "tesla coil" in text_lower:
        # Check if it's about the company or the person. If it mentions "Nikola Tesla" but NOT "Elon Musk", "EV", "stock", "TSLA", or "car"
        company_keywords = ["musk", "ev", "stock", "tsla", "car", "vehicle", "model 3", "model y", "model s", "model x", "gigafactory", "quarterly"]
        if not any(kw in text_lower for kw in company_keywords):
            suppressed.add("Electric Vehicles")
            suppressed.add("Autonomous Driving")

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
        if any(kw in text_lower for kw in actor_keywords):
            suppressed.add("Automotive")
            suppressed.add("Electric Vehicles")
            suppressed.add("Autonomous Driving")

    # Filter out suppressed topics
    final_topics = [t for t in detected_topics if t not in suppressed]
    return final_topics
