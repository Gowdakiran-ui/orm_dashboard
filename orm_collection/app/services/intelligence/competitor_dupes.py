"""
Duplicate competitors in the benchmark view.

A client's tracked competitors can include two entities for the same company under different names (Godrej: the seeded "Prestige Group"
and an older, unseeded "Prestige Estates"), so one company is counted twice in the ranking and in share of voice. When a SEEDED
competitor exists, an unseeded competitor with the same name apart from generic company words is hidden from the benchmark view. The entity
itself is kept (nothing is deleted, merged or re-typed), and the seeded one always stays.

The key drops generic words (group, estates, limited, india, holdings ...) and a plural s, so "Prestige Group" and "Prestige Estates" both
reduce to "prestige". It is deliberately strict about everything else: "Tata Projects" and "Tata Motors" do not match, and two unseeded
entities are never hidden against each other (they are only reported by duplicate_groups, for a person to decide).
"""
import re
from typing import Dict, Iterable, List, Sequence, Set, Tuple

GENERIC = frozenset({
    "group", "groups", "estate", "estates", "limited", "ltd", "pvt", "private", "inc", "incorporated", "corp", "corporation", "company",
    "co", "llc", "llp", "plc", "the", "and", "of", "holdings", "holding", "india", "indian",
})


def name_key(name: str) -> Tuple[str, ...]:
    """The words of a company name that identify it, lower-cased, generic company words and a plural 's' removed. () for nothing usable."""
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower())]
    kept = []
    for w in words:
        if w in GENERIC:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        kept.append(w)
    return tuple(kept)


def hidden_duplicates(entities: Iterable[Tuple[object, str]], seeded_ids: Set[object]) -> Set[object]:
    """Ids of unseeded entities whose name key equals the key of a seeded entity in the same list. entities: (entity_id, name) pairs."""
    pairs = list(entities)
    seeded_keys = {name_key(n) for i, n in pairs if i in seeded_ids and name_key(n)}
    return {i for i, n in pairs if i not in seeded_ids and name_key(n) and name_key(n) in seeded_keys}


def duplicate_groups(names: Sequence[str]) -> List[List[str]]:
    """Groups of two or more names with the same key (for a report; nothing is hidden on this basis)."""
    by_key: Dict[Tuple[str, ...], List[str]] = {}
    for n in names:
        k = name_key(n)
        if k:
            by_key.setdefault(k, []).append(n)
    return [v for v in by_key.values() if len(v) > 1]
