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

    # Google News RSS descriptions append the source outlet's own name as
    # <font color="#6f6f6f">{source}</font> after the real headline. Left in,
    # this reads as ordinary article text to the entity matcher, and any
    # client with a competitor/brand entity whose name happens to equal a
    # real publisher name (e.g. "Business Today", "Guardian", "GuruFocus")
    # exact-matches every article that outlet republishes, regardless of
    # topic — confirmed live cross-tenant leak, see FINDINGS.md.
    for tag in soup.find_all('font'):
        if (tag.get('color') or '').strip().lower() == '#6f6f6f':
            tag.decompose()

    # Ars Technica's content:encoded always ends with two fixed-template
    # links: <p><a href="...">Read full article</a></p> followed by
    # <p><a href="...#comments">Comments</a></p> — confirmed structurally
    # identical (only the href varies) across every sampled entry during
    # TASK_ADD_RSS_FEEDS.md Phase 1 validation. Left in, "Read full article
    # Comments" gets appended as plain text to every document from this
    # source, the same class of matching-pollution risk as the Google News
    # boilerplate above, just plain-text UI chrome rather than a publisher
    # name. Matched on exact anchor text (not href, which varies per
    # article) so this only ever strips this specific template, never
    # genuine article prose.
    for a_tag in soup.find_all('a'):
        link_text = a_tag.get_text(strip=True).lower()
        if link_text in ('read full article', 'comments'):
            a_tag.decompose()

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
