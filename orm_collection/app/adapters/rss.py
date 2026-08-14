import requests
import feedparser
import json
from typing import List, Dict, Any
from datetime import datetime, timezone
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
        # Extract published date. Use dict-style access, not hasattr/attribute
        # access: after an async round-trip through json.dumps/json.loads (see
        # collection_tasks.py -> document_processor.py), feedparser's
        # FeedParserDict becomes a plain dict, which doesn't expose keys as
        # attributes. FeedParserDict is itself a dict subclass, so .get()
        # works identically for both the live feedparser object and the
        # deserialized plain dict.
        published_at = None
        published_parsed = raw_data.get('published_parsed')
        if published_parsed:
            # After the async json.dumps/json.loads round-trip, struct_time
            # comes back as a plain list, which mktime() rejects (it only
            # accepts a tuple or struct_time). Coerce to tuple first.
            # mktime() interprets its input as LOCAL time and fromtimestamp()
            # (no tz arg) converts back to local naive time, so the local
            # offset cancels out and the naive result's wall-clock value
            # already equals the UTC value feedparser gives us (feedparser
            # always normalizes published_parsed to UTC). Passing tz=utc
            # directly to fromtimestamp() here would NOT be equivalent — the
            # epoch value from mktime() already has the local-offset
            # assumption baked in, so interpreting it as UTC would shift the
            # result by the local UTC offset. Just label the existing
            # (already-correct) naive value as UTC (see FINDINGS.md D9).
            published_at = datetime.fromtimestamp(mktime(tuple(published_parsed))).replace(tzinfo=timezone.utc)
            
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
            "collected_at": datetime.now(timezone.utc),
            "raw_payload": json.dumps(raw_data)
        }

class GoogleNewsRSSAdapter(RSSAdapter):
    # Specialized logic for Google News can be added here if needed
    pass
