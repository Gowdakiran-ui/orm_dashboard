import requests
import json
from typing import List, Dict, Any
from datetime import datetime, timezone
from .base import BaseAdapter
from app.utils.text_processing import clean_document_content


class GDELTAdapter(BaseAdapter):
    """
    GDELT DOC 2.0 API adapter. feed_url is expected to be a fully-formed
    query URL, e.g.
    https://api.gdeltproject.org/api/v2/doc/doc?query=Tesla&mode=artlist&format=json&maxrecords=50

    Rate limit (confirmed live): GDELT returns HTTP 429 for requests closer
    together than ~5s. Callers must respect poll_interval_minutes and not
    poll this more aggressively than that.
    """

    def fetch(self, feed_url: str, **kwargs) -> List[Dict[str, Any]]:
        headers = {
            "User-Agent": "windows:orm_collection:v1.0 (by /u/bot_tester_99)"
        }
        response = requests.get(feed_url, headers=headers, timeout=15)
        if response.status_code >= 400:
            raise Exception(f"HTTP Error {response.status_code} fetching GDELT feed: {feed_url}")

        data = response.json()
        return data.get("articles", [])

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        """
        Normalizes a GDELT DOC 2.0 article into the standard NormalizedDocument mapping.
        GDELT does not return article body text — only metadata — so `content`
        falls back to `title`, same pattern RSSAdapter uses when a feed has no
        full content, only a summary.
        """
        published_at = None
        seendate = raw_data.get("seendate")
        if seendate:
            try:
                published_at = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                published_at = None

        title = raw_data.get("title", "")
        content = clean_document_content(title)

        return {
            "source_id": str(source_id),
            "source_type": "gdelt",
            "title": title,
            "content": content,
            "url": raw_data.get("url", ""),
            "author": None,
            "published_at": published_at,
            "collected_at": datetime.now(timezone.utc),
            "raw_payload": json.dumps(raw_data)
        }
