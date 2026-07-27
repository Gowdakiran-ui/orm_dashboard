import pytest
from app.services.matching_engine import GlobalMatchingEngine

def test_engine_initialization():
    engine = GlobalMatchingEngine()
    assert not engine.is_loaded

# Normally, here we'd set up an SQLite in-memory DB or similar to test the full 
# DB interaction: creating clients, entities, keywords, then refreshing the processor.
# For simplicity in this suite structure placeholder, we mock the db or run minimal asserts.
