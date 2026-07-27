import requests
import feedparser
import json
from typing import List, Dict, Any
from datetime import datetime
from time import mktime
from .base import BaseAdapter
from app.utils.text_processing import clean_document_content

class RSSAdapter(BaseAdapter):
    def fetch(self, feed_url: str, **kwargs) -> List[Dict[str, Any]]:
        """Fetches RSS feed and returns entries."""
        headers = {
            "User-Agent": "windows:orm_collection:v1.0 (by /u/bot_tester_99)"
        }
        response = requests.get(feed_url, headers=headers, timeout=10)
        if response.status_code >= 400:
            raise Exception(f"HTTP Error {response.status_code} fetching feed: {feed_url}")
            
        feed = feedparser.parse(response.content)
        if feed.bozo and feed.bozo_exception:
            raise Exception(f"Invalid XML or Parse Error: {feed.bozo_exception}")
        return feed.entries

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        """
        Normalizes a feedparser entry into the standard NormalizedDocument mapping.
        """
        # Extract published date
        published_at = None
        if hasattr(raw_data, 'published_parsed') and raw_data.published_parsed:
            published_at = datetime.fromtimestamp(mktime(raw_data.published_parsed))
            
        # Get content (prefer content over summary)
        content = ""
        # Check dictionary keys first (for tests passing dicts), then attributes
        raw_content = raw_data.get('content') if isinstance(raw_data, dict) else getattr(raw_data, 'content', None)
        raw_summary = raw_data.get('summary') if isinstance(raw_data, dict) else getattr(raw_data, 'summary', None)

        if raw_content:
            if isinstance(raw_content, list) and len(raw_content) > 0:
                # Could be feedparser structure
                val = raw_content[0]
                content = val.value if hasattr(val, 'value') else (val.get('value') if isinstance(val, dict) else str(val))
            else:
                content = str(raw_content)
        elif raw_summary:
            content = str(raw_summary)
        
        # Clean content: strip HTML, remove placeholders
        content = clean_document_content(content)
            
        return {
            "source_id": str(source_id),
            "source_type": "rss",
            "title": raw_data.get('title', ''),
            "content": content,
            "url": raw_data.get('link', ''),
            "author": raw_data.get('author', None),
            "published_at": published_at,
            "collected_at": datetime.utcnow(),
            "raw_payload": json.dumps(raw_data)
        }

class GoogleNewsRSSAdapter(RSSAdapter):
    # Specialized logic for Google News can be added here if needed
    pass
