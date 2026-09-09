import os
import time
import json as _json
import structlog
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.risk import RiskEvent
from app.models.alert import Alert
from app.models.narrative import Narrative
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


class AISummaryEngine:
    """
    Per-item AI Summary (what / when / how_to_solve) for individual MEDIUM+
    Risk Events and Active Alerts -- the same RCA discipline
    narrative_engine.py's _generate_rca already applies at the narrative
    level, extended down to the individual item so a Risk Event/Alert never
    shows only a raw score with nothing explaining it.

    Reuse-first: if this item is already covered by a linked narrative that
    has a real, evidence-grounded RCA (narrative_engine.py's
    evidence_metadata.rca), that RCA's root_cause/recommended_action is
    reused verbatim as how_to_solve rather than generating a second,
    potentially-conflicting explanation for the same underlying story. Only
    items with no such linked RCA get a fresh, item-scoped LLM call.

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

    def _narrative_maps(self, db: Session, client_id: str) -> Tuple[Dict[str, tuple], Dict[str, tuple]]:
        """
        Reverse index from RiskEvent id / Alert id -> (Narrative, rca dict),
        built off each narrative's own evidence_metadata.supporting_risks /
        supporting_alerts -- the exact same fields narrative_engine.py
        already populates per narrative (see calculate_narratives), just
        read in the other direction. Same mechanism documents.py already
        uses for the "Part of: narrative" badge (there via
        supporting_documents); this is that identical pattern applied to
        the two other id lists the narrative already carries, not a new
        lookup path.

        Only narratives with a real `rca` dict are included -- a narrative
        linkage without an RCA has nothing to reuse, so those items fall
        through to fresh generation, same as an unlinked item.
        """
        narratives = db.query(Narrative).filter(Narrative.client_id == client_id).all()
        risk_map: Dict[str, tuple] = {}
        alert_map: Dict[str, tuple] = {}
        for n in narratives:
            em = n.evidence_metadata or {}
            rca = em.get("rca")
            if not isinstance(rca, dict):
                continue
            for rid in em.get("supporting_risks") or []:
                risk_map.setdefault(rid, (n, rca))
            for aid in em.get("supporting_alerts") or []:
                alert_map.setdefault(aid, (n, rca))
        return risk_map, alert_map

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
        Single-field LLM call, same DeepSeek/OpenRouter call pattern and
        fail-safe convention as narrative_engine.py's _generate_rca (returns
        None on ANY failure -- missing key, timeout, non-200, malformed
        JSON -- never a fabricated fallback string). Grounded only in this
        one item's own real fields and its own source document snippet, not
        the narrative-level cluster context _generate_rca uses -- there is
        no cluster here, only one item.
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
                    # Same reasoning=False choice as narrative_engine.py's
                    # _generate_rca: this is a bounded, single-field task, and
                    # reasoning burns the completion budget on chain-of-thought
                    # before reaching the actual JSON on this model.
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

    def _build_for_risk_event(
        self, db: Session, re: RiskEvent, risk_narrative_map: Dict[str, tuple],
        client_name: str, client_id: str, run_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        existing = (re.explainability or {}).get("ai_summary")
        # Cache: only regenerate if this row's own computed_at has moved
        # since the summary was generated (mirrors narrative_engine.py's
        # mention_count freshness check) -- not on every pipeline run.
        # None here means "nothing to write", not "no summary exists".
        cache_key = re.computed_at.isoformat() if re.computed_at else None
        if existing and existing.get("_cache_key") == cache_key:
            return None

        document = db.query(Document).filter(Document.id == re.document_id).first() if re.document_id else None
        doc_topic = db.query(DocumentTopic).filter(DocumentTopic.document_id == re.document_id).first() if re.document_id else None
        topic_name = getattr(getattr(doc_topic, "topic", None), "name", None) or "General"
        title = (document.title if document and document.title else None) or "an untitled item"

        what = f"{re.risk_level} risk flagged on \"{title}\" (category: {topic_name})."
        when = self._format_when(re.computed_at or re.created_at)

        linked = risk_narrative_map.get(str(re.id))
        if linked:
            narrative, rca = linked
            return {
                "what": what,
                "when": when,
                "how_to_solve": rca.get("recommended_action"),
                "root_cause": rca.get("root_cause"),
                "source": "narrative",
                "narrative_id": str(narrative.id),
                "narrative_name": narrative.narrative_name,
                "_cache_key": cache_key,
            }

        how_to_solve = self._generate_how_to_solve(
            item_kind="Risk Event",
            what=what,
            topic_name=topic_name,
            document_title=document.title if document else None,
            document_snippet=document.normalized_content if document else None,
            client_name=client_name,
            client_id=client_id,
            run_id=run_id,
        )
        if how_to_solve is None:
            # Fail-safe convention (same as _generate_rca): never overwrite
            # a previously-good summary with a partial one on a failed call.
            return None

        return {
            "what": what,
            "when": when,
            "how_to_solve": how_to_solve,
            "source": "generated",
            "_cache_key": cache_key,
        }

    def _build_for_alert(
        self, db: Session, alert: Alert, alert_narrative_map: Dict[str, tuple], risk_narrative_map: Dict[str, tuple],
        client_name: str, client_id: str, run_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        existing = (alert.explainability or {}).get("ai_summary")
        cache_key = alert.updated_at.isoformat() if alert.updated_at else None
        if existing and existing.get("_cache_key") == cache_key:
            return None

        document = db.query(Document).filter(Document.id == alert.document_id).first() if alert.document_id else None
        doc_topic = db.query(DocumentTopic).filter(DocumentTopic.document_id == alert.document_id).first() if alert.document_id else None
        topic_name = getattr(getattr(doc_topic, "topic", None), "name", None) or alert.alert_type

        what = f"{alert.severity} {alert.alert_type} alert: {alert.title}."
        when = self._format_when(alert.created_at)

        # Direct link first (narrative's own supporting_alerts); if this
        # alert isn't directly in any narrative's cluster, fall through to
        # the risk events that fed it (Alert.explainability.contributing_risks,
        # already populated by alert_engine.py) and reuse whichever of those
        # is itself narrative-linked. Same two reverse-index maps built once
        # per client, no second lookup mechanism.
        linked = alert_narrative_map.get(str(alert.id))
        if not linked:
            for rid in (alert.explainability or {}).get("contributing_risks") or []:
                if rid in risk_narrative_map:
                    linked = risk_narrative_map[rid]
                    break

        if linked:
            narrative, rca = linked
            return {
                "what": what,
                "when": when,
                "how_to_solve": rca.get("recommended_action"),
                "root_cause": rca.get("root_cause"),
                "source": "narrative",
                "narrative_id": str(narrative.id),
                "narrative_name": narrative.narrative_name,
                "_cache_key": cache_key,
            }

        how_to_solve = self._generate_how_to_solve(
            item_kind="Active Alert",
            what=what,
            topic_name=topic_name,
            document_title=document.title if document else None,
            document_snippet=document.normalized_content if document else None,
            client_name=client_name,
            client_id=client_id,
            run_id=run_id,
        )
        if how_to_solve is None:
            return None

        return {
            "what": what,
            "when": when,
            "how_to_solve": how_to_solve,
            "source": "generated",
            "_cache_key": cache_key,
        }

    def process_client(
        self,
        db: Session,
        client_id: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        log = logger.bind(run_id=run_id, batch_id=batch_id, worker_id=worker_id, client_id=client_id,
                           processing_stage="AI_SUMMARY")
        log.info("ai_summary_started")

        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            log.error("ai_summary_client_not_found")
            return

        risk_narrative_map, alert_narrative_map = self._narrative_maps(db, client_id)

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
            or_(Entity.entity_type != "competitor", RiskEvent.entity_id.is_(None)),
        ).all()

        # No visibility cap needed: Active Alerts has no pagination, it
        # already shows every unacknowledged alert 1:1 with what this query
        # returns.
        alerts = db.query(Alert).outerjoin(Entity, Entity.id == Alert.entity_id).filter(
            Alert.client_id == client_id,
            Alert.is_acknowledged == False,
            or_(Entity.entity_type != "competitor", Alert.entity_id.is_(None)),
        ).all()

        generated = 0
        reused = 0
        skipped = 0

        for re in risk_events:
            summary = self._build_for_risk_event(db, re, risk_narrative_map, client.name, client_id, run_id)
            if summary is None:
                skipped += 1
                continue
            explainability = dict(re.explainability or {})
            explainability["ai_summary"] = summary
            re.explainability = explainability
            if summary.get("source") == "narrative":
                reused += 1
            else:
                generated += 1

        db.commit()

        for alert in alerts:
            summary = self._build_for_alert(db, alert, alert_narrative_map, risk_narrative_map, client.name, client_id, run_id)
            if summary is None:
                skipped += 1
                continue
            explainability = dict(alert.explainability or {})
            explainability["ai_summary"] = summary
            alert.explainability = explainability
            if summary.get("source") == "narrative":
                reused += 1
            else:
                generated += 1

        db.commit()

        log.info("ai_summary_complete", risk_events=len(risk_events), alerts=len(alerts),
                  generated=generated, reused=reused, skipped=skipped)
