"""Helpers for the JSON explainability blobs stored on risk events and alerts."""
from typing import Any


def strip_trend_keys(obj: Any) -> Any:
    """Copy of `obj` without any dict key containing "trend" (any case, any depth).

    Trend detection was removed from scoring (2026-10-01), but explainability
    stored by the old formula -- and merged forward on later re-scores -- still
    carries keys like `trend_contribution` and `individual_weights.trend_weight`.
    The stored rows are NOT edited; this is applied where stored explainability
    leaves the system: the documents API and the inputs of the AI-summary prompt.

    Returns new dicts/lists (the input, e.g. a live SQLAlchemy JSON value, is
    never mutated). Only keys are filtered; string values are left as they are.
    """
    if isinstance(obj, dict):
        return {k: strip_trend_keys(v) for k, v in obj.items() if "trend" not in str(k).lower()}
    if isinstance(obj, (list, tuple)):
        return [strip_trend_keys(v) for v in obj]
    return obj
