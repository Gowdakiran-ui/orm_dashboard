import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.adapters import youtube as youtube_module
from app.adapters.youtube import (
    YouTubeAdapter,
    YouTubeQuotaExhaustedError,
    YouTubeCircuitBreakerOpenError,
    _reserve_search_quota,
    _check_circuit_breaker,
    _record_api_failure_4xx,
    DAILY_QUOTA_LIMIT,
    SEARCH_LIST_COST,
    CIRCUIT_BREAKER_THRESHOLD,
)


@pytest.fixture
def fake_redis():
    """
    In-memory stand-in for redis_client covering exactly the methods
    youtube.py calls (incrby/get/set/delete/client.expire). Real INCRBY
    semantics (atomic add-and-return-new-total) so the reserve-then-check
    math in _reserve_search_quota is exercised faithfully.
    """
    store = {}

    fake = MagicMock()

    def incrby(key, amount=1):
        store[key] = store.get(key, 0) + amount
        return store[key]

    fake.incrby.side_effect = incrby
    fake.get.side_effect = lambda key: store.get(key)
    fake.set.side_effect = lambda key, value, *a, **kw: store.__setitem__(key, value)
    fake.delete.side_effect = lambda key: store.pop(key, None)
    fake.client.expire = MagicMock()

    with patch.object(youtube_module, "redis_client", fake):
        yield fake, store


def test_reserve_search_quota_increments_by_cost(fake_redis):
    fake, store = fake_redis
    total = _reserve_search_quota()
    assert total == SEARCH_LIST_COST
    assert store[youtube_module._quota_key()] == SEARCH_LIST_COST


def test_reserve_search_quota_raises_and_compensates_when_exhausted(fake_redis):
    fake, store = fake_redis
    key = youtube_module._quota_key()
    store[key] = DAILY_QUOTA_LIMIT - 50  # only 50 units left, next call needs 100

    with pytest.raises(YouTubeQuotaExhaustedError):
        _reserve_search_quota()

    # Compensated back to the pre-reservation total, not left over-budget.
    assert store[key] == DAILY_QUOTA_LIMIT - 50


def test_reserve_search_quota_allows_exact_limit(fake_redis):
    fake, store = fake_redis
    key = youtube_module._quota_key()
    store[key] = DAILY_QUOTA_LIMIT - SEARCH_LIST_COST

    total = _reserve_search_quota()
    assert total == DAILY_QUOTA_LIMIT


def test_circuit_breaker_trips_after_threshold_consecutive_4xx(fake_redis):
    fake, store = fake_redis

    for _ in range(CIRCUIT_BREAKER_THRESHOLD - 1):
        _record_api_failure_4xx(429)
        _check_circuit_breaker()  # should not raise yet

    _record_api_failure_4xx(429)  # the Nth failure trips it

    with pytest.raises(YouTubeCircuitBreakerOpenError):
        _check_circuit_breaker()

    assert youtube_module._COOLDOWN_KEY in store
    # Consecutive-failure counter resets once tripped, ready for next window.
    assert youtube_module._CIRCUIT_BREAKER_KEY not in store


def test_circuit_breaker_resets_on_success(fake_redis):
    fake, store = fake_redis

    _record_api_failure_4xx(403)
    _record_api_failure_4xx(403)
    youtube_module._record_api_success()

    assert youtube_module._CIRCUIT_BREAKER_KEY not in store
    _check_circuit_breaker()  # does not raise


def test_circuit_breaker_cooldown_expires(fake_redis):
    fake, store = fake_redis
    # Cooldown already in the past -- should not block.
    store[youtube_module._COOLDOWN_KEY] = (datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()
    _check_circuit_breaker()  # does not raise


def test_search_skips_cleanly_when_adapter_unavailable(monkeypatch, fake_redis):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    adapter = YouTubeAdapter()
    results, cursor = adapter.search("acme", cursor=None)
    assert results == []
    assert cursor is None


def test_search_raises_quota_exhausted_before_calling_api(monkeypatch, fake_redis):
    fake, store = fake_redis
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key-for-test")
    store[youtube_module._quota_key()] = DAILY_QUOTA_LIMIT  # already at the ceiling

    with patch.object(youtube_module, "build") as mock_build:
        adapter = YouTubeAdapter()
        with pytest.raises(YouTubeQuotaExhaustedError):
            adapter.search("acme", cursor=None)
        # The actual YouTube client must never be invoked once quota is exhausted.
        mock_build.return_value.search.assert_not_called()


def test_search_raises_circuit_breaker_open_before_calling_api(monkeypatch, fake_redis):
    fake, store = fake_redis
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key-for-test")
    store[youtube_module._COOLDOWN_KEY] = (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()

    with patch.object(youtube_module, "build") as mock_build:
        adapter = YouTubeAdapter()
        with pytest.raises(YouTubeCircuitBreakerOpenError):
            adapter.search("acme", cursor=None)
        mock_build.return_value.search.assert_not_called()
