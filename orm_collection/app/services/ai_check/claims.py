"""
Cross-check of what an AI says (flagged sentences, see triage.py) against what XOOP itself holds about the client.

For each flagged sentence (a serious accusation about the client or an executive, stated as plain fact) this finds the XOOP
incident it is about: the client's flagged risk documents are grouped into incidents (incidents.py), and a sentence matches the
incident whose headlines and event phrases share the most distinctive words with the sentence's own event phrase and wording.
The match reads the incident's case status (allegation, probe, charged, penalty_or_order, settled ...). When the AI states as fact
something XOOP labels allegation, probe or charged, a one-line note says so. No match is reported as such.

Super admin only (the endpoint fills this for super admins and returns nothing otherwise). Reads risk events; writes nothing; no score
reads it.
"""
from typing import Any, Dict, List, Optional, Sequence

from app.services.intelligence.incidents import event_tokens, group_incidents, outlet_of, title_tokens

MATCH_MIN_SHARED = 2
# Words that appear in nearly every accusation sentence and so say nothing about which story it is.
_GENERIC = frozenset({
    "section", "sections", "act", "code", "case", "cases", "against", "invoking", "filed", "registered", "company", "project",
    "projects", "management", "top", "crore", "lakh", "rs", "yes", "also", "multiple", "regulators", "authorities", "legal", "proceedings",
    "penalty", "fine", "penalised", "penalized", "violation", "violations", "issued", "imposed", "authority",
})
AS_FACT_NOTE_STATUSES = ("allegation", "probe", "charged")
_STATUS_WORD = {"allegation": "an allegation", "probe": "a probe", "charged": "charged"}


def _tokens(text: Optional[str], event: Optional[str], client_name: str) -> frozenset:
    return frozenset((title_tokens(text, client_name) | event_tokens(event, client_name)) - _GENERIC)


def xoop_incidents(db, client) -> List[Dict[str, Any]]:
    """The client's flagged documents (score above LOW, not a competitor's) grouped into incidents. Each: title (the strongest
    document's), status (that document's case-status label, or None), documents, sources, score, and the pooled word set."""
    from app.models.document import Document
    from app.models.entity import Entity
    from app.models.risk import RiskEvent
    from app.core.risk_config import RISK_THRESHOLDS
    from sqlalchemy import or_

    best: Dict[Any, Any] = {}
    q = db.query(RiskEvent.document_id, RiskEvent.entity_id, RiskEvent.risk_score, RiskEvent.explainability,
                 Document.title, Document.published_at).join(Document, Document.id == RiskEvent.document_id).outerjoin(
        Entity, Entity.id == RiskEvent.entity_id).filter(
        RiskEvent.client_id == client.id, RiskEvent.risk_score > RISK_THRESHOLDS["LOW_TO_MEDIUM"],
        or_(Entity.entity_type != "competitor", Entity.entity_type.is_(None), RiskEvent.entity_id.is_(None)))
    for doc_id, entity_id, score, expl, title, published in q.all():
        if doc_id not in best or score > best[doc_id]["score"]:
            ex = expl or {}
            best[doc_id] = {"doc_id": doc_id, "entity_id": entity_id, "entity_name": client.name, "score": score, "title": title,
                            "published_at": published, "status": ex.get("case_status"), "event": ex.get("case_event")}
    items = sorted(best.values(), key=lambda i: str(i["doc_id"]))
    out = []
    for group in group_incidents(items):
        members = [items[i] for i in group]
        lead = max(members, key=lambda m: (m["score"], m["published_at"].timestamp() if m["published_at"] else 0.0, str(m["doc_id"])))
        pooled = frozenset().union(*[_tokens(m["title"], m["event"], client.name) for m in members])
        out.append({
            "title": lead["title"] or "Untitled document", "status": lead["status"], "score": lead["score"], "documents": len(members),
            "sources": len({outlet_of(m["title"]) or f"doc:{m['doc_id']}" for m in members}), "tokens": pooled,
        })
    return out


def match_incident(flag_tokens: frozenset, incidents: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The incident sharing the most words with the sentence (at least MATCH_MIN_SHARED); larger incidents win ties."""
    best, best_key = None, (0, 0)
    for inc in incidents:
        shared = len(flag_tokens & inc["tokens"])
        if shared >= MATCH_MIN_SHARED and (shared, inc["documents"]) > best_key:
            best, best_key = inc, (shared, inc["documents"])
    return best


def claim_note(framing: str, matched: Optional[Dict[str, Any]]) -> str:
    if not matched:
        return "No matching XOOP incident."
    status = matched.get("status")
    if framing == "FACT" and status in AS_FACT_NOTE_STATUSES:
        return f"The AI states this as fact; XOOP labels the matching story {_STATUS_WORD[status]}."
    if status is None:
        return "Matching XOOP incident has no case status yet."
    return f"Matches an XOOP incident labelled {status.replace('_', ' ')}."


def build_claim_checks(db, client, flags: Sequence[Any], question_labels: Dict[str, str]) -> List[Dict[str, Any]]:
    """One entry per flagged sentence: the sentence, where the AI said it, and the matching XOOP incident (or None) with the note."""
    flagged = [f for f in flags if f.flagged]
    if not flagged:
        return []
    incidents = xoop_incidents(db, client)
    out = []
    for f in flagged:
        match = match_incident(_tokens(f.sentence, f.event, client.name), incidents)
        occ = f.occurrences or []
        out.append({
            "sentence": f.sentence,
            "questions": [question_labels.get(o.get("prompt"), o.get("prompt")) for o in occ],
            "repeats": sorted({r for o in occ for r in (o.get("repeats") or [])}),
            "about": f.about, "event": f.event, "inline_domains": f.inline_domains or [],
            "matched": None if not match else {"status": match["status"], "title": match["title"], "documents": match["documents"], "sources": match["sources"]},
            "note": claim_note(f.framing or "FACT", match),
        })
    return out
