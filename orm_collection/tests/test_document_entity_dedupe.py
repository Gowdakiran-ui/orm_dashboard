"""A document's Mentioned Targets listed the same entity several times
(entity_mentions has duplicate rows for one (document, entity) pair). The
endpoints now collapse them. Pure-function test: no database is touched, and
DATABASE_URL is forced to an unreachable dummy so an accidental SessionLocal()
use could never reach production.
"""
import os
import sys
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.endpoints.documents import _unique_mentions


def m(doc, ent, name="N"):
    return SimpleNamespace(document_id=doc, entity_id=ent, entity=SimpleNamespace(name=name))


def test_duplicate_rows_for_the_same_document_and_entity_collapse_to_one_in_first_seen_order():
    rows = [m("d1", "gautam", "Gautam Adani"), m("d1", "pranav", "Pranav Adani"), m("d1", "gautam", "Gautam Adani"), m("d1", "gautam", "Gautam Adani")]
    out = _unique_mentions(rows)
    assert [r.entity_id for r in out] == ["gautam", "pranav"]
    assert out[0] is rows[0]


def test_the_same_entity_on_a_different_document_is_kept():
    rows = [m("d1", "gautam"), m("d2", "gautam"), m("d2", "gautam")]
    assert [(r.document_id, r.entity_id) for r in _unique_mentions(rows)] == [("d1", "gautam"), ("d2", "gautam")]


def test_two_different_entities_that_share_a_name_are_not_merged():
    rows = [m("d1", "e1", "Same Name"), m("d1", "e2", "Same Name")]
    assert len(_unique_mentions(rows)) == 2


def test_empty_input():
    assert _unique_mentions([]) == []
