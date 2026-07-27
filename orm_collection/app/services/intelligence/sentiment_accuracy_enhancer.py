import os
import re
import uuid
from typing import List, Dict, Any, Set
from sqlalchemy.orm import Session
from app.models.document import Document, DocumentMatch
from app.models.entity import Entity
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.source import Source, SourceCategory
from app.models.system import ModelRun

# Re-use or define our own high-value segment extraction and preprocessing inside our analyzer to keep it isolated and locked
def clean_html_tags(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&apos;', "'").replace('&#39;', "'")
    return text

def remove_boilerplate(text: str) -> str:
    if not text:
        return ""
    boilerplate_patterns = [
        r"(?i)this website uses cookies to ensure you get the best experience.*?\.",
        r"(?i)by continuing to browse the site you are agreeing to our use of cookies.*?\.",
        r"(?i)read our privacy policy.*?\.",
        r"(?i)all rights reserved\b.*?\bcopyright\b.*?\.",
        r"(?i)copyright © \d{4}.*?\.",
        r"(?i)share this article on (facebook|twitter|linkedin|reddit)",
        r"(?i)subscribe to our newsletter for more updates.*?\.",
        r"(?i)advertisement\b",
        r"(?i)click here to read more.*?\."
    ]
    cleaned_text = text
    for pattern in boilerplate_patterns:
        cleaned_text = re.sub(pattern, ' ', cleaned_text)
    return cleaned_text

def normalize_unicode_and_whitespace(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def extract_high_value_segments(text: str, title: str, summary: str, matched_keywords: Set[str]) -> str:
    segments = []
    if title and title.strip():
        segments.append(f"Title: {title.strip()}")
    if summary and summary.strip():
        segments.append(f"Summary: {summary.strip()}")
        
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    lead_paragraphs = paragraphs[:2]
    other_paragraphs = paragraphs[2:]
    
    for lp in lead_paragraphs:
        if lp not in segments:
            segments.append(lp)
            
    keyword_paragraphs = []
    if matched_keywords:
        for p in other_paragraphs:
            p_lower = p.lower()
            if any(kw.lower() in p_lower for kw in matched_keywords):
                keyword_paragraphs.append(p)
                
    for kp in keyword_paragraphs[:4]:
        if kp not in segments:
            segments.append(kp)
            
    if len(segments) <= 3 and other_paragraphs:
        for p in other_paragraphs[:3]:
            if p not in segments:
                segments.append(p)
                
    combined = "\n\n".join(segments)
    if len(combined) > 2048:
        truncated = combined[:2000]
        last_dot = max(truncated.rfind('.'), truncated.rfind('?'), truncated.rfind('!'))
        if last_dot > 1000:
            combined = truncated[:last_dot + 1]
        else:
            combined = truncated + "..."
    return combined

def preprocess_text(raw_text: str, title: str = "", summary: str = "", matched_keywords: Set[str] = None) -> str:
    if not raw_text:
        return ""
    cleaned = clean_html_tags(raw_text)
    cleaned = remove_boilerplate(cleaned)
    cleaned = normalize_unicode_and_whitespace(cleaned)
    return extract_high_value_segments(cleaned, title, summary, matched_keywords or set())

# ORM Keywords and categories
NEG_WORDS = ["recall", "recalls", "lawsuit", "lawsuits", "scandal", "investigate", "investigation", "investigations", "probe", "scandal", "breach", "hack", "layoffs", "layoff", "fine", "fines", "bankruptcy", "sued", "court", "fraud", "complaint", "defect", "safety data", "misleading", "fatal", "crash", "accident"]
POS_WORDS = ["profit", "profits", "beat", "launch", "launches", "innovation", "breakthrough", "partnership", "expansion", "award", "success", "record", "growth"]

def apply_orm_rules(text_content: str, raw_label: str, raw_score: float) -> Dict[str, Any]:
    text_lower = text_content.lower()
    final_label = raw_label
    final_score = raw_score
    applied_rule = None
    trigger_words = []

    # Check negative risk matches
    matched_neg = [w for w in NEG_WORDS if w in text_lower]
    matched_pos = [w for w in POS_WORDS if w in text_lower]

    if matched_neg:
        trigger_words = matched_neg[:3]
        if raw_label == "neutral":
            # Upgrade neutral to negative for severe ORM risk
            final_label = "negative"
            final_score = min(raw_score + 0.15, 1.0)
            applied_rule = "Negative-Risk Upgrade"
        elif raw_label == "negative":
            # Boost negative confidence
            final_score = min(raw_score + 0.15, 1.0)
            applied_rule = "Negative-Risk Boost"
    elif matched_pos:
        trigger_words = matched_pos[:3]
        if raw_label == "neutral" and raw_score < 0.65:
            # Calibrate positive
            final_label = "positive"
            final_score = min(raw_score + 0.10, 1.0)
            applied_rule = "Positive-Milestone Upgrade"
        elif raw_label == "positive":
            final_score = min(raw_score + 0.10, 1.0)
            applied_rule = "Positive-Milestone Boost"

    # Calibration gate: if low confidence and no rule matched, default to Neutral
    if final_score < 0.65 and not applied_rule:
        final_label = "neutral"
        final_score = 1.0
        applied_rule = "Low-Confidence Neutral Calibration"

    return {
        "label": final_label,
        "score": final_score,
        "applied_rule": applied_rule,
        "trigger_words": trigger_words
    }

def get_dynamic_source_reliability(db: Session, source_id: str, url: str) -> float:
    # Default fallback
    reliability = 1.0
    if not source_id:
        return reliability

    source = db.query(Source).filter(Source.id == source_id).first()
    if source:
        # Check category reliability
        category = db.query(SourceCategory).filter(SourceCategory.id == source.category_id).first()
        if category:
            reliability = float(category.base_reliability_score or 1.0)
        
        # Override based on source type
        st_lower = str(source.source_type).lower()
        if "reddit" in st_lower or "forum" in st_lower or "social" in st_lower:
            reliability = min(reliability, 0.60)
        elif "rss" in st_lower:
            # Check domain name to see if it is verified news
            url_lower = str(url or source.url).lower()
            if any(domain in url_lower for domain in ["reuters.com", "bloomberg.com", "wsj.com", "nytimes.com", "ft.com"]):
                reliability = 1.00
            else:
                reliability = min(reliability, 0.80)
    return reliability
