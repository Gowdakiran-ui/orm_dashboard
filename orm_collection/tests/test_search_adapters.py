import pytest
from app.adapters.reddit import RedditAdapter
from app.adapters.youtube import YouTubeAdapter

def test_reddit_adapter_normalize():
    adapter = RedditAdapter()
    
    mock_raw_data = {
        "title": "Test Reddit Title",
        "selftext": "Test reddit content",
        "subreddit": "testsub",
        "author": "testauthor",
        "url": "http://reddit.com/r/testsub/post",
        "created_utc": 1600000000
    }
    
    normalized = adapter.normalize(mock_raw_data, "test_source_id")
    
    assert normalized["title"] == "Test Reddit Title"
    assert normalized["url"] == "http://reddit.com/r/testsub/post"
    assert normalized["content"] == "Test reddit content"
    assert normalized["source_id"] == "test_source_id"
    assert normalized["source_type"] == "reddit"
    assert normalized["author"] == "testauthor"

def test_youtube_adapter_normalize():
    adapter = YouTubeAdapter()
    
    mock_raw_data = {
        "id": {"videoId": "test_vid_123"},
        "snippet": {
            "title": "Test YouTube Title",
            "description": "Test youtube content",
            "channelTitle": "testchannel",
            "publishedAt": "2020-09-13T12:26:40Z"
        }
    }
    
    normalized = adapter.normalize(mock_raw_data, "test_source_id")
    
    assert normalized["title"] == "Test YouTube Title"
    assert normalized["url"] == "https://www.youtube.com/watch?v=test_vid_123"
    assert normalized["content"] == "Test youtube content"
    assert normalized["source_id"] == "test_source_id"
    assert normalized["source_type"] == "youtube"
    assert normalized["author"] == "testchannel"
