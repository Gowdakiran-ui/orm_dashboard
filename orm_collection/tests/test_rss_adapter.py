import pytest
from app.adapters.rss import RSSAdapter
from app.schemas.document import NormalizedDocument

def test_rss_adapter_normalize():
    adapter = RSSAdapter()
    
    mock_raw_data = {
        "title": "Test Title",
        "link": "http://example.com/article",
        "summary": "This is a test summary.",
        "author": "Test Author"
    }
    
    normalized = adapter.normalize(mock_raw_data, "test_source_id")
    
    assert normalized["title"] == "Test Title"
    assert normalized["url"] == "http://example.com/article"
    assert normalized["content"] == "This is a test summary."
    assert normalized["source_id"] == "test_source_id"
    assert normalized["source_type"] == "rss"

# Further integration tests would require Celery testing tools (e.g. celery worker in eager mode)
# and a test database.
