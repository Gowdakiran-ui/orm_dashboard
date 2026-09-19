import os
import time
import hashlib
import json as _json
import structlog
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.risk import RiskEvent
from app.models.alert import Alert
from app.models.document import Document
from app.models.topic import DocumentTopic
from app.models.entity import Entity
from app.models.client import Client
from app.core.risk_config import RISK_THRESHOLDS
from app.utils.llm_call_logging import log_llm_call

logger = structlog.get_logger()

# Same MEDIUM+ boundary risk_engine.py itself uses (RISK_THRESHOLDS) -- a
# Risk Event's AI Summary is only worth generating once it has already
# crossed out of LOW, the same "is this worth an analyst's attention"
# line the rest of Risk Center draws.
_MEDIUM_PLUS = ("MEDIUM", "HIGH", "CRITICAL")

# Must match what fetchDocuments() itself requests
# (orm_dashboard/src/lib/api.ts: `?limit=500`) -- the real cap on how many
# of a client's documents Risk Center can ever have loaded into `documents`
# to filter into its register.
_UI_DOCUMENT_WINDOW = 500


def _content_signature(*parts) -> str:
    """
    Stable hash of the exact values that determine a summary's content --
    used as the cache key instead of RiskEvent.computed_at/Alert.updated_at.

    Real bug this replaces (forensic audit, confirmed live with two
    consecutive pipeline runs against unchanged data): both those columns
    get re-stamped by risk_engine.py/alert_engine.py on every single
    re-evaluation, regardless of whether the score/content actually
    changed -- so a timestamp-keyed cache never holds, and every eligible
    item was being re-billed to the LLM on every pipeline run. Keys on a
    value that only changes when the underlying data actually changes,
    rather than a clock.
    """
    joined = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class AISummaryEngine:
    """
    Per-item AI Summary (what / when / how_to_solve) for individual MEDIUM+
    Risk Events and Active Alerts, so a Risk Event/Alert never shows only a
    raw score with nothing explaining it.

    Cost-scoped to what's actually on screen: a Risk Event tied to a
    document outside Risk Center's own visible window (see
    get_client_visible_documents, imported below rather than
    reimplemented) can never be shown in the UI, so it's excluded from
    LLM-billed generation entirely -- confirmed live that some clients'
    full MEDIUM+ history is much larger than what the register can ever
    display. Active Alerts need no equivalent cap: that list has no
    pagination, it already shows every unacknowledged alert.

    Stored in the item's own existing `explainability` JSON column under an
    `ai_summary` key -- no schema change. That column already flows through
    documents.py's read_document/read_client_documents (as
    risk_explainability) and the active-alerts endpoint exposes it the same
    way, so no new API surface is needed beyond adding that one field.
    """

    @staticmethod
    def _severity_label(risk_score: float) -> str:
        if risk_score <= RISK_THRESHOLDS["LOW_TO_MEDIUM"]:
            return "LOW"
        elif risk_score <= RISK_THRESHOLDS["MEDIUM_TO_HIGH"]:
            return "MEDIUM"
        elif risk_score <= RISK_THRESHOLDS["HIGH_TO_CRITICAL"]:
            return "HIGH"
        else:
            return "CRITICAL"

    @staticmethod
    def _format_when(dt) -> Optional[str]:
        if not dt:
            return None
        return dt.strftime("%b %d, %Y %H:%M UTC")

    def _generate_how_to_solve(
        self, *, item_kind: str, what: str, topic_name: str, document_title: Optional[str],
        document_snippet: Optional[str], client_name: str, client_id: str, run_id: Optional[str],
    ) -> Optional[str]:
        """
        Single-field LLM call over DeepSeek/OpenRouter. Fail-safe: returns
        None on ANY failure -- missing key, timeout, non-200, malformed
        JSON -- never a fabricated fallback string. Grounded only in this
        one item's own real fields and its own source document snippet.
        """
        import requests

        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return None

        log = logger.bind(run_id=run_id, task="ai_summary_generate", client=client_name, item_kind=item_kind)
        t_call_start = time.perf_counter()

        def _record(success, usage=None):
            log_llm_call(
                call_type="ai_summary_generate",
                client_id=client_id,
                run_id=run_id,
                tokens_prompt=(usage or {}).get("prompt_tokens"),
                tokens_completion=(usage or {}).get("completion_tokens"),
                latency_ms=(time.perf_counter() - t_call_start) * 1000,
                success=success,
            )

        user_prompt = (
            f"Client: {client_name}\n"
            f"Item type: {item_kind}\n"
            f"Category/topic: {topic_name}\n"
            f"Summary: {what}\n"
            f"Source document title: {document_title or '(none)'}\n"
            f"Source document excerpt: {(document_snippet or '(none)')[:1500]}\n"
        )
        system_prompt = (
            "You write ONE concrete, actionable next step for resolving or "
            "responding to a single brand risk item or alert, using ONLY the "
            "data given to you. Never invent facts, numbers, names, or events "
            "not present in the input. If the input is too thin to support a "
            "specific claim, keep the step brief and generic rather than "
            "fabricating specifics.\n"
            'Return strict JSON with exactly this one key: {"how_to_solve": "..."}\n'
            "how_to_solve: one or two sentences, a concrete next step someone "
            "could take today, grounded in the item and excerpt given."
        )

        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek/deepseek-v4-pro",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 400,
                    # reasoning=False: this is a bounded, single-field task,
                    # and reasoning burns the completion budget on
                    # chain-of-thought before reaching the actual JSON.
                    "reasoning": {"enabled": False},
                    "response_format": {"type": "json_object"},
                },
                timeout=15.0,
            )
            if resp.status_code != 200:
                log.warning("ai_summary_http_error", status=resp.status_code, body=resp.text[:300])
                _record(success=False)
                return None

            resp_json = resp.json()
            usage = resp_json.get("usage")
            content = resp_json["choices"][0]["message"]["content"]
            if content is None:
                log.warning("ai_summary_null_content", raw=str(resp_json)[:400])
                _record(success=False, usage=usage)
                return None

            parsed = _json.loads(content)
            value = parsed.get("how_to_solve")
            if not isinstance(value, str) or not value.strip():
                log.warning("ai_summary_malformed", raw=str(content)[:400])
                _record(success=False, usage=usage)
                return None

            log.info("ai_summary_generated")
            _record(success=True, usage=usage)
            return value.strip()

        except Exception as exc:
            log.warning("ai_summary_failed", error=str(exc))
            _record(success=False)
            return None

    def _build_risk_event_what(self, re: RiskEvent) -> str:
        """
        Real description of what specifically triggered this risk event --
        not the old risk_level/title/category restatement, which told the
        reader nothing beyond what the Badge/title already show on the same
        card. Built from the event's own real trigger signals -- already
        computed and stored on it by risk_engine.py (explainability.
        decision_reason, a deterministic sentence built from real topic/
        sentiment/trend/source values, and risk_factors), not a new data
        path.
        """
        explainability = re.explainability or {}
        decision_reason = explainability.get("decision_reason")
        if decision_reason:
            return decision_reason

        risk_factors = re.risk_factors or []
        factor_parts = [
            f"{f.get('type')} '{f.get('factor')}'" for f in risk_factors if f.get("factor")
        ]
        if factor_parts:
            return f"{re.risk_level} risk driven by {', '.join(factor_parts)}."

        return f"{re.risk_level} risk flagged with no further trigger detail available."

    def _prepare_risk_event(
        self, db: Session, re: RiskEvent,
        client_name: str, client_id: str, run_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Decide-only half of what used to be _build_for_risk_event: every
        cache/reuse check and every non-LLM field, but stops short of
        actually calling _generate_how_to_solve so that call can be fanned
        out to its own task (see pipeline_stage_ai_summary in
        aggregation_tasks.py) instead of happening inline in this loop.

        Returns None (nothing to do -- cache unchanged, no write needed) or
        {"action": "generate", "gen_kwargs": {...}, "partial": {...}} (needs
        a fresh LLM call; "partial" is every summary field except
        how_to_solve, merged with the LLM result by the gather step).
        """
        existing = (re.explainability or {}).get("ai_summary")

        document = db.query(Document).filter(Document.id == re.document_id).first() if re.document_id else None
        doc_topic = db.query(DocumentTopic).filter(DocumentTopic.document_id == re.document_id).first() if re.document_id else None
        topic_name = getattr(getattr(doc_topic, "topic", None), "name", None) or "General"
        title = (document.title if document and document.title else None) or "an untitled item"
        # [:1500] matches _generate_how_to_solve's own truncation -- content
        # past that point never actually reaches the prompt, so it must not
        # be able to bust the cache either.
        snippet = (document.normalized_content if document else "") [:1500]

        what = self._build_risk_event_what(re)
        when = self._format_when(re.computed_at or re.created_at)

        # Cache key: a hash of exactly the fields that feed how_to_solve
        # (risk_level, topic, title, source excerpt) plus `what` itself, so
        # a cache hit can't leave a stale `what` behind after risk_engine.py
        # updates the trigger signals it's built from on a later pipeline
        # run -- same fix as _prepare_alert's item_signature.
        cache_key = _content_signature(re.risk_level, topic_name, title, snippet, what)
        if existing and existing.get("_cache_key") == cache_key:
            return None

        return {"action": "generate", "gen_kwargs": {
            "item_kind": "Risk Event",
            "what": what,
            "topic_name": topic_name,
            "document_title": document.title if document else None,
            "document_snippet": snippet,
            "client_name": client_name,
            "client_id": client_id,
            "run_id": run_id,
        }, "partial": {
            "what": what,
            "when": when,
            "source": "generated",
            "_cache_key": cache_key,
        }}

    def _build_alert_what(self, db: Session, alert: Alert) -> str:
        """
        Real description of what specifically triggered this alert -- not
        the old severity/alert_type/title restatement, which told the
        reader nothing beyond what the Badge/title already show on the same
        card. Built from the alert's own real trigger signals -- already
        computed and stored on it by alert_engine.py's
        _upsert_hardened_alert (explainability.supporting_evidence,
        supporting_signals, evidence_score, confidence_score), not a new
        data path. Still real numbers, never a fabricated-sounding sentence.
        """
        explainability = alert.explainability or {}
        supporting_evidence = explainability.get("supporting_evidence") or {}
        supporting_signals = alert.supporting_signals or {}

        entity_name = None
        if alert.entity_id:
            entity = db.query(Entity).filter(Entity.id == alert.entity_id).first()
            entity_name = entity.name if entity else None
        entity_name = entity_name or "this entity"

        risks_count = supporting_signals.get("risks_count")
        trends_count = supporting_signals.get("trends_count")
        doc_count = supporting_evidence.get("document_count")
        exec_involved = supporting_evidence.get("executive_involved")

        signal_parts = []
        if risks_count:
            signal_parts.append(f"{risks_count} risk signal{'s' if risks_count != 1 else ''}")
        if trends_count:
            signal_parts.append(f"{trends_count} trend signal{'s' if trends_count != 1 else ''}")
        signals_desc = " and ".join(signal_parts) if signal_parts else "multiple intelligence signals"

        detail_parts = []
        if doc_count:
            detail_parts.append(f"backed by {doc_count} document{'s' if doc_count != 1 else ''}")
        if alert.evidence_score is not None:
            detail_parts.append(f"evidence score {alert.evidence_score:.1f}")
        if alert.confidence_score is not None:
            detail_parts.append(f"confidence {alert.confidence_score:.1f}%")
        if exec_involved:
            detail_parts.append("with executive involvement")

        sentence = f"{signals_desc} for {entity_name}"
        if detail_parts:
            sentence += f", {', '.join(detail_parts)}"
        sentence += "."
        return sentence

    def _prepare_alert(
        self, db: Session, alert: Alert,
        client_name: str, client_id: str, run_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Decide-only half of what used to be _build_for_alert -- see
        _prepare_risk_event's docstring for the return-value contract."""
        existing = (alert.explainability or {}).get("ai_summary")

        document = db.query(Document).filter(Document.id == alert.document_id).first() if alert.document_id else None
        doc_topic = db.query(DocumentTopic).filter(DocumentTopic.document_id == alert.document_id).first() if alert.document_id else None
        topic_name = getattr(getattr(doc_topic, "topic", None), "name", None) or alert.alert_type
        snippet = (document.normalized_content if document else "") [:1500]

        when = self._format_when(alert.created_at)
        what = self._build_alert_what(db, alert)

        # Cache key: a hash of exactly the fields that feed how_to_solve
        # (severity, alert_type, title, topic, source excerpt) plus `what`
        # itself, so a cache hit can't leave a stale `what` behind after
        # alert_engine.py updates the trigger signals it's built from on a
        # later pipeline run -- not alert.updated_at, which gets re-stamped
        # on every re-evaluation regardless of whether content actually
        # changed (see _content_signature's docstring).
        cache_key = _content_signature(alert.severity, alert.alert_type, alert.title, topic_name, snippet, what)
        if existing and existing.get("_cache_key") == cache_key:
            return None

        return {"action": "generate", "gen_kwargs": {
            "item_kind": "Active Alert",
            "what": what,
            "topic_name": topic_name,
            "document_title": document.title if document else None,
            "document_snippet": snippet,
            "client_name": client_name,
            "client_id": client_id,
            "run_id": run_id,
        }, "partial": {
            "what": what,
            "when": when,
            "source": "generated",
            "_cache_key": cache_key,
        }}

    def process_client(
        self,
        db: Session,
        client_id: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Decide-only pass: writes every ready/skip item immediately (no LLM
        involved) and returns the list of items that still need a fresh
        _generate_how_to_solve call, instead of generating them itself.
        pipeline_stage_ai_summary (aggregation_tasks.py) fans those out via
        chord and writes them back in pipeline_stage_ai_summary_gather --
        mirroring pipeline_stage_process's PROCESSING-stage fan-out. Only
        caller is that stage task; nothing else depends on this method
        completing all generation synchronously.
        """
        log = logger.bind(run_id=run_id, batch_id=batch_id, worker_id=worker_id, client_id=client_id,
                           processing_stage="AI_SUMMARY")
        log.info("ai_summary_started")

        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            log.error("ai_summary_client_not_found")
            return []

        # The exact document set Risk Center can ever show for this client --
        # imported from documents.py, not reimplemented here, so a future
        # change to the cap/ordering there is automatically inherited
        # instead of silently drifting apart (see module docstring).
        from app.api.endpoints.documents import get_client_visible_documents
        visible_docs = get_client_visible_documents(db, client_id, skip=0, limit=_UI_DOCUMENT_WINDOW)
        visible_doc_ids = {doc.id for doc in visible_docs}

        # Same competitor exclusion as risk_engine.py/alert_engine.py/
        # documents.py: a tracked competitor's own risk/alert is not this
        # client's own item to summarize. A RiskEvent tied to a document
        # outside visible_doc_ids can never be shown in Risk Center, so it's
        # excluded from LLM-billed generation entirely (cost fix -- see
        # module docstring).
        risk_events = db.query(RiskEvent).outerjoin(Entity, Entity.id == RiskEvent.entity_id).filter(
            RiskEvent.client_id == client_id,
            RiskEvent.risk_level.in_(_MEDIUM_PLUS),
            RiskEvent.document_id.in_(visible_doc_ids) if visible_doc_ids else False,
            or_(Entity.entity_type != "competitor", Entity.entity_type.is_(None), RiskEvent.entity_id.is_(None)),
        ).all()

        # No visibility cap needed: Active Alerts has no pagination, it
        # already shows every unacknowledged alert 1:1 with what this query
        # returns.
        alerts = db.query(Alert).outerjoin(Entity, Entity.id == Alert.entity_id).filter(
            Alert.client_id == client_id,
            Alert.is_acknowledged == False,
            or_(Entity.entity_type != "competitor", Entity.entity_type.is_(None), Alert.entity_id.is_(None)),
        ).all()

        pending: List[Dict[str, Any]] = []
        skipped = 0

        for re in risk_events:
            result = self._prepare_risk_event(db, re, client.name, client_id, run_id)
            if result is None:
                skipped += 1
                continue
            pending.append({"kind": "risk_event", "id": str(re.id), **result})

        for alert in alerts:
            result = self._prepare_alert(db, alert, client.name, client_id, run_id)
            if result is None:
                skipped += 1
                continue
            pending.append({"kind": "alert", "id": str(alert.id), **result})

        log.info("ai_summary_decide_complete", risk_events=len(risk_events), alerts=len(alerts),
                  skipped=skipped, pending_generation=len(pending))
        return pending

    def finalize_generated(self, db: Session, kind: str, item_id: str, partial: Dict[str, Any], how_to_solve: Optional[str]) -> bool:
        """
        Write-back half of the old inline generation path, run from
        pipeline_stage_ai_summary_gather once a fanned-out
        _generate_how_to_solve call has returned. how_to_solve is None on
        any LLM failure (see _generate_how_to_solve's fail-safe convention)
        -- same as the old code, that means skip: never overwrite a
        previously-good summary with a partial one. Returns True if a write
        happened.
        """
        if how_to_solve is None:
            return False
        model = RiskEvent if kind == "risk_event" else Alert
        obj = db.query(model).filter(model.id == item_id).first()
        if not obj:
            return False
        summary = {**partial, "how_to_solve": how_to_solve}
        explainability = dict(obj.explainability or {})
        explainability["ai_summary"] = summary
        obj.explainability = explainability
        return True
