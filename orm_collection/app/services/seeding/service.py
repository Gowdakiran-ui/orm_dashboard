"""
Seeding orchestration: propose (one web-grounded LLM call), validate every candidate, choose the top five of each BY RULE,
resolve aliases, and optionally apply.

Executives: role order first (chairperson, MD/CEO, CFO, founders, other management), validated news count second within a
slot; independent and non-executive directors only fill slots management leaves open. Competitors: valid peers only (see
validator.group_conflict / market_conflict), the five with the highest validated news count.

dry run  - proposes and validates, prints, writes nothing.
apply    - writes seeded_entities rows (selected -> active, failed validation -> needs_review), creates or links the Entity and its
           keywords, provisions the entity's three search feeds, sets the verified company website on the brand entity when
           it has none, and runs the seed-scoped rematch of the existing documents. The chosen list is PERSISTED: a second apply
           is refused until an explicit refresh. Existing tracked entities are never deleted; a seeded name that matches one is
           linked to it.
retire   - marks a seeded row retired and deactivates the feeds seeding provisioned for it. The entity is left in place.
"""
import datetime as dt
import uuid
from typing import Any, Callable, Dict, List, Optional

import structlog

from app.services.seeding import aliases as alias_mod
from app.services.seeding import proposer, validator

logger = structlog.get_logger()

core_name = validator.core_name


class AlreadySeeded(Exception):
    """The client already has an active seeded list; re-seeding needs an explicit refresh."""


def client_context(db, client_id) -> Dict[str, Any]:
    from app.models.client import Client
    from app.models.entity import Entity
    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        raise ValueError(f"Client {client_id} not found")
    brand = db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == "brand").first()
    domains = []
    for v in ((brand.domain if brand else None), (brand.website if brand else None)):
        if v:
            v = v.lower().replace("https://", "").replace("http://", "").split("/")[0]
            if v.startswith("www."):
                v = v[4:]
            if v and v not in domains:
                domains.append(v)
    return {"client": client, "name": (brand.name if brand else client.name), "brand": brand,
            "domains": domains, "industry": ((brand.industry if brand else None) or client.industry)}


def _slot_key(item: Dict[str, Any]):
    return (proposer.SLOT_ORDER.get(item.get("slot", "management"), 4), -(item["validation"].get("pair_count_24m") or 0), item["name"].lower())


