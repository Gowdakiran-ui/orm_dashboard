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
    # youtu.be/{id} (path-based) not /watch?v={id} (query-based) -- the
    # video ID must survive canonicalize_url()'s query-string stripping,
    # or every video collapses onto the same canonical URL and gets
    # silently deduplicated after the first one ever saved.
    assert normalized["url"] == "https://youtu.be/test_vid_123"
    # Part D fix 1: title is prepended to content so entity matching (which
    # only ever scans `content`/normalized_content, never the separate
    # `title` field) can see brand names that appear in the title but not
    # the description -- confirmed live as the cause of real high-view
    # videos never getting an entity_mention at all.
    assert normalized["content"] == "Test YouTube Title\n\nTest youtube content"
    assert normalized["source_id"] == "test_source_id"
    assert normalized["source_type"] == "youtube"
    assert normalized["author"] == "testchannel"


def test_youtube_adapter_normalize_includes_stats_prefix_when_available():
    adapter = YouTubeAdapter()

    mock_raw_data = {
        "id": {"videoId": "test_vid_456"},
        "snippet": {
            "title": "Stats Video",
            "description": "Some description",
            "channelTitle": "testchannel",
            "publishedAt": "2020-09-13T12:26:40Z"
        },
        "statistics": {"viewCount": "1200000", "commentCount": "340"}
    }

    normalized = adapter.normalize(mock_raw_data, "test_source_id")

    assert normalized["content"] == "Stats Video\n\n1.2M views, 340 comments\n\nSome description"


def test_youtube_adapter_unavailable_without_api_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    adapter = YouTubeAdapter()

    assert adapter.available is False
    results, cursor = adapter.search("anything", cursor="c1")
    assert results == []
    assert cursor == "c1"
