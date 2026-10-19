"""Onboarding keyword variants: name without legal suffixes (new clients only)."""
import pytest
from app.services.keyword_service import strip_legal_suffix, generate_keywords_for_entity


@pytest.mark.parametrize("name,expected", [
    ("Sobha Limited", "Sobha"),
    ("Brigade Enterprises", "Brigade"),
    ("Tata Motors Limited", "Tata Motors"),
    ("Godrej Properties Limited", "Godrej Properties"),
    ("Infosys Pvt. Ltd.", "Infosys"),
    ("Adani Group", None),            # "Group" is not a legal form
    ("Ola Pvt Ltd", None),            # "Ola" < 4 chars
    ("Incredible India", None),       # old substring check mangled this
    ("Apple Inc", "Apple"),
    ("Limited", None),
])
def test_strip_legal_suffix(name, expected):
    assert strip_legal_suffix(name) == expected


class _FakeDB:
    def add_all(self, rows): self.rows = rows
    def commit(self): pass


def test_generate_keywords_adds_variants_only_when_stripped():
    db = _FakeDB()
    kws = generate_keywords_for_entity(db, "e1", "Ease My Trip Limited")
    texts = {k.keyword_text for k in kws}
    assert {"Ease My Trip", "EaseMyTrip"} <= texts and "Ease My Trip Limited" in texts
    kws = generate_keywords_for_entity(db, "e1", "Adani Group")
    assert {k.keyword_text for k in kws if k.category == "ALIAS"} == {"adani group", "AdaniGroup"}
