"""Builds the set of (kind, entity, query-per-source) the backfill walks for one client."""
from dataclasses import dataclass, field
from typing import List, Optional

RISK_TERMS = ("complaint", "RERA", "court", "refund", "fraud", "probe", "lawsuit", "protest")


@dataclass
class QuerySpec:
    kind: str                    # brand | executive | risk | competitor | product
    entity_id: Optional[str]
    entity_name: str
    google_news: str
    youtube: str
    gdelt: str
    hn: str


def _q(s: str) -> str:
    return '"' + s.replace('"', " ").strip() + '"'


def build_queries(db, client_id, include_competitors: bool = False, include_products: bool = False,
                  exclude_entity_names: Optional[List[str]] = None) -> List[QuerySpec]:
    from app.models.entity import Entity
    excl = {n.lower() for n in (exclude_entity_names or [])}
    ents = db.query(Entity).filter(Entity.client_id == client_id).order_by(Entity.name).all()
    brand = next((e for e in ents if e.entity_type == "brand"), None)
    if not brand:
        return []
    specs: List[QuerySpec] = []
    b = _q(brand.name)
    specs.append(QuerySpec("brand", str(brand.id), brand.name, b, b, b, brand.name))

    risk_or = " OR ".join(RISK_TERMS)
    specs.append(QuerySpec(
        "risk", str(brand.id), brand.name,
        f"{b} ({risk_or})",
        f"{b} " + "|".join(RISK_TERMS),   # YouTube treats | as OR
        f"{b} (" + " OR ".join(RISK_TERMS) + ")",
        "",  # HN search is not boolean; a risk-word query adds noise, so risk is skipped for HN
    ))

    for e in ents:
        if e.name.lower() in excl:
            continue
        et = (e.entity_type or "").lower()
        if et == "person":
            # person names are always paired with the brand so a same-name stranger never matches
            pair = f"{_q(e.name)} {b}"
            specs.append(QuerySpec("executive", str(e.id), e.name, pair, pair, pair, f"{e.name} {brand.name}"))
        elif et == "competitor" and include_competitors:
            c = _q(e.name)
            specs.append(QuerySpec("competitor", str(e.id), e.name, c, c, c, e.name))
        elif et == "product" and include_products:
            pair = f"{_q(e.name)} {b}"
            specs.append(QuerySpec("product", str(e.id), e.name, pair, pair, pair, f"{e.name} {brand.name}"))
    return specs
