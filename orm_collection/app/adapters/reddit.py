import praw
import json
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import os
from .search_base import BaseSearchAdapter

class RedditAdapter(BaseSearchAdapter):
    def __init__(self):
        # We assume credentials exist in environment for production.
        # This will fail gracefully or we mock it in tests.
        self.client_id = os.environ.get("REDDIT_CLIENT_ID", "dummy_client_id")
        self.client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "dummy_secret")
        self.user_agent = os.environ.get("REDDIT_USER_AGENT", "ORM_Collection_Agent")
        
        # PRAW initialization only succeeds if valid credentials or handled otherwise
        self.reddit = None
        try:
            self.reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent
            )
        except Exception:
            pass

    def search(self, keyword: str, cursor: Optional[str] = None, limit: int = 25, **kwargs) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self.reddit:
            return [], cursor
            
        params = {"limit": limit}
        if cursor:
            params["params"] = {"after": cursor}
            
        results = []
        new_cursor = cursor
        
        try:
            subreddit = self.reddit.subreddit("all")
            # Using PRAW search, which returns a ListingGenerator
            for submission in subreddit.search(keyword, sort="new", **params):
                results.append({
                    "id": submission.id,
                    "title": submission.title,
                    "selftext": submission.selftext,
                    "subreddit": submission.subreddit.display_name,
                    "author": submission.author.name if submission.author else "[deleted]",
                    "score": submission.score,
                    "num_comments": submission.num_comments,
                    "url": submission.url,
                    "created_utc": submission.created_utc,
                    "name": submission.name # Full ID needed for 'after' pagination
                })
                new_cursor = submission.name
        except Exception as e:
            raise Exception(f"Reddit Search Failed: {e}") from e
            
        return results, new_cursor

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        published_at = datetime.utcfromtimestamp(raw_data.get("created_utc", 0))
        
        return {
            "source_id": source_id,
            "source_type": "reddit",
            "title": raw_data.get("title", ""),
            "content": raw_data.get("selftext", ""),
            "url": raw_data.get("url", ""),
            "author": raw_data.get("author", ""),
            "published_at": published_at,
            "collected_at": datetime.utcnow(),
            "raw_payload": json.dumps(raw_data)
        }
