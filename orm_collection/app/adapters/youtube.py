import json
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import os
from googleapiclient.discovery import build
from .search_base import BaseSearchAdapter

class YouTubeAdapter(BaseSearchAdapter):
    def __init__(self):
        self.api_key = os.environ.get("YOUTUBE_API_KEY", "dummy_api_key")
        self.youtube = None
        try:
            self.youtube = build("youtube", "v3", developerKey=self.api_key)
        except Exception:
            pass

    def search(self, keyword: str, cursor: Optional[str] = None, limit: int = 25, **kwargs) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self.youtube:
            return [], cursor
            
        results = []
        new_cursor = cursor
        
        try:
            request = self.youtube.search().list(
                part="snippet",
                q=keyword,
                maxResults=limit,
                pageToken=cursor,
                type="video",
                order="date"
            )
            response = request.execute()
            
            for item in response.get("items", []):
                # The search API doesn't return viewCount. For this milestone, we skip viewCount or assume 0
                # A secondary API call to videos().list() would be needed for view counts.
                results.append(item)
                
            new_cursor = response.get("nextPageToken")
            
        except Exception as e:
            raise Exception(f"YouTube Search Failed: {e}") from e
            
        return results, new_cursor

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        snippet = raw_data.get("snippet", {})
        video_id = raw_data.get("id", {}).get("videoId", "")
        
        published_str = snippet.get("publishedAt")
        published_at = datetime.utcnow()
        if published_str:
            try:
                published_at = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass
                
        return {
            "source_id": source_id,
            "source_type": "youtube",
            "title": snippet.get("title", ""),
            "content": snippet.get("description", ""), # description mapped to content
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "author": snippet.get("channelTitle", ""),
            "published_at": published_at,
            "collected_at": datetime.utcnow(),
            "raw_payload": json.dumps(raw_data)
        }
