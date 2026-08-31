import datetime
import time
import os
import uuid
import structlog
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.models.document import Document
from app.models.topic import DocumentTopic, Topic
from app.models.sentiment import DocumentSentiment
from app.models.risk import RiskEvent
from app.models.trends import TrendEvent
from app.models.alert import Alert
from app.models.narrative import Narrative
from app.models.entity import EntityMention, Entity
from app.models.client import Client

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────
# NARRATIVE PROCESSING STATE MACHINE (R2)
# ─────────────────────────────────────────────────────────────
class NarrativeStateMachine:
    PENDING = "NARRATIVE_PENDING"
    PROCESSING = "NARRATIVE_PROCESSING"
    COMPLETE = "NARRATIVE_COMPLETE"
    FAILED = "NARRATIVE_FAILED"
    RETRYING = "NARRATIVE_RETRYING"
    SKIPPED = "NARRATIVE_SKIPPED"

    TRANSITIONS = {
        PENDING: {PROCESSING, SKIPPED},
        PROCESSING: {COMPLETE, FAILED, RETRYING, SKIPPED},
        RETRYING: {PROCESSING, FAILED, SKIPPED},
        FAILED: {PROCESSING, SKIPPED},
        COMPLETE: {PROCESSING, SKIPPED},
        SKIPPED: {PROCESSING}
    }

    @classmethod
    def is_valid_transition(cls, from_state: str, to_state: str) -> bool:
        allowed = cls.TRANSITIONS.get(from_state, set())
        return to_state in allowed

    @staticmethod
    def transition(
        db: Session,
        client: Client,
        to_state: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
        retry_count: Optional[int] = None,
        latency_ms: Optional[float] = None
    ) -> bool:
        from_state = client.narrative_processing_status or NarrativeStateMachine.PENDING
        if not NarrativeStateMachine.is_valid_transition(from_state, to_state):
            logger.warning(
                "narrative_invalid_state_transition",
                client_id=str(client.id),
                from_state=from_state,
                to_state=to_state
            )
            return False
        
        client.narrative_processing_status = to_state
        if run_id is not None:
            client.narrative_run_id = run_id
        if batch_id is not None:
            client.narrative_batch_id = batch_id
        if failure_reason is not None:
            client.narrative_failure_reason = str(failure_reason)[:4000]
        if retry_count is not None:
            client.narrative_retry_count = retry_count
        if latency_ms is not None:
            client.narrative_latency_ms = latency_ms
        if to_state == NarrativeStateMachine.FAILED:
            client.narrative_failed_at = datetime.datetime.now(datetime.timezone.utc)
        return True


