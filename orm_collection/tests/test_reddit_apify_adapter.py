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


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _fake_apify(monkeypatch, dataset_items):
    """Mock Apify's real async flow: POST /acts/{id}/runs -> {"data": {...}},
    GET /actor-runs/{id} while running, GET /datasets/{id}/items -> JSON array."""
    captured = {"posts": [], "gets": []}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["posts"].append(json)
        return _FakeResponse({"data": {"id": "run1", "status": "READY", "defaultDatasetId": "ds1"}})

    def fake_get(url, params=None, timeout=None):
        captured["gets"].append(url)
        if "/datasets/" in url:
            return _FakeResponse(dataset_items)
        return _FakeResponse({"data": {"id": "run1", "status": "SUCCEEDED", "defaultDatasetId": "ds1"}})

    monkeypatch.setattr("app.adapters.reddit_apify.requests.post", fake_post)
    monkeypatch.setattr("app.adapters.reddit_apify.requests.get", fake_get)
    monkeypatch.setattr("app.adapters.reddit_apify.time.sleep", lambda s: None)
    return captured


def test_reddit_apify_adapter_search_caps_results_at_max_per_call(monkeypatch):
    # Stale before: this mocked a single POST returning a bare list (an older
    # one-call Apify endpoint). The adapter starts an async run, polls it, then
    # reads the dataset, so the mock now follows that lifecycle.
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    captured = _fake_apify(monkeypatch, [])

    adapter.search("Godrej Properties", limit=9999)

    assert captured["posts"][0]["maxItems"] == MAX_RESULTS_PER_CALL
    assert captured["posts"][0]["maxPostCount"] == MAX_RESULTS_PER_CALL
    # The phrase is quoted so Reddit's search matches it literally; unquoted it
    # is fuzzy and returns unrelated posts when a brand has little Reddit chatter.
    assert captured["posts"][0]["searches"] == ['"Godrej Properties"']


def test_reddit_apify_adapter_search_returns_dataset_items_from_real_response_shape(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    items = [{"id": "t3_1", "title": "a post about Godrej Properties", "body": "text", "url": "https://www.reddit.com/r/x/comments/1/"}]
    captured = _fake_apify(monkeypatch, items)

    results, cursor = adapter.search("Godrej Properties", limit=5)

    assert results == items and cursor is None
    assert any("/datasets/ds1/items" in u for u in captured["gets"])


def test_reddit_apify_adapter_search_fails_loudly_when_run_does_not_succeed(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    monkeypatch.setattr("app.adapters.reddit_apify.requests.post",
                        lambda *a, **k: _FakeResponse({"data": {"id": "run1", "status": "FAILED", "defaultDatasetId": "ds1"}}))
    with pytest.raises(Exception, match="finished with status FAILED"):
        adapter.search("Godrej Properties", limit=5)


# ---------------------------------------------------------------------------
# Quoted phrase + off-topic filter (Reddit's unquoted search is fuzzy: a live
# EaseMyTrip run returned 22 posts, none mentioning the brand).
# ---------------------------------------------------------------------------

def test_search_sends_the_keyword_as_a_quoted_phrase(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    captured = _fake_apify(monkeypatch, [])

    adapter.search("EaseMyTrip")

    assert captured["posts"][0]["searches"] == ['"EaseMyTrip"']


def test_search_strips_quotes_already_inside_the_keyword(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    captured = _fake_apify(monkeypatch, [])

    adapter.search('Ease "My"  Trip')

    assert captured["posts"][0]["searches"] == ['"Ease My Trip"']


def _post(**over):
    base = {"id": "t3_x", "title": "", "body": "", "url": "https://www.reddit.com/r/x/comments/1/slug/", "link": "https://i.redd.it/a.png"}
    base.update(over)
    return base


def test_keeps_a_post_that_mentions_the_keyword_in_any_one_field_case_insensitively(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    in_title = _post(id="title", title="[H] EASEMYTRIP voucher worth 3k")
    in_body = _post(id="body", body="anyone used easemytrip for flights?")
    in_url = _post(id="url", url="https://www.reddit.com/r/x/comments/1/h_easemytrip_voucher_worth_3k/")
    in_link = _post(id="link", link="https://www.easemytrip.com/offer")
    in_flair = _post(id="flair", flair="EaseMyTrip deals")
    in_flair_text = _post(id="flairtext", linkFlairText="EaseMyTrip")
    _fake_apify(monkeypatch, [in_title, in_body, in_url, in_link, in_flair, in_flair_text])

    results, cursor = adapter.search("EaseMyTrip")

    assert [r["id"] for r in results] == ["title", "body", "url", "link", "flair", "flairtext"]
    assert cursor is None


def test_drops_a_post_that_mentions_the_keyword_nowhere(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    junk = [
        _post(id="trip", title="2 week Vietnam Itinerary check / 15 days", body="planning a trip"),
        _post(id="image_only", title="Selling some coupons...DM if interested", body=""),
        _post(id="empty", title=None, body=None, url=None, link=None),
    ]
    _fake_apify(monkeypatch, junk)

    results, _ = adapter.search("EaseMyTrip")

    assert results == []


def test_multi_word_keyword_needs_the_whole_phrase_and_matches_a_slugged_url(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    items = [
        _post(id="whole", title="Godrej Properties Q1 results"),
        _post(id="slug", url="https://www.reddit.com/r/thane/comments/1/godrej_properties_manpada/"),
        _post(id="one_word_only", title="Godrej appliances sale", body="best price on properties"),
        _post(id="other_words", title="Properties of a Godrej lock"),
    ]
    _fake_apify(monkeypatch, items)

    results, _ = adapter.search("Godrej Properties")

    assert [r["id"] for r in results] == ["whole", "slug"]


def test_keyword_must_match_whole_words_not_a_fragment_of_a_longer_word(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    items = [_post(id="longer", title="easemytripper is not the brand"), _post(id="hash", title="loving #EaseMyTrip's app"), _post(id="domain", body="see easemytrip.com")]
    _fake_apify(monkeypatch, items)

    results, _ = adapter.search("EaseMyTrip")

    assert [r["id"] for r in results] == ["hash", "domain"]


def test_real_easemytrip_test_run_shape_keeps_the_three_text_mentions_and_drops_the_two_image_posts(monkeypatch):
    # Shapes taken from a real 5-result run (2026-10-08): two image posts
    # (i.redd.it) carry no brand text in any field the actor returns.
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy_token")
    adapter = RedditApifyAdapter()
    items = [
        _post(id="a", title="Rupay Debit Card Lounge Access Not Refreshed this Quarter", body="I have an Easemytrip voucher"),
        _post(id="b", title="Would've this been released in today's time considering everything", link="https://i.redd.it/xvw2hzrq4ush1.jpeg"),
        _post(id="c", title="selling some coupons/discount codes", body="easemytrip coupons"),
        _post(id="d", title="Selling some coupons...DM if interested", link="https://i.redd.it/7kesi9b0btsh1.png"),
        _post(id="e", title="[H] Easemytrip voucher worth 3k [W] 2.5k UPI"),
    ]
    _fake_apify(monkeypatch, items)

    results, _ = adapter.search("EaseMyTrip", limit=5)

    assert [r["id"] for r in results] == ["a", "c", "e"]
