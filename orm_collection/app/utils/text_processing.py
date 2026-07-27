import hashlib
import re
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup

def canonicalize_url(url: str) -> str:
    """
    Canonicalizes a URL by stripping out tracking query parameters.
    """
    if not url:
        return ""
        
    parsed = urlparse(url)
    
    # Keeping it simple for the milestone: drop query and fragment entirely
    # Alternatively, we could filter out specific params like utm_*
    canonical = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, '', ''))
    return canonical

def generate_content_hash(text: str) -> str:
    """
    Generates a SHA256 hash of the content.
    """
    if not text:
        return ""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def strip_html(html_content: str) -> str:
    """
    Safely strip HTML tags and decode HTML entities.
    Preserves text content while removing markup.
    """
    if not html_content:
        return ""
    
    # Use BeautifulSoup to safely strip HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def remove_placeholder_text(content: str) -> str:
    """
    Remove common placeholder text patterns.
    """
    if not content:
        return ""
    
    # Common placeholder patterns
    placeholders = [
        r'Content content content',
        r'bench content text',
        r'^\s*$',
        r'^\s*<a href',  # HTML-only fragments
    ]
    
    for pattern in placeholders:
        if re.match(pattern, content, re.IGNORECASE):
            return ""
    
    # Check if content is too short after stripping
    if len(content.strip()) < 20:
        return ""
    
    return content

def clean_document_content(content: str) -> str:
    """
    Full content cleaning pipeline:
    1. Strip HTML
    2. Remove placeholders
    3. Normalize whitespace
    """
    if not content:
        return ""
    
    # Strip HTML
    cleaned = strip_html(content)
    
    # Remove placeholders
    cleaned = remove_placeholder_text(cleaned)
    
    return cleaned
