import requests
import json
from typing import List, Dict, Any
from datetime import datetime, timezone
from .base import BaseAdapter
from app.utils.text_processing import clean_document_content


class HNAlgoliaAdapter(BaseAdapter):
    """
    Hacker News Algolia search API adapter. feed_url is expected to be a
    fully-formed query URL, e.g.
    https://hn.algolia.com/api/v1/search?query=Tesla&tags=story
    """

    def fetch(self, feed_url: str, **kwargs) -> List[Dict[str, Any]]:
        headers = {
            "User-Agent": "windows:orm_collection:v1.0 (by /u/bot_tester_99)"
        }
        response = requests.get(feed_url, headers=headers, timeout=15)
        if response.status_code >= 400:
            raise Exception(f"HTTP Error {response.status_code} fetching HN Algolia feed: {feed_url}")

        data = response.json()
        return data.get("hits", [])

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        """
        Normalizes an HN Algolia hit into the standard NormalizedDocument mapping.
        Most HN stories are link posts with no body text — `content` falls back
        to `story_text` (self-posts only) then `title`, same "no full text
        available" pattern as the RSS/GDELT adapters.
        """
        published_at = None
        created_at = raw_data.get("created_at")
        if created_at:
            try:
                published_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                published_at = None

        title = raw_data.get("title", "")
        # Link posts have no external url; fall back to the HN discussion page.
        url = raw_data.get("url") or f"https://news.ycombinator.com/item?id={raw_data.get('objectID', '')}"
        raw_content = raw_data.get("story_text") or title
        content = clean_document_content(raw_content)

        return {
            "source_id": str(source_id),
            "source_type": "hn_algolia",
            "title": title,
            "content": content,
            "url": url,
            "author": raw_data.get("author"),
            "published_at": published_at,
            "collected_at": datetime.now(timezone.utc),
            "raw_payload": json.dumps(raw_data)
        }