def build_plan(db, client_id, propose_fn: Optional[Callable] = None, fetch: Optional[Callable] = None,
               measure_aliases: bool = True, today: Optional[dt.date] = None, fetch_text: Optional[Callable] = None,
               http_get: Optional[Callable] = None, retry_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Propose + validate + choose. Reads the DB (client context), makes the one paid call, writes nothing."""
    ctx = client_context(db, client_id)
    # The client's already-tracked competitors join the candidate pool and go through the same guards and the same news count.
    from app.models.entity import Entity
    tracked_names = [e.name for e in db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == "competitor").all()]
    proposal = (propose_fn or proposer.propose_multi)(ctx["name"], ctx["domains"][0] if ctx["domains"] else None, ctx["industry"],
                                                      tracked_competitors=tracked_names)
    company_info = proposal.get("company") or {}
    if not isinstance(company_info, dict):
        company_info = {}
    # Company website: only checked when the brand entity has none stored; a stored domain is authoritative.
    if ctx["domains"]:
        website = {"ok": True, "domain": ctx["domains"][0], "reason": "already stored on the brand entity", "stored": True}
        domains = list(ctx["domains"])
    else:
        website = validator.verify_website(company_info.get("website"), ctx["name"], http_get)
        domains = [website["domain"]] if website.get("ok") and website.get("domain") else []
    plan = {"client": ctx["name"], "client_id": str(client_id), "cost_usd": proposal.get("cost_usd"),
            "citations": proposal.get("citations", []), "model": proposal.get("model"),
            "company": {k: company_info.get(k) for k in ("website", "primary_market", "parent_company", "group_companies")},
            "website": website, "follow_up": proposal.get("follow_up"), "executives": [], "competitors": []}

    # ---- executives: validate every candidate, then choose by rule
    seen = set()
    execs = []
    for e in proposal["executives"]:
        key = core_name(e["name"])
        if key in seen:
            continue
        seen.add(key)
        v = validator.validate_executive(e, ctx["name"], domains, fetch, today, fetch_text)
        execs.append({"name": e["name"].strip(), "slot": e.get("slot", "management"), "role": (e.get("role") or "").strip(),
                      "reason": e.get("reason"), "confidence": e.get("confidence"), "raw_aliases": e.get("aliases"), "validation": v, "_raw": e})
    # ONE retry for people with 1-2 news items whose citations could not be read: ask for readable pages / a BSE-NSE transcript.
    rf = retry_fn or (proposer.source_retry if propose_fn is None else None)
    needs = [x for x in execs if x["validation"].get("needs_better_sources")]
    plan["retry"] = None
    if needs and rf is not None:
        answer = rf(ctx["name"], [{"name": x["name"], "role": x["role"]} for x in needs])
        urls_by = {}
        for p_ in answer.get("executives", []):
            urls_by.setdefault(core_name(p_["name"]), []).extend(p_.get("source_urls") or [])
        for x in needs:
            more = urls_by.get(core_name(x["name"]), [])
            if more:
                raw = dict(x["_raw"])
                raw["source_urls"] = list(dict.fromkeys(list(raw.get("source_urls") or []) + list(more)))
                x["validation"] = {**validator.validate_executive(raw, ctx["name"], domains, fetch, today, fetch_text), "retried": True}
        plan["retry"] = {"asked": [x["name"] for x in needs], "cost_usd": answer.get("cost_usd")}
        if answer.get("cost_usd"):
            plan["cost_usd"] = (plan.get("cost_usd") or 0) + answer["cost_usd"]
    for x in execs:
        x.pop("_raw", None)
    chosen = sorted([x for x in execs if x["validation"]["accepted"]], key=_slot_key)[:proposer.MAX_EXECUTIVES]
    chosen_names = {x["name"] for x in chosen}
    for rank, x in enumerate(chosen, start=1):
        x["rank"], x["selected"] = rank, True
    others = [x for x in execs if x["name"] not in chosen_names]
    for j, x in enumerate(others, start=100):
        x["rank"], x["selected"] = j, False
        if x["validation"]["accepted"]:
            x["validation"] = {**x["validation"], "reason": x["validation"]["reason"] + "; accepted but not selected (five slots filled by role order)"}
    for x in chosen + others:
        x["aliases"] = alias_mod.resolve_aliases(x["name"], x.pop("raw_aliases", None), "executive", [], measure_aliases and x["selected"], fetch, today)
    plan["executives"] = chosen + others

    # ---- competitors: validate every candidate, keep valid peers, top five by validated news count
    names = [c["name"].strip() for c in proposal["competitors"]]
    own_sources, withdrawn = {}, set()
    for ev in proposal.get("ownership_evidence") or []:
        key = _evidence_key(ev, names)
        own_sources.setdefault(key, []).extend(ev.get("source_urls") or [])
        if ev.get("still_owned") is False:
            withdrawn.add(key)
    cand_sources = {core_name(c["name"]): list(c.get("source_urls") or []) for c in proposal["competitors"]}
    comps = []
    for idx, c in enumerate(proposal["competitors"], start=1):
        if core_name(c["name"]) in withdrawn:
            c = {**c, "claim_withdrawn": True}
        v = validator.validate_competitor(c, fetch, today, company=ctx["name"], company_info=company_info, other_candidates=names,
                                          fetch_text=fetch_text, ownership_sources=own_sources, candidate_sources=cand_sources)
        context = (c.get("context_term") or "").strip()
        comps.append({"name": c["name"].strip(), "role": (c.get("reason") or "").strip(), "context_term": context,
                      "confidence": c.get("confidence"), "raw_aliases": c.get("aliases"), "validation": v,
                      "hq_country": c.get("hq_country"), "parent_company": c.get("parent_company"),
                      "tracked": any(validator.same_company(t, c["name"]) for t in tracked_names),
                      "seen_in": c.get("seen_in") or 1, "positions": c.get("positions") or [idx], "answers": proposal.get("calls") or 1})
    # valid peers (every guard + sector count >= 20), top five by: already tracked, number of answers that name the company, the model's
    # own position, then news count. The exchange-listed flag is a label only.
    chosen_c = validator.rank_competitors([x for x in comps if x["validation"]["accepted"]])[:proposer.MAX_COMPETITORS]
    chosen_names = {x["name"] for x in chosen_c}
    for rank, x in enumerate(chosen_c, start=1):
        x["rank"], x["selected"] = rank, True
    others = [x for x in comps if x["name"] not in chosen_names]
    for j, x in enumerate(others, start=100):
        x["rank"], x["selected"] = j, False
        if x["validation"]["accepted"]:
            x["validation"] = {**x["validation"], "reason": x["validation"]["reason"] + "; valid peer but not in the top five (tracked, then answers naming it, then model position, then news count)"}
    for x in chosen_c + others:
        ctxs = [x["context_term"]] if x["context_term"] else []
        x["aliases"] = alias_mod.resolve_aliases(x["name"], x.pop("raw_aliases", None), "competitor", ctxs, measure_aliases and x["selected"], fetch, today)
    plan["competitors"] = chosen_c + others
    return plan


def summary_lines(plan: Dict[str, Any]) -> List[str]:
    """One line per chosen executive / competitor: name | role | source URL | Google News count (24 months) | verification method;
    then every candidate that was not chosen with its reason."""
    lines = []
    for title, key in (("EXECUTIVES", "executives"), ("COMPETITORS", "competitors")):
        lines.append(f"{title} - chosen")
        for it in [x for x in plan[key] if x.get("selected")]:
            v = it["validation"]
            url = v.get("verified_page") or (v.get("sources") or ["-"])[0]
            role = it.get("role") if key == "executives" else (it.get("context_term") or "")
            tag = (" [already tracked]" if it.get("tracked") else "") + (" [listed per model]" if v.get("listed") else "")
            if key == "competitors" and it.get("seen_in") is not None:
                tag += f" [named in {it['seen_in']} of {it.get('answers')} answers, mean position {sum(it['positions']) / len(it['positions']):.1f}]"
            note = ("  NOTE: " + "; ".join(v["notes"])) if v.get("notes") else ""
            more = f" (+{len(v['verified_pages']) - 1} more verifying page(s))" if len(v.get("verified_pages") or []) > 1 else ""
            lines.append(f"  {it['rank']}. {it['name']}{tag} | {role} | {url}{more} | news {v.get('pair_count_24m')} | {v.get('method')}{note}")
        lines.append(f"{title} - not chosen")
        for it in [x for x in plan[key] if not x.get("selected")]:
            v = it["validation"]
            tag = (" [already tracked]" if it.get("tracked") else "") + (" [listed]" if v.get("listed") else "")
            note = ("  NOTE: " + "; ".join(v["notes"])) if v.get("notes") else ""
            lines.append(f"  - {it['name']}{tag} ({it.get('slot', it.get('context_term', ''))}) | {'valid, not in top five' if v['accepted'] else 'REJECTED'}: {v['reason']}{note}")
    return lines


def _evidence_key(ev: Dict[str, Any], names: List[str]) -> str:
    """Which pooled competitor an ownership-evidence row is about. The model sometimes puts the whole claim sentence in "candidate"
    ("Goibibo is owned by MakeMyTrip"), so the "child" field is tried first, then a candidate name found in the candidate text."""
    for field in (ev.get("child"), ev.get("candidate")):
        for n in names:
            if field and validator.same_company(n, field):
                return core_name(n)
    text = " " + core_name(ev.get("candidate") or "") + " "
    hits = [(text.find(" " + core_name(n) + " "), n) for n in names if core_name(n) and (" " + core_name(n) + " ") in text]
    return core_name(min(hits)[1]) if hits else core_name(ev.get("candidate") or ev.get("child") or "")


def format_plan(plan: Dict[str, Any]) -> str:
    lines = [f"Seeding plan for {plan['client']}  (model {plan.get('model')}, cost ${plan.get('cost_usd')})"]
    w = plan.get("website") or {}
    lines.append(f"website: {(plan.get('company') or {}).get('website')} -> {'OK ' + str(w.get('domain')) if w.get('ok') else 'not set'} ({w.get('reason')})")
    lines.append("")
    for title, key in (("EXECUTIVES (chosen: role order, then validated news count)", "executives"), ("COMPETITORS (chosen: valid India-market peers, top 5 by validated news count)", "competitors")):
        lines.append(title)
        chosen = [x for x in plan[key] if x.get("selected")]
        rest = [x for x in plan[key] if not x.get("selected")]
        for it in chosen:
            v = it["validation"]
            extra = f" [{it['context_term']}]" if key == "competitors" else f" ({it.get('slot')})"
            lines.append(f"  {it['rank']}. {it['name']}{extra}  - {it['role']}  -> ACCEPT: {v['reason']}")
            for u in v.get("sources", [])[:3]:
                lines.append(f"       source: {u}")
            for a in it["aliases"]:
                lines.append(f"       alias {'ON ' if a['enabled'] else 'off'} {a['alias']}: {a['reason']}")
        if rest:
            lines.append("  not chosen:")
            for it in rest:
                v = it["validation"]
                lines.append(f"     - {it['name']} ({it.get('slot', '')}) {'accepted' if v['accepted'] else 'needs_review'}: {v['reason']}")
        lines.append("")
    lines.append(f"web citations on the call: {len(plan.get('citations', []))}; follow-up call: {plan.get('follow_up')}")
    lines.append("")
    lines.extend(summary_lines(plan))
    return "\n".join(lines)


def _dedupe_entity(db, client_id, name: str, entity_type: str):
    from app.models.entity import Entity
    from app.services.intelligence.entity_discovery import entity_discovery_engine as eng
    existing = db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == entity_type,
                                       Entity.name.ilike(name)).first()
    if existing:
        return existing, "exact"
    if entity_type == "competitor":
        key = core_name(name)
        if key:
            for e in db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == "competitor").all():
                if core_name(e.name) == key:
                    return e, "same core name"
    cid = client_id if isinstance(client_id, uuid.UUID) else uuid.UUID(str(client_id))
    near = (eng._find_near_duplicate_person_entity(db, cid, name) if entity_type == "person"
            else eng._find_near_duplicate_competitor_entity(db, cid, name))
    if near:
        return near, "near-duplicate"
    return None, None


def _enabled_alias_keywords(entity_id, aliases) -> list:
    from app.models.entity import EntityKeyword
    return [EntityKeyword(entity_id=entity_id, keyword_text=a["alias"], match_type="exact", category="ALIAS",
                          priority=2, is_active=True) for a in aliases if a.get("enabled")]


def apply_plan(db, client_id, plan: Dict[str, Any], refresh: bool = False, rematch: bool = True) -> Dict[str, Any]:
    """Write the plan. The chosen list is persisted: with an active list already stored this raises AlreadySeeded unless
    refresh=True. On a refresh, stored rows that are no longer chosen are retired (their entities stay)."""
    from app.models.entity import Entity, EntityKeyword
    from app.models.seeded_entity import SeededEntity
    from app.services.client_service import provision_entity_search_feeds

    existing_active = db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.status == "active").count()
    if existing_active and not refresh:
        raise AlreadySeeded(f"{existing_active} seeded entities are already stored for this client; re-seeding needs an explicit refresh")
    ctx = client_context(db, client_id)
    summary = {"active": 0, "needs_review": 0, "created": 0, "linked": 0, "feeds": 0, "retired": 0, "website_set": None}
    # verified company website -> brand entity, only into an empty field
    w = plan.get("website") or {}
    brand = ctx["brand"]
    if brand is not None and w.get("ok") and w.get("domain") and not w.get("stored"):
        if not brand.domain:
            brand.domain = w["domain"]
            summary["website_set"] = w["domain"]
        if not brand.website:
            brand.website = "https://" + w["domain"]
    touched_entities, seeded_entity_ids, chosen_by_kind = [], [], {"executive": set(), "competitor": set()}
    for kind, key, etype in (("executive", "executives", "person"), ("competitor", "competitors", "competitor")):
        for it in plan[key]:
            v = it["validation"]
            if not it.get("selected") and v["accepted"]:
                continue                        # a valid candidate that did not make the top five is not stored
            row = db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.kind == kind,
                                                SeededEntity.name == it["name"]).first()
            if row is None:
                row = SeededEntity(client_id=client_id, kind=kind, name=it["name"], rank=it["rank"])
                db.add(row)
            row.rank = it["rank"]
            row.role = it.get("role")
            row.context_term = it.get("context_term") or None
            row.aliases = it["aliases"]
            row.sources = v.get("sources", [])
            row.pair_count_24m = v.get("pair_count_24m")
            row.validated = bool(v["accepted"])
            row.seeded_at = dt.datetime.now(dt.timezone.utc)
            if row.status == "retired":
                continue                        # an operator retired it: a refresh does not bring it back
            if not v["accepted"]:
                row.status = "needs_review"
                summary["needs_review"] += 1
                continue
            row.status = "active"
            chosen_by_kind[kind].add(it["name"])
            ent, how = _dedupe_entity(db, client_id, it["name"], etype)
            if ent is None:
                ent = Entity(client_id=client_id, name=it["name"], entity_type=etype)
                db.add(ent)
                db.flush()
                db.add(EntityKeyword(entity_id=ent.id, keyword_text=it["name"], match_type="exact", category="PRIMARY",
                                     priority=1, is_active=True))
                for kw in _enabled_alias_keywords(ent.id, it["aliases"]):
                    db.add(kw)
                summary["created"] += 1
                touched_entities.append(ent)
            else:
                summary["linked"] += 1
            row.entity_id = ent.id
            seeded_entity_ids.append(ent.id)
            summary["active"] += 1
            co = ctx["name"] if kind == "executive" else (it.get("context_term") or None)
            feeds = provision_entity_search_feeds(db, client_id, ent.name, co_occur_with=co, quote=True, co_quoted=(kind == "executive"))
            summary["feeds"] += len(feeds)
    if refresh:
        for r in db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.status == "active").all():
            if r.name not in chosen_by_kind[r.kind]:
                r.status = "retired"
                summary["retired"] += 1
    db.commit()
    if touched_entities:
        _refresh_matcher_and_rematch(db, client_id, touched_entities)
    if rematch and seeded_entity_ids:
        from app.services.seeding import rematch as rematch_mod
        summary["rematch"] = rematch_mod.rematch_seeded(db, client_id, seeded_entity_ids)
    logger.info("seeding_applied", client_id=str(client_id), **{k: v for k, v in summary.items() if k != "rematch"})
    return summary


def _refresh_matcher_and_rematch(db, client_id, entities) -> None:
    """Refresh the live matcher's keywords (new documents match the seeded names from now on). The shared 6-hour rematch of
    just-collected documents also runs; the full-corpus seed-scoped rematch is services/seeding/rematch.py."""
    try:
        from app.services.matching_engine import engine_instance
        engine_instance.refresh_processor(db)
    except Exception as e:
        logger.warning("seeding_matcher_refresh_failed", error=str(e)[:200])
    try:
        from app.utils.redis_client import redis_client
        redis_client.publish("keyword_updated", "refresh")
    except Exception:
        pass
    try:
        from app.services.intelligence.entity_discovery import entity_discovery_engine
        for e in entities:
            entity_discovery_engine._rematch_recent_documents_for_new_entity(db, str(client_id), e.id, e.name)
    except Exception as e:
        logger.warning("seeding_rematch_failed", error=str(e)[:200])


def add_aliases(db, client_id, name: str, aliases: List[str], write: bool = False, fetch: Optional[Callable] = None,
                measure: bool = True) -> Dict[str, Any]:
    """Add aliases the news uses to one ACTIVE seeded entity, under the same safety rule as seeding (aliases.resolve_aliases:
    multi-word accepted, a bare competitor alias only after the 50-document false-match measurement, generic words and a
    person's single word rejected). Without write=True it only reports what would happen. With write=True the resolved aliases
    are stored on the seeded row, the enabled ones become ALIAS keywords on the entity, the live matcher is refreshed and the
    seed-scoped rematch runs for that entity. No LLM call; the measurement uses free Google News requests."""
    from app.models.entity import EntityKeyword
    from app.models.seeded_entity import SeededEntity
    row = db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.name.ilike(name),
                                        SeededEntity.status == "active").first()
    if row is None:
        return {"error": f'No active seeded entity named "{name}".'}
    ctx = [row.context_term] if row.context_term else []
    resolved = alias_mod.resolve_aliases(row.name, aliases, row.kind, ctx, measure, fetch)
    have = {str(a.get("alias", "")).strip().lower() for a in (row.aliases or [])}
    new = [a for a in resolved if a["alias"].strip().lower() not in have]
    out: Dict[str, Any] = {"entity": row.name, "resolved": resolved, "new": new,
                           "enabled": [a["alias"] for a in new if a["enabled"]], "written": False}
    if not write:
        return out
    if new:
        row.aliases = list(row.aliases or []) + new           # reassigned so the JSON column change is tracked
    existing = {k[0].strip().lower() for k in db.query(EntityKeyword.keyword_text).filter(EntityKeyword.entity_id == row.entity_id).all()}
    for kw in _enabled_alias_keywords(row.entity_id, new):
        if kw.keyword_text.strip().lower() not in existing:
            db.add(kw)
    # A multi-word alias also gets its own Google News / GDELT / HN search feeds (the existing provisioning, same query style as the
    # entity's own feeds); they are polled by the Run Pipeline. A one-word or disabled alias gets none.
    from app.services.client_service import provision_entity_search_feeds
    from app.services.seeding.gates import enabled_alias_texts
    co = client_context(db, client_id)["name"] if row.kind == "executive" else (row.context_term or None)
    # Every enabled multi-word alias of the row (not only the new ones), so re-running the command for an alias stored earlier creates
    # its feeds; provisioning skips feeds that already exist.
    alias_feeds = []
    for alias in [a for a in enabled_alias_texts(row) if len(a.split()) >= 2]:
        alias_feeds += provision_entity_search_feeds(db, client_id, alias, co_occur_with=co, quote=True, co_quoted=(row.kind == "executive"))
    out["alias_feeds"] = [f.feed_url for f in alias_feeds]
    db.commit()
    try:
        from app.services.matching_engine import engine_instance
        engine_instance.refresh_processor(db)
    except Exception as e:
        logger.warning("alias_matcher_refresh_failed", error=str(e)[:200])
    from app.services.seeding import rematch as rematch_mod
    out["rematch"] = rematch_mod.rematch_seeded(db, client_id, [row.entity_id])
    out["written"] = True
    return out


def retire(db, client_id, name: str) -> Dict[str, Any]:
    from app.models.entity import Entity
    from app.models.rss_feed import RSSFeed
    from app.models.seeded_entity import SeededEntity
    from app.services.client_service import entity_search_feed_urls
    rows = db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.name.ilike(name)).all()
    if not rows:
        return {"retired": 0, "message": f'No seeded entity named "{name}".'}
    ctx = client_context(db, client_id)
    feeds_off = 0
    for r in rows:
        r.status = "retired"
        if r.entity_id:
            ent = db.query(Entity).filter(Entity.id == r.entity_id).first()
            if ent:
                co = ctx["name"] if r.kind == "executive" else (r.context_term or None)
                urls = list(entity_search_feed_urls(ent.name, co_occur_with=co, quote=True, co_quoted=(r.kind == "executive")).values())
                for f in db.query(RSSFeed).filter(RSSFeed.client_id == client_id, RSSFeed.feed_url.in_(urls)).all():
                    if f.is_active:
                        f.is_active = False
                        feeds_off += 1
    db.commit()
    return {"retired": len(rows), "feeds_deactivated": feeds_off, "message": "Retired. The entity itself is left in place."}


def seed_client(db, client_id, apply: bool = False, propose_fn: Optional[Callable] = None,
                fetch: Optional[Callable] = None, measure_aliases: bool = True, refresh: bool = False,
                fetch_text: Optional[Callable] = None, http_get: Optional[Callable] = None) -> Dict[str, Any]:
    plan = build_plan(db, client_id, propose_fn, fetch, measure_aliases, fetch_text=fetch_text, http_get=http_get)
    result = {"plan": plan, "applied": None}
    if apply:
        result["applied"] = apply_plan(db, client_id, plan, refresh=refresh)
    return result
