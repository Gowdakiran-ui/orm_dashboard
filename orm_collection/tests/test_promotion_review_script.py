"""scripts/list_promotion_candidates.py is the human review list for the switched-off executive auto-promotion. It must stay read-only."""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = open(os.path.join(ROOT, "scripts", "list_promotion_candidates.py"), encoding="utf-8").read()
CODE = re.sub(r'"""[\s\S]*?"""', "", SRC)


def test_script_runs_in_a_read_only_transaction_and_never_commits():
    assert 'SET TRANSACTION READ ONLY' in CODE
    assert ".commit(" not in CODE and ".add(" not in CODE and ".flush(" not in CODE


def test_script_has_no_write_sql():
    assert not re.search(r"\b(insert\s+into|update\s+\w+\s+set|delete\s+from|drop\s+table|alter\s+table)\b", CODE, re.I)


def test_script_is_the_documented_review_path():
    assert "EXECUTIVE_AUTO_PROMOTION_ENABLED" in CODE and "track executive" in SRC
