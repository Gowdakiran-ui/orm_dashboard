import pytest
from app.adapters.instagram import InstagramAdapter, MAX_RESULTS_PER_CALL


def test_instagram_adapter_normalize():
    adapter = InstagramAdapter()

    # Shape confirmed against a real apify/instagram-scraper API response
    # (directUrls=[".../explore/tags/godrejproperties/"], resultsType=posts),
    # trimmed to the fields normalize() actually reads.
    mock_raw_data = {
        "id": "3984462685500152959",
        "shortCode": "DdLp7OuCRx_",
        "caption": "Godrej Properties has settled its dispute over the Godrej Air project.",
        "url": "https://www.instagram.com/p/DdLp7OuCRx_/",
        "commentsCount": 0,
        "likesCount": 22,
        "timestamp": "2026-09-12T09:23:07.000Z",
        "ownerFullName": "Manish Kumar",
        "ownerUsername": "propertywithmanish",
    }

    normalized = adapter.normalize(mock_raw_data, "test_source_id")

    assert normalized["title"] == ""
    assert normalized["content"] == "Godrej Properties has settled its dispute over the Godrej Air project."
    assert normalized["url"] == "https://www.instagram.com/p/DdLp7OuCRx_/"
    assert normalized["source_id"] == "test_source_id"
    assert normalized["source_type"] == "instagram"
    assert normalized["author"] == "propertywithmanish"
    assert normalized["comment_count"] == 0
    assert normalized["view_count"] is None


def test_instagram_adapter_normalize_reel_maps_play_count_to_view_count():
    adapter = InstagramAdapter()

    # Reels (productType "clips") are a distinct post type from the image
    # posts test_instagram_adapter_normalize above uses, and carry a real
    # play/view count that image posts don't (confirmed against
    # apify/instagram-scraper's documented Reel-mode output fields).
    mock_raw_data = {
        "caption": "Reel about Godrej Properties",
        "url": "https://www.instagram.com/reel/abc123/",
        "commentsCount": 3,
        "playCount": 5400,
        "ownerUsername": "someaccount",
    }

    normalized = adapter.normalize(mock_raw_data, "test_source_id")

    assert normalized["view_count"] == 5400
    assert normalized["comment_count"] == 3


def test_instagram_adapter_normalize_falls_back_to_full_name_without_username():
    adapter = InstagramAdapter()

    mock_raw_data = {
        "caption": "No username on this one",
        "url": "https://www.instagram.com/p/abc/",
        "ownerFullName": "Some Brand",
        "ownerUsername": "",
    }

    normalized = adapter.normalize(mock_raw_data, "test_source_id")

    assert normalized["author"] == "Some Brand"


def test_instagram_adapter_unavailable_without_api_token(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    adapter = InstagramAdapter()

    assert adapter.available is False
    results, cursor = adapter.search("anything")
    assert results == []
    assert cursor is None


def test_instagram_adapter_search_caps_results_at_max_per_call(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = InstagramAdapter()

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return []

    def fake_post(url, params=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("app.adapters.instagram.requests.post", fake_post)

    adapter.search("Godrej Properties", limit=9999)

    assert captured["json"]["resultsLimit"] == MAX_RESULTS_PER_CALL
    assert captured["json"]["directUrls"] == ["https://www.instagram.com/explore/tags/godrejproperties/"]
