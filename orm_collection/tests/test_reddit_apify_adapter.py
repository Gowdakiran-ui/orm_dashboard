import pytest
from app.adapters.reddit_apify import RedditApifyAdapter, MAX_RESULTS_PER_CALL


def test_reddit_apify_adapter_normalize():
    adapter = RedditApifyAdapter()

    # Real item captured from a live trudax/reddit-scraper-lite test call
    # (searches=["Godrej Properties"], searchPosts=True, maxItems=5,
    # 2026-09-12), trimmed to the fields normalize() actually reads.
    mock_raw_data = {
        "id": "t3_1wdei3c",
        "title": "Godrej Plots Coimbatore: A Closer Look at Plot Suitability",
        "url": "https://www.reddit.com/r/RealestatesPosting/comments/1wdei3c/godrej_plots_coimbatore_a_closer_look_at_plot/",
        "link": "https://www.reddit.com/r/RealestatesPosting/comments/1wdei3c/godrej_plots_coimbatore_a_closer_look_at_plot/",
        "username": "realestate_02",
        "upVotes": 1,
        "upVoteRatio": 1,
        "numberOfComments": 1,
        "createdAt": "2026-09-11T12:11:28.698Z",
        "body": "Godrej Plots Coimbatore is one of the project that strategically located adjacent to Coimbatore Golf Club.",
        "communityName": "r/RealestatesPosting",
        "parsedCommunityName": "RealestatesPosting",
        "contentType": "multi_media",
        "dataType": "post",
    }

    normalized = adapter.normalize(mock_raw_data, "test_source_id")

    assert normalized["title"] == "Godrej Plots Coimbatore: A Closer Look at Plot Suitability"
    assert "Coimbatore Golf Club" in normalized["content"]
    assert normalized["url"] == mock_raw_data["url"]
    assert normalized["source_id"] == "test_source_id"
    assert normalized["source_type"] == "reddit"
    assert normalized["author"] == "realestate_02"
    assert normalized["view_count"] == 1
    assert normalized["comment_count"] == 1


def test_reddit_apify_adapter_normalize_falls_back_to_link_without_url():
    adapter = RedditApifyAdapter()

    mock_raw_data = {
        "title": "No url field on this one",
        "link": "https://www.reddit.com/r/test/comments/abc/",
        "body": "content",
        "username": "someone",
    }

    normalized = adapter.normalize(mock_raw_data, "test_source_id")

    assert normalized["url"] == "https://www.reddit.com/r/test/comments/abc/"
    assert normalized["view_count"] is None
    assert normalized["comment_count"] is None


def test_reddit_apify_adapter_unavailable_without_api_token(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    adapter = RedditApifyAdapter()

    assert adapter.available is False
    results, cursor = adapter.search("anything")
    assert results == []
    assert cursor is None


def test_reddit_apify_adapter_search_caps_results_at_max_per_call(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return []

    def fake_post(url, params=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("app.adapters.reddit_apify.requests.post", fake_post)

    adapter.search("Godrej Properties", limit=9999)

    assert captured["json"]["maxItems"] == MAX_RESULTS_PER_CALL
    assert captured["json"]["maxPostCount"] == MAX_RESULTS_PER_CALL
    assert captured["json"]["searches"] == ["Godrej Properties"]
