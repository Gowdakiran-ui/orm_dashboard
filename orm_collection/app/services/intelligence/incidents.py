"""
Group risk items that report the same story into one incident.

Pure functions, computed when the risk summary is read (nothing is stored, so it can never go stale).

Two items are the same incident when they belong to the same entity, were published within MAX_GAP_DAYS of each other and
either (a) their `event` phrases (the short English "who did what" the case-status call returns, so a Hindi and an English
headline of one story agree) overlap enough, or (b) their headlines share enough distinctive words. Links chain: A~B and
B~C put A, B and C in one incident.
"""
import re
from difflib import SequenceMatcher
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

MAX_GAP_DAYS = 45
EVENT_JACCARD_MIN = 0.5
EVENT_SHARED_MIN = 3
EVENT_OVERLAP_MIN = 0.6
TITLE_SHARED_MIN = 4
TITLE_OVERLAP_MIN = 0.5
ENTITY_WORD_RATIO = 0.8

_STOP = frozenset(
    "a an the of in on at to for and or as by with from over after amid into about against its his her their is are was were be "
    "has have had says said say new news report reports reportedly case cases india indian company companies group ltd limited "
    "pvt private properties what why how who which that this these those here there more than also not no".split()
)
# Words that name the same move in different headlines.
_CANON = {
    "chargesheets": "chargesheet", "chargesheeted": "chargesheet", "charges": "chargesheet", "charged": "chargesheet",
    "charge": "chargesheet", "chargesheet": "chargesheet",
    "raids": "raid", "raided": "raid", "searches": "raid", "searched": "raid", "search": "raid", "raid": "raid",
    "probes": "probe", "probed": "probe", "probing": "probe", "investigation": "probe", "investigates": "probe",
    "investigating": "probe", "probe": "probe",
    "fined": "fine", "fines": "fine", "penalty": "fine", "penalised": "fine", "penalized": "fine", "slaps": "fine",
    "settles": "settle", "settled": "settle", "settlement": "settle",
    "ed": "ed", "enforcement": "ed",
    "cgrera": "rera", "maharera": "rera", "rera": "rera",
    "accuses": "allege", "alleges": "allege", "alleged": "allege", "allegation": "allege", "allegations": "allege",
    "claim": "allege", "claims": "allege", "accused": "allege",
    "chinese": "china", "link": "link", "links": "link", "ties": "link", "tie": "link", "linked": "link",
    "ads": "advertisement", "advert": "advertisement", "advertising": "advertisement", "advertisements": "advertisement",
    "arrested": "arrest", "arrests": "arrest",
}


def outlet_of(title: Optional[str]) -> Optional[str]:
    """Google News convention: '<headline> - <Outlet>'. None when the title has no such suffix."""
    if not title or " - " not in title:
        return None
    tail = title.rsplit(" - ", 1)[1].strip()
    return tail.lower() or None if len(tail) <= 40 else None


def _strip_outlet(title: str) -> str:
    if " - " in title:
        head, tail = title.rsplit(" - ", 1)
        if len(tail.strip()) <= 40:
            return head
    return title


def _words(text: str) -> Set[str]:
    out: Set[str] = set()
    for w in re.findall(r"\w+", text.lower()):
        w = _CANON.get(w, w)
        if w in _STOP or (len(w) < 3 and not w.isdigit()):
            continue
        if len(w) > 4 and w.endswith("s") and w not in _CANON:
            w = w[:-1]
        out.add(w)
    return out


def _drop_entity_words(words: Set[str], entity_name: Optional[str]) -> Set[str]:
    """The entity is the same for every item compared, so its name (in any spelling, e.g. EaseMyTrip / easytrip) says nothing."""
    if not entity_name:
        return words
    names = [w for w in re.findall(r"\w+", entity_name.lower()) if len(w) >= 4]
    names.append("".join(re.findall(r"\w+", entity_name.lower())))
    return {w for w in words if not any(SequenceMatcher(None, w, n).ratio() >= ENTITY_WORD_RATIO for n in names)}


def title_tokens(title: Optional[str], entity_name: Optional[str] = None) -> Set[str]:
    return _drop_entity_words(_words(_strip_outlet(title or "")), entity_name)


def event_tokens(event: Optional[str], entity_name: Optional[str] = None) -> Set[str]:
    return _drop_entity_words(_words(event or ""), entity_name)


def _jaccard(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def same_story(a: Dict[str, Any], b: Dict[str, Any], ta: Set[str], tb: Set[str], ea: Set[str], eb: Set[str]) -> bool:
    if a.get("entity_id") != b.get("entity_id"):
        return False
    pa, pb = a.get("published_at"), b.get("published_at")
    if isinstance(pa, datetime) and isinstance(pb, datetime):
        try:
            if abs((pa - pb).total_seconds()) > MAX_GAP_DAYS * 86400:
                return False
        except TypeError:           # naive vs aware: cannot compare, so do not use the date
            pass
    if ea and eb:
        shared_e = len(ea & eb)
        if _jaccard(ea, eb) >= EVENT_JACCARD_MIN or (shared_e >= EVENT_SHARED_MIN and shared_e / min(len(ea), len(eb)) >= EVENT_OVERLAP_MIN):
            return True
    shared = len(ta & tb)
    return bool(ta and tb and shared >= TITLE_SHARED_MIN and shared / min(len(ta), len(tb)) >= TITLE_OVERLAP_MIN)


def group_incidents(items: List[Dict[str, Any]]) -> List[List[int]]:
    """Index groups over `items` (each: entity_id, entity_name, title, published_at, event). Every item is in exactly one group;
    groups come back largest first, then by first index, members in input order."""
    n = len(items)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tt = [title_tokens(it.get("title"), it.get("entity_name")) for it in items]
    et = [event_tokens(it.get("event"), it.get("entity_name")) for it in items]
    for i in range(n):
        for j in range(i + 1, n):
            if find(i) != find(j) and same_story(items[i], items[j], tt[i], tt[j], et[i], et[j]):
                parent[find(j)] = find(i)
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: (-len(g), g[0]))