class NarrativeEngine:
    def __init__(self):
        # N15-F1: previously only 4 keys, and 3 of those 4 ("Layoffs",
        # "Customer Complaints", "Regulatory Action") don't match any name in
        # the actual production taxonomy (TOPIC_KEYWORDS in
        # topic_classification_batch_processor.py -- the only other place
        # these 17 topic names are declared in the codebase; topic.name here
        # comes from the same Topic table that taxonomy classifies into). So
        # in practice only "Cybersecurity" was ever really mapped -- the
        # other 16 production topics all fell through to the generic
        # "{topic.name} Narrative" / "General" fallback, not the 13-of-17
        # gap the original finding described. Now maps all 17 production
        # topics; the original 3 non-taxonomy keys are kept too (not
        # removed) since test_narrative_engine.py's fixtures construct Topic
        # rows under those exact names and Topic is otherwise
        # admin-configurable, not necessarily hard-limited to the 17.
        self.narrative_mapping = {
            "Layoffs": {
                "name": "Layoff Narrative",
                "type": "Operational"
            },
            "Customer Complaints": {
                "name": "Customer Dissatisfaction Narrative",
                "type": "Reputational"
            },
            "Regulatory Action": {
                "name": "Regulatory Scrutiny Narrative",
                "type": "Legal"
            },
            "Financial Results": {
                "name": "Financial Performance Narrative",
                "type": "Financial"
            },
            "Executive Leadership": {
                "name": "Executive Leadership Narrative",
                "type": "Reputational"
            },
            "Product Launch": {
                "name": "Product Launch Narrative",
                "type": "Operational"
            },
            "Legal Risk": {
                "name": "Legal Risk Narrative",
                "type": "Legal"
            },
            "Regulatory Risk": {
                "name": "Regulatory Scrutiny Narrative",
                "type": "Legal"
            },
            "Environmental": {
                "name": "Environmental & ESG Narrative",
                "type": "Reputational"
            },
            "Cybersecurity": {
                "name": "Cybersecurity Risk Narrative",
                "type": "Risk"
            },
            "Labor Relations": {
                "name": "Labor Relations Narrative",
                "type": "Operational"
            },
            "Mergers & Acquisitions": {
                "name": "M&A Narrative",
                "type": "Financial"
            },
            "Market Share": {
                "name": "Market Position Narrative",
                "type": "Competitive"
            },
            "Innovation": {
                "name": "Innovation Narrative",
                "type": "Reputational"
            },
            "Customer Satisfaction": {
                "name": "Customer Sentiment Narrative",
                "type": "Reputational"
            },
            "Safety Recall": {
                "name": "Safety Recall Narrative",
                "type": "Risk"
            },
            "Competition": {
                "name": "Competitive Landscape Narrative",
                "type": "Competitive"
            },
            "Electric Vehicles": {
                "name": "Electric Vehicle Narrative",
                "type": "Operational"
            },
            "Autonomous Driving": {
                "name": "Autonomous Driving Narrative",
                "type": "Operational"
            },
            "Energy Storage": {
                "name": "Energy Storage Narrative",
                "type": "Operational"
            }
        }

    def _determine_status(self, mention_count: int, trend_strength: float, is_emerging: bool) -> str:
        if is_emerging:
            return "EMERGING"
        if trend_strength < -10.0:
            return "DECLINING"
        elif mention_count > 50 and trend_strength > 10.0:
            return "PEAK"
        elif trend_strength > 50.0:
            return "GROWING"
        else:
            return "EMERGING"

    def _calculate_confidence_and_gate(
        self,
        doc_count: int,
        source_diversity: int,
        has_trend: bool,
        has_risk: bool,
        has_alert: bool
    ) -> Dict[str, Any]:
        doc_factor = min(doc_count / 5.0, 1.0)
        source_factor = min(source_diversity / 3.0, 1.0)
        
        trend_factor = 1.0 if has_trend else 0.0
        risk_factor = 1.0 if has_risk else 0.0
        alert_factor = 1.0 if has_alert else 0.0

        final_score = (
            0.20 * doc_factor +
            0.20 * source_factor +
            0.20 * trend_factor +
            0.20 * risk_factor +
            0.20 * alert_factor
        )

        evidence_score = (doc_count * 0.4) + (source_diversity * 0.2)
        if has_trend:
            evidence_score += 1.5
        if has_risk:
            evidence_score += 1.5
        if has_alert:
            evidence_score += 1.5
        # Multi-document corroboration bonus. A cluster of >=2 documents that
        # independent processing (title similarity or shared entities, see
        # the clustering step above) judged to be about the same real event
        # is itself real evidence, in the same spirit as the trend/risk/alert
        # bonuses above -- it just comes from document agreement rather than
        # a separate aggregation engine. Without this, a genuine 2-document
        # cluster with 1 source (0.4*2 + 0.2*1 = 1.0, sitting exactly on the
        # boundary) or 0 sources (0.8, below it) could never pass without one
        # of those three unrelated signals also firing. Singleton clusters
        # (doc_count == 1, evidence_score == 0.6 unless boosted) are
        # deliberately left ungated by this bonus -- weak, single-document
        # "narratives" should still fail evidence, same as before.
        if doc_count >= 2:
            evidence_score += 1.0

        is_emerging = not (has_trend or has_risk or has_alert)

        return {
            "final_score": round(final_score, 4),
            "evidence_score": round(evidence_score, 4),
            "is_emerging": is_emerging,
            "metrics": {
                "doc_factor": round(doc_factor, 4),
                "agreement_factor": round(source_factor, 4),
                "alert_factor": round(alert_factor, 4),
                "trend_factor": round(trend_factor, 4),
                "risk_factor": round(risk_factor, 4)
            }
        }

    def _generate_executive_summary(
        self,
        client_name: str,
        topic_name: str,
        doc_count: int,
        top_doc_title: str,
        avg_sentiment: float,
        trend_event: Optional[TrendEvent],
        risk_event: Optional[RiskEvent],
        alerts: List[Alert],
        narrative_type: str,
        status: str,
        confidence_score: float,
        entity_names: List[str],
        executives: List[str],
        competitors: List[str],
        is_emerging: bool
    ) -> str:
        entities_str = ", ".join(entity_names[:3])
        
        p1 = f"An intelligence narrative regarding '{topic_name}' has been detected for {client_name}, based on a cluster of {doc_count} articles."
        if executives:
            p1 += f" This coverage specifically highlights mentions of {', '.join(executives[:3])}."
        if competitors:
            p1 += f" The incident also involves competitor references to {', '.join(competitors[:3])}."
        p1 += f" The primary driver is the report: '{top_doc_title}'."

        p2_segments = []
        if trend_event:
            p2_segments.append(f"A confirmed trend event was detected with a change of {trend_event.percentage_change:.1f}%.")
        else:
            p2_segments.append("Recent media coverage indicates an emerging pattern, though no formal trend event has been established in the database.")

        if risk_event:
            p2_segments.append(f"This activity is associated with a risk score of {risk_event.risk_score:.1f}/100 (level: {risk_event.risk_level}).")
        else:
            p2_segments.append("Multiple negative articles were detected, but no formal risk event has been registered.")

        if alerts:
            max_sev = "INFO"
            severities = [a.severity for a in alerts]
            for sev in ["CRITICAL", "HIGH", "WARNING", "INFO"]:
                if sev in severities:
                    max_sev = sev
                    break
            p2_segments.append(f"This activity triggered {len(alerts)} active alerts (highest severity: {max_sev}).")
        else:
            p2_segments.append("No active intelligence alerts have been triggered for this incident.")

        if trend_event and risk_event and alerts:
            p2_segments.append("This represents a verified causal chain where negative sentiment drove a trend increase, escalating the risk profile and triggering active alerts.")
        else:
            p2_segments.append("A complete causal chain is not verified due to missing intermediate signals.")

        p2 = " ".join(p2_segments)

        if is_emerging:
            p3 = (
                f"As this is an emerging topic with limited multi-signal evidence, further tracking is required before escalating. "
                f"The narrative is currently classified as {status} with a business confidence score of {confidence_score:.2f}."
            )
        else:
            p3 = (
                f"Leadership attention is recommended under {narrative_type} tracking. "
                f"The narrative is currently classified as {status} (confidence score: {confidence_score:.2f}). "
                f"It is recommended that analysts monitor the situation, specifically focusing on {entities_str}."
            )

        return f"{p1}\n\n{p2}\n\n{p3}"

    def calculate_narratives(
        self,
        db: Session,
        client_id: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt: int = 0
    ):
        t0 = time.perf_counter()
        rid = run_id or uuid.uuid4().hex
        bid = batch_id or uuid.uuid4().hex[:12]
        wid = worker_id or str(os.getpid())

        log = logger.bind(
            run_id=rid,
            batch_id=bid,
            worker_id=wid,
            client_id=client_id,
            attempt=attempt,
            processing_stage="NARRATIVE_CALCULATION"
        )
        log.info("narrative_calculation_started")

        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            log.error("narrative_client_not_found")
            raise ValueError(f"Client {client_id} not found")

        # P3 — Batch Database Access: Preload client entities
        client_entities = db.query(Entity).filter(Entity.client_id == client_id).all()
        entity_ids = [e.id for e in client_entities]
        entity_names = [e.name for e in client_entities]
        
        if not entity_ids:
            log.info("narrative_no_entities_found", action="skipping")
            return

        # P3 — Batch Database Access: Preload all document IDs linked to these entities
        mentions = db.query(EntityMention).filter(EntityMention.entity_id.in_(entity_ids)).all()
        doc_ids = list(set(m.document_id for m in mentions))
        
        if not doc_ids:
            log.info("narrative_no_documents_found", action="skipping")
            return

        # P3 — Batch Database Access: Preload all related documents
        documents = db.query(Document).filter(Document.id.in_(doc_ids)).all()
        doc_map = {d.id: d for d in documents}

        # P3 — Batch Database Access: Preload all topic associations
        doc_topics = db.query(DocumentTopic).filter(DocumentTopic.document_id.in_(doc_ids)).all()
        topic_ids = list(set(dt.topic_id for dt in doc_topics))
        topics = db.query(Topic).filter(Topic.id.in_(topic_ids)).all()
        topic_map = {t.id: t for t in topics}

        # Map topic_id -> list of Document objects
        topic_docs_map = {}
        for dt in doc_topics:
            d = doc_map.get(dt.document_id)
            if d:
                topic_docs_map.setdefault(dt.topic_id, []).append(d)

        # P3 — Batch Database Access: Preload all sentiments
        sentiments = db.query(DocumentSentiment).filter(DocumentSentiment.document_id.in_(doc_ids)).all()
        sentiment_map = {s.document_id: s.sentiment_score for s in sentiments}

        # P3 — Batch Database Access: Preload all RiskEvents
        risks = db.query(RiskEvent).filter(
            RiskEvent.client_id == client_id,
            RiskEvent.document_id.in_(doc_ids)
        ).all()
        risk_map = {}
        for r in risks:
            risk_map.setdefault(r.document_id, []).append(r)

        # P3 — Batch Database Access: Preload all TrendEvents
        trends = db.query(TrendEvent).filter(
            TrendEvent.client_id == client_id,
            TrendEvent.trend_type == "Topic",
            TrendEvent.topic_id.in_(topic_ids)
        ).all()
        trend_map = {}
        for tr in trends:
            trend_map.setdefault(tr.topic_id, []).append(tr)

        # P3 — Batch Database Access: Preload all Alerts
        alerts = db.query(Alert).filter(
            Alert.client_id == client_id,
            Alert.document_id.in_(doc_ids)
        ).all()
        alert_map = {}
        for a in alerts:
            alert_map.setdefault(a.document_id, []).append(a)

        # P3 — Batch Database Access: Preload all EntityMentions (including Entity details) for these documents
        all_mentions = db.query(EntityMention).join(Entity).filter(
            EntityMention.document_id.in_(doc_ids)
        ).all()
        mention_map = {}
        for m in all_mentions:
            mention_map.setdefault(m.document_id, []).append(m)

        # P4 — Incident Cluster Optimization: Precompute and cache document title tokens
        token_cache = {}
        for d in documents:
            token_cache[d.id] = set(w.lower() for w in (d.title or "").split() if len(w) > 3)

        # Entity-overlap clustering signal, supplementing the title-Jaccard
        # check below. Two real news articles about the same event rarely
        # share 25% of their title words verbatim (confirmed live — with
        # only the title check, 108 real Tesla documents produced almost
        # entirely singleton clusters and zero narratives ever cleared the
        # evidence gate; see NLP_AUDIT_REPORT.md Part 4), but they do tend to
        # mention the same specific people/companies. The client's own brand
        # entity is excluded from this signal: since every document here was
        # matched to this client via that exact entity, it is present on
        # ~100% of documents and would collapse an entire topic into one
        # mega-cluster rather than distinguishing real events.
        brand_entity_id = next((e.id for e in client_entities if e.entity_type == "brand"), None)
        entity_cache = {}
        for d in documents:
            entity_cache[d.id] = {
                m.entity_id for m in mention_map.get(d.id, [])
                if m.entity_id != brand_entity_id
            }

        for topic_id, docs in topic_docs_map.items():
            topic = topic_map.get(topic_id)
            if not topic or not docs:
                continue

            # Sort documents by publication date to ensure identical incident grouping order
            docs.sort(key=lambda d: d.published_at or d.collected_at)

            # P4 — Incident Cluster Optimization: Time-window clustering using
            # cached title tokens AND shared (non-brand) matched entities.
            # Either signal alone is enough to cluster two documents together
            # -- title-Jaccard for cases with near-identical headlines,
            # entity-overlap for cases (the common real-world one) where
            # different outlets cover the same event with unrelated wording
            # but name the same person/competitor.
            incident_clusters = []
            for doc in docs:
                matched_cluster = None
                doc_tokens = token_cache.get(doc.id, set())
                doc_entities = entity_cache.get(doc.id, set())

                for cluster in incident_clusters:
                    ref_doc = cluster["ref_doc"]
                    time_diff = abs((doc.published_at or doc.collected_at) - (ref_doc.published_at or ref_doc.collected_at)).days

                    if time_diff <= 3:
                        ref_tokens = token_cache.get(ref_doc.id, set())
                        intersection = doc_tokens.intersection(ref_tokens)
                        union = doc_tokens.union(ref_tokens)
                        similarity = len(intersection) / len(union) if union else 0.0

                        ref_entities = entity_cache.get(ref_doc.id, set())
                        shares_entity = bool(doc_entities and ref_entities and (doc_entities & ref_entities))

                        if similarity >= 0.25 or shares_entity or (not doc_tokens and not ref_tokens):
                            matched_cluster = cluster
                            break

                if matched_cluster:
                    matched_cluster["documents"].append(doc)
                else:
                    incident_clusters.append({
                        "ref_doc": doc,
                        "documents": [doc]
                    })

            for idx, cluster in enumerate(incident_clusters):
                t_narrative_start = time.perf_counter()
                cluster_docs = cluster["documents"]
                cluster_doc_ids = [d.id for d in cluster_docs]
                top_doc_title = cluster["ref_doc"].title or "No Title Available"

                # Map topic to narrative name
                mapping = self.narrative_mapping.get(topic.name, {
                    "name": f"{topic.name} Narrative",
                    "type": "General"
                })
                
                if len(incident_clusters) > 1:
                    title_snippet = top_doc_title[:40] + "..." if len(top_doc_title) > 40 else top_doc_title
                    narrative_name = f"{mapping['name']} - {title_snippet}"
                else:
                    narrative_name = mapping["name"]
                    
                narrative_type = mapping["type"]

                # Calculate average sentiment from preloaded sentiment map
                s_scores = [sentiment_map[did] for did in cluster_doc_ids if did in sentiment_map]
                avg_sentiment = sum(s_scores) / len(s_scores) if s_scores else 0.0
                
                # Calculate Risk Score from preloaded risk map
                cluster_risks = []
                for did in cluster_doc_ids:
                    if did in risk_map:
                        cluster_risks.extend(risk_map[did])
                risk_ids = [str(r.id) for r in cluster_risks]
                risk_event = cluster_risks[0] if cluster_risks else None
                avg_risk = sum(r.risk_score for r in cluster_risks) / len(cluster_risks) if cluster_risks else 0.0
                
                # Retrieve Trend Event from preloaded trend map
                topic_trends = trend_map.get(topic_id, [])
                trend_event = None
                if topic_trends:
                    # Find latest trend event by created_at
                    trend_event = max(topic_trends, key=lambda tr: tr.created_at)
                trend_ids = [str(tr.id) for tr in topic_trends]
                trend_strength = trend_event.percentage_change if trend_event else 0.0

                # Retrieve Alerts from preloaded alert map
                cluster_alerts = []
                for did in cluster_doc_ids:
                    if did in alert_map:
                        cluster_alerts.extend(alert_map[did])
                alert_ids = [str(a.id) for a in cluster_alerts]

                # Extract Executive & Competitor Mentions from preloaded mention map
                executors = set()
                competitors = set()
                exec_ids = []
                for did in cluster_doc_ids:
                    for m in mention_map.get(did, []):
                        if m.entity.entity_type == "person":
                            executors.add(m.entity.name)
                            exec_ids.append(str(m.entity_id))
                        elif m.entity.entity_type == "competitor":
                            competitors.add(m.entity.name)

                # Calculate Confidence & Gate
                source_diversity = len(set(d.source_id for d in cluster_docs if d.source_id))
                confidence_data = self._calculate_confidence_and_gate(
                    doc_count=len(cluster_docs),
                    source_diversity=source_diversity,
                    has_trend=trend_event is not None,
                    has_risk=risk_event is not None,
                    has_alert=len(cluster_alerts) > 0
                )
                
                confidence_score = confidence_data["final_score"]
                evidence_score = confidence_data["evidence_score"]
                is_emerging = confidence_data["is_emerging"]

                # Gating threshold check
                if evidence_score < 1.0:
                    log.info("narrative_gated_insufficient_evidence", narrative_name=narrative_name, score=evidence_score)
                    continue

                status = self._determine_status(len(cluster_docs), trend_strength, is_emerging)

                # Generate summary text
                summary_text = self._generate_executive_summary(
                    client_name=client.name,
                    topic_name=topic.name,
                    doc_count=len(cluster_docs),
                    top_doc_title=top_doc_title,
                    avg_sentiment=float(avg_sentiment),
                    trend_event=trend_event,
                    risk_event=risk_event,
                    alerts=cluster_alerts,
                    narrative_type=narrative_type,
                    status=status,
                    confidence_score=confidence_score,
                    entity_names=entity_names,
                    executives=list(executors),
                    competitors=list(competitors),
                    is_emerging=is_emerging
                )

                # Lineage Metadata
                evidence_metadata = {
                    "supporting_documents": [str(did) for did in cluster_doc_ids],
                    "supporting_risks": risk_ids,
                    "supporting_trends": trend_ids,
                    "supporting_alerts": alert_ids,
                    "supporting_entities": [str(eid) for eid in entity_ids],
                    "supporting_topics": [str(topic_id)],
                    "supporting_executives": list(set(exec_ids)),
                    "confidence_calculation": confidence_data,
                    "decision_reason": f"Narrative generated with evidence score {evidence_score}.",
                    "evidence_counts": {
                        "documents": len(cluster_doc_ids),
                        "risks": len(risk_ids),
                        "trends": len(trend_ids),
                        "alerts": len(alert_ids),
                        "entities": len(entity_ids),
                        "executives": len(exec_ids)
                    }
                }

                elapsed_narrative_ms = (time.perf_counter() - t_narrative_start) * 1000

                # Save point nested transaction commit
                savepoint = db.begin_nested()
                try:
                    stmt = insert(Narrative).values(
                        id=uuid.uuid4(),
                        client_id=client_id,
                        narrative_name=narrative_name,
                        narrative_type=narrative_type,
                        mention_count=len(cluster_docs),
                        sentiment_score=float(avg_sentiment),
                        risk_score=float(avg_risk),
                        trend_strength=trend_strength,
                        status=status,
                        summary_text=summary_text,
                        confidence_score=confidence_score,
                        evidence_metadata=evidence_metadata,
                        run_id=rid,
                        batch_id=bid,
                        worker_id=wid,
                        latency_ms=elapsed_narrative_ms,
                        retry_count=attempt
                    ).on_conflict_do_update(
                        constraint="uq_client_narrative",
                        set_={
                            "mention_count": len(cluster_docs),
                            "sentiment_score": float(avg_sentiment),
                            "risk_score": float(avg_risk),
                            "trend_strength": trend_strength,
                            "status": status,
                            "summary_text": summary_text,
                            "confidence_score": confidence_score,
                            "evidence_metadata": evidence_metadata,
                            "run_id": rid,
                            "batch_id": bid,
                            "worker_id": wid,
                            "latency_ms": elapsed_narrative_ms,
                            "retry_count": attempt
                        }
                    )
                    db.execute(stmt)
                    savepoint.commit()
                except Exception as e:
                    savepoint.rollback()
                    log.error("narrative_savepoint_failed", error=str(e))

        elapsed_client_ms = (time.perf_counter() - t0) * 1000
        log.info("narrative_calculation_complete", total_latency_ms=round(elapsed_client_ms, 2))

    def process_client(
        self,
        db: Session,
        client_id: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt: int = 0
    ):
        self.calculate_narratives(
            db,
            client_id,
            run_id=run_id,
            batch_id=batch_id,
            worker_id=worker_id,
            attempt=attempt
        )
