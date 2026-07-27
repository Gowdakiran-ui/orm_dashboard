import re
import unicodedata
from typing import List, Set

def clean_html_tags(text: str) -> str:
    """Strip HTML tags and clean up common entities."""
    if not text:
        return ""
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Clean common HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&apos;', "'").replace('&#39;', "'")
    return text

def normalize_unicode_and_whitespace(text: str) -> str:
    """Normalize unicode characters and clean up excess spaces/newlines."""
    if not text:
        return ""
    # NFKC Normalize
    text = unicodedata.normalize('NFKC', text)
    # Standardize spaces and tabs
    text = re.sub(r'[ \t]+', ' ', text)
    # Standardize multiple newlines
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def remove_boilerplate(text: str) -> str:
    """Remove ads, banners, copyrights, and other noise."""
    if not text:
        return ""
    
    # Common cookie banner and privacy phrases
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

def extract_high_value_segments(text: str, title: str, summary: str, matched_keywords: Set[str]) -> str:
    """
    Extract title, summary, lead paragraphs, and paragraphs containing matched entities/keywords.
    Ensures text is highly informative and under token limits.
    """
    segments = []
    
    if title and title.strip():
        segments.append(f"Title: {title.strip()}")
        
    if summary and summary.strip():
        segments.append(f"Summary: {summary.strip()}")
        
    # Split text into paragraphs
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    
    lead_paragraphs = paragraphs[:2]
    other_paragraphs = paragraphs[2:]
    
    # Keep lead paragraphs
    for lp in lead_paragraphs:
        if lp not in segments:
            segments.append(lp)
            
    # Find paragraphs containing matched keywords/entities
    keyword_paragraphs = []
    if matched_keywords:
        for p in other_paragraphs:
            # Check if any keyword matches
            p_lower = p.lower()
            if any(kw.lower() in p_lower for kw in matched_keywords):
                keyword_paragraphs.append(p)
                
    # Append keyword-rich paragraphs (up to 4 to prevent bloat)
    for kp in keyword_paragraphs[:4]:
        if kp not in segments:
            segments.append(kp)
            
    # Fallback: if we have very little text, add some subsequent paragraphs
    if len(segments) <= 3 and other_paragraphs:
        for p in other_paragraphs[:3]:
            if p not in segments:
                segments.append(p)
                
    combined = "\n\n".join(segments)
    
    # Cap size cleanly at sentence boundaries (approx 2048 chars / ~400 words)
    if len(combined) > 2048:
        truncated = combined[:2000]
        # Find last sentence end
        last_dot = max(truncated.rfind('.'), truncated.rfind('?'), truncated.rfind('!'))
        if last_dot > 1000:
            combined = truncated[:last_dot + 1]
        else:
            combined = truncated + "..."
            
    return combined

def preprocess_document_text(raw_text: str, title: str = "", summary: str = "", matched_keywords: Set[str] = None) -> str:
    """Full preprocessing pipeline for Topic Classification."""
    if not raw_text:
        return ""
        
    # 1. Clean HTML tags
    cleaned = clean_html_tags(raw_text)
    
    # 2. Remove boilerplate
    cleaned = remove_boilerplate(cleaned)
    
    # 3. Unicode and whitespace normalization
    cleaned = normalize_unicode_and_whitespace(cleaned)
    
    # 4. Extract informative segments
    final_text = extract_high_value_segments(cleaned, title, summary, matched_keywords or set())
    
    return final_text
