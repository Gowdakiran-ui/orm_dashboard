"""Pure date-slice helpers (no I/O)."""
import datetime as dt
from typing import List, Optional, Tuple

Slice = Tuple[dt.date, dt.date]  # half-open [start, end)


def _add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.year * 12 + (d.month - 1) + months, 12)
    return dt.date(y, m + 1, 1)


def calendar_slices(start: dt.date, end: dt.date, months: int) -> List[Slice]:
    """
    Calendar-aligned slices of `months` months covering [start, end).
    The first slice begins at `start`; the last is clipped to `end`.
    months=1 -> monthly, 3 -> quarterly, 12 -> yearly.
    """
    if start >= end:
        return []
    out: List[Slice] = []
    cur = start
    while cur < end:
        # align to the next boundary that is a multiple of `months` from the year start
        anchor = dt.date(cur.year, 1, 1)
        offset = ((cur.year * 12 + cur.month - 1) - (anchor.year * 12)) // months
        nxt = _add_months(anchor, (offset + 1) * months)
        out.append((cur, min(nxt, end)))
        cur = nxt
    return out


def fixed_day_slices(start: dt.date, end: dt.date, days: int) -> List[Slice]:
    out: List[Slice] = []
    cur = start
    while cur < end:
        nxt = min(cur + dt.timedelta(days=days), end)
        out.append((cur, nxt))
        cur = nxt
    return out


def split_slice(s: Slice) -> Optional[Tuple[Slice, Slice]]:
    """
    Split a slice into two halves at the day midpoint. Returns None when the
    slice is already a single day (cannot be split further).
    """
    start, end = s
    span = (end - start).days
    if span <= 1:
        return None
    mid = start + dt.timedelta(days=span // 2)
    return (start, mid), (mid, end)


def needs_split(item_count: int, cap: int) -> bool:
    """A slice that returned >= cap items may have been truncated by the source."""
    return item_count >= cap
