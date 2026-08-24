from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Dict, Any
from app.core.db import get_db
from app.models.client import Client
from app.models.trends import TrendEvent

router = APIRouter()

@router.get("/{client_id}/trend-events", response_model=List[Dict[str, Any]])
def get_client_trend_events(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    events = db.query(TrendEvent).filter(TrendEvent.client_id == client_id).order_by(TrendEvent.created_at.desc(), TrendEvent.id.desc()).limit(100).all()
    
    results = []
    for e in events:
        results.append({
            "id": str(e.id),
            "trend_type": e.trend_type,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "topic_id": str(e.topic_id) if e.topic_id else None,
            "baseline_value": e.baseline_value,
            "current_value": e.current_value,
            "percentage_change": e.percentage_change,
            "severity": e.severity,
            "created_at": e.created_at.isoformat() if e.created_at else None
        })
    return results

from app.models.risk import RiskEvent
from sqlalchemy import func

@router.get("/{client_id}/risks", response_model=Dict[str, Any])
def get_client_risks(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Aggregate risks (e.g. average risk score over last 30 days, or just recent events)
    recent_events = db.query(RiskEvent).filter(RiskEvent.client_id == client_id).order_by(RiskEvent.created_at.desc(), RiskEvent.id.desc()).limit(50).all()
    avg_score = sum(e.risk_score for e in recent_events) / len(recent_events) if recent_events else 0.0
    
    return {
        "client_id": str(client_id),
        "average_recent_risk_score": avg_score,
        "recent_critical_events": sum(1 for e in recent_events if e.risk_level == "CRITICAL"),
        "recent_high_events": sum(1 for e in recent_events if e.risk_level == "HIGH")
    }

from app.models.alert import Alert

@router.get("/{client_id}/active-alerts", response_model=List[Dict[str, Any]])
def get_client_active_alerts(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    alerts = db.query(Alert).filter(Alert.client_id == client_id, Alert.is_acknowledged == False).order_by(Alert.created_at.desc()).all()
    results = []
    for a in alerts:
        results.append({
            "id": str(a.id),
            "alert_type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "is_acknowledged": a.is_acknowledged,
            "created_at": a.created_at.isoformat() if a.created_at else None
        })
    return results

from app.models.narrative import Narrative

@router.get("/{client_id}/narratives", response_model=List[Dict[str, Any]])
def get_client_narratives(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    narratives = db.query(Narrative).filter(Narrative.client_id == client_id).order_by(Narrative.updated_at.desc()).all()
    results = [{
        "id": str(n.id),
        "name": n.narrative_name,
        "type": n.narrative_type,
        "mentions": n.mention_count,
        "sentiment": n.sentiment_score,
        "risk": n.risk_score,
        "trend": n.trend_strength,
        "status": n.status
    } for n in narratives]
    return results

@router.get("/{client_id}/top-narratives", response_model=List[Dict[str, Any]])
def get_client_top_narratives(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    narratives = db.query(Narrative).filter(Narrative.client_id == client_id).order_by(Narrative.mention_count.desc(), Narrative.id.desc()).limit(5).all()
    results = [{
        "id": str(n.id),
        "name": n.narrative_name,
        "status": n.status,
        "mentions": n.mention_count
    } for n in narratives]
    return results

from app.models.reputation import ReputationScore

@router.get("/{client_id}/reputation", response_model=Dict[str, Any])
def get_client_reputation(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    rep = db.query(ReputationScore).filter(ReputationScore.client_id == client_id).order_by(ReputationScore.created_at.desc(), ReputationScore.id.desc()).first()
    if not rep:
        return {
            "score": None,
            "grade": None,
            "trend": "INSUFFICIENT_DATA",
            "confidence_score": 0.0,
            "data_coverage": 0.0
        }
    return {
        "score": rep.score,
        "grade": rep.grade,
        "trend": rep.reputation_trend,
        "confidence_score": rep.confidence_score,
        "data_coverage": getattr(rep, "data_coverage", 0.40)
    }

@router.get("/{client_id}/reputation-history", response_model=List[Dict[str, Any]])
def get_client_reputation_history(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    reps = db.query(ReputationScore).filter(ReputationScore.client_id == client_id).order_by(ReputationScore.created_at.desc(), ReputationScore.id.desc()).limit(30).all()
    return [{
        "date": r.created_at.isoformat() if r.created_at else None,
        "score": r.score
    } for r in reps]

@router.get("/{client_id}/reputation-breakdown", response_model=Dict[str, Any])
def get_client_reputation_breakdown(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    rep = db.query(ReputationScore).filter(ReputationScore.client_id == client_id).order_by(ReputationScore.created_at.desc(), ReputationScore.id.desc()).first()
    if not rep:
        return {
            "sentiment": None,
            "risk": None,
            "narrative": None,
            "trend": None,
            "source": None,
            "visibility": None
        }
    return {
        "sentiment": rep.sentiment_component,
        "risk": rep.risk_component,
        "narrative": rep.narrative_component,
        "trend": rep.trend_component,
        "source": rep.source_component,
        "visibility": rep.visibility_component
    }

@router.get("/{client_id}/executives", response_model=List[Dict[str, Any]])
def get_client_executives(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.executive_reputation import ExecutiveReputationScore
    
    # Get latest score for each executive entity
    subq = db.query(
        ExecutiveReputationScore.entity_id,
        func.max(ExecutiveReputationScore.created_at).label("max_created")
    ).filter(ExecutiveReputationScore.client_id == client_id).group_by(ExecutiveReputationScore.entity_id).subquery()
    
    scores = db.query(ExecutiveReputationScore).join(
        subq,
        (ExecutiveReputationScore.entity_id == subq.c.entity_id) &
        (ExecutiveReputationScore.created_at == subq.c.max_created)
    ).all()
    
    return [{
        "id": str(s.id),
        "entity_id": str(s.entity_id),
        "name": s.executive_name,
        "score": s.score,
        "grade": s.grade,
        "trend": s.reputation_trend,
        "top_positive": s.top_positive_narrative,
        "top_negative": s.top_negative_narrative,
        "confidence_score": s.confidence_score,
        "data_coverage": s.data_coverage,
        "health_status": s.health_status
    } for s in scores]

@router.get("/{client_id}/executive-history", response_model=Dict[str, List[Dict[str, Any]]])
def get_client_executive_history(client_id: UUID, db: Session = Depends(get_db)):
    """
    Historical reputation score timeline per executive — the missing fetch
    behind the "Leadership Figures Reputation Trend" card (TASK.md Item 4).
    Mirrors get_client_reputation_history's shape but keyed by executive
    name, since the frontend plots one line per executive.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.executive_reputation import ExecutiveReputationScore

    # Cap at the last 30 points per executive via a row_number() partition
    # (same pattern as get_client_executives's latest-per-executive subquery
    # above) rather than a flat LIMIT, which would starve later executives
    # once an earlier one accumulates more than 30 rows.
    row_num = func.row_number().over(
        partition_by=ExecutiveReputationScore.entity_id,
        order_by=ExecutiveReputationScore.created_at.desc()
    ).label("row_num")
    subq = db.query(
        ExecutiveReputationScore.executive_name,
        ExecutiveReputationScore.score,
        ExecutiveReputationScore.created_at,
        row_num
    ).filter(ExecutiveReputationScore.client_id == client_id).subquery()

    rows = db.query(subq).filter(subq.c.row_num <= 30).order_by(subq.c.created_at.asc()).all()

    history: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        history.setdefault(r.executive_name, []).append({
            "date": r.created_at.isoformat() if r.created_at else None,
            "score": r.score
        })
    return history

from app.models.competitor_benchmark import CompetitorBenchmark

@router.get("/{client_id}/benchmark", response_model=List[Dict[str, Any]])
def get_client_benchmark(
    client_id: UUID,
    response: Response,
    limit: int = Query(25, ge=1, le=200, description="Max competitors to return (SQL-level pagination, not a client-side truncation)."),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.entity import Entity

    # B1/B5: latest row per competitor is now selected at the SQL level (same
    # pattern as get_client_executives above), instead of loading every
    # historical row for the client and deduplicating in Python. Previously
    # this loaded the client's full competitor_benchmarks history (e.g. 180
    # rows for Tesla) to return 10.
    latest_sub = db.query(
        CompetitorBenchmark.competitor_entity_id,
        func.max(CompetitorBenchmark.created_at).label("max_created")
    ).filter(CompetitorBenchmark.client_id == client_id).group_by(
        CompetitorBenchmark.competitor_entity_id
    ).subquery()

    base_query = db.query(CompetitorBenchmark, Entity).join(
        Entity, Entity.id == CompetitorBenchmark.competitor_entity_id
    ).join(
        latest_sub,
        (CompetitorBenchmark.competitor_entity_id == latest_sub.c.competitor_entity_id) &
        (CompetitorBenchmark.created_at == latest_sub.c.max_created)
    ).filter(CompetitorBenchmark.client_id == client_id)

    # B1: the old cap of 10 silently dropped Tesla's 11th competitor with no
    # signal to the caller. Total count is now exposed via a response header
    # so a truncated page is visible rather than silent; `limit`/`offset`
    # give a real pagination mechanism instead of a bigger magic number.
    total_count = base_query.count()
    response.headers["X-Total-Count"] = str(total_count)

    benchmarks = base_query.order_by(CompetitorBenchmark.created_at.desc()).offset(offset).limit(limit).all()

    if not benchmarks:
        # B3: the engine's own skip threshold (calculate_competitor_benchmarks)
        # is `len(competitors) < 1` — align the endpoint's sentinel to the same
        # threshold instead of a stricter local `< 2` that disagreed with it.
        competitor_count = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "competitor"
        ).count()

        if competitor_count < 1:
            return [{"message": "No competitor intelligence available."}]

    return [{
        "id": str(b.CompetitorBenchmark.id),
        "competitor_id": str(b.CompetitorBenchmark.competitor_entity_id),
        "competitor_name": b.Entity.name,
        "rank": b.CompetitorBenchmark.rank,
        "sov": b.CompetitorBenchmark.share_of_voice,
        "reputation": b.CompetitorBenchmark.reputation_score,
        "sentiment": b.CompetitorBenchmark.sentiment_score,
        "risk": b.CompetitorBenchmark.risk_score,
        "visibility": b.CompetitorBenchmark.visibility_score,
        # B2: already computed and stored by BenchmarkEngine, same propagation
        # gap the P2-A fix closed for get_client_executives above.
        "health_status": b.CompetitorBenchmark.health_status,
        "confidence_score": b.CompetitorBenchmark.confidence_score,
        "data_coverage": b.CompetitorBenchmark.data_coverage,
        "top_narrative": b.CompetitorBenchmark.top_narrative
    } for b in benchmarks]

@router.get("/{client_id}/share-of-voice", response_model=List[Dict[str, Any]])
def get_client_sov(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.entity import Entity
    benchmarks_raw = db.query(CompetitorBenchmark).filter(CompetitorBenchmark.client_id == client_id).order_by(CompetitorBenchmark.created_at.desc()).all()
    
    # Deduplicate in Python keeping the first one seen (which is the latest due to DESC order)
    seen_competitors = set()
    benchmarks = []
    for b in benchmarks_raw:
        comp_id = b.competitor_entity_id
        if comp_id not in seen_competitors:
            seen_competitors.add(comp_id)
            benchmarks.append(b)
            if len(benchmarks) >= 10:
                break
    
    if not benchmarks:
        # Check if there are any competitor entities at all
        competitor_count = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "competitor"
        ).count()
        
        if competitor_count < 2:
            return [{"message": "No competitor intelligence available."}]
    
    return [{"competitor_id": str(b.competitor_entity_id), "sov": b.share_of_voice} for b in benchmarks]

@router.get("/{client_id}/competitive-summary", response_model=Dict[str, Any])
def get_client_competitive_summary(client_id: UUID, db: Session = Depends(get_db)):
    """
    Compact competitive summary (count, average reputation, top competitor,
    client's own rank), built from the same latest-per-competitor
    CompetitorBenchmark query pattern as get_client_benchmark above.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.entity import Entity

    latest_sub = db.query(
        CompetitorBenchmark.competitor_entity_id,
        func.max(CompetitorBenchmark.created_at).label("max_created")
    ).filter(CompetitorBenchmark.client_id == client_id).group_by(
        CompetitorBenchmark.competitor_entity_id
    ).subquery()

    benchmarks = db.query(CompetitorBenchmark, Entity).join(
        Entity, Entity.id == CompetitorBenchmark.competitor_entity_id
    ).join(
        latest_sub,
        (CompetitorBenchmark.competitor_entity_id == latest_sub.c.competitor_entity_id) &
        (CompetitorBenchmark.created_at == latest_sub.c.max_created)
    ).filter(CompetitorBenchmark.client_id == client_id).all()

    if not benchmarks:
        return {
            "competitor_count": 0,
            "avg_competitor_reputation": None,
            "top_competitor": None,
            "client_rank": None
        }

    reps = [b.CompetitorBenchmark.reputation_score for b in benchmarks if b.CompetitorBenchmark.reputation_score is not None]
    top = max(benchmarks, key=lambda b: b.CompetitorBenchmark.reputation_score or 0)

    # Client's own rank among these competitors -- 1 + count of competitors
    # with a strictly higher reputation score, matching the frontend's own
    # definition (useAnalytics.ts's clientRankValue) since CompetitorBenchmark.rank
    # is a competitor-to-competitor ranking and doesn't include the client itself.
    rep = db.query(ReputationScore).filter(ReputationScore.client_id == client_id).order_by(
        ReputationScore.created_at.desc(), ReputationScore.id.desc()
    ).first()
    client_rank = None
    if rep and rep.score is not None:
        higher_count = sum(1 for r in reps if r > rep.score)
        client_rank = higher_count + 1

    return {
        "competitor_count": len(benchmarks),
        "avg_competitor_reputation": sum(reps) / len(reps) if reps else None,
        "top_competitor": {
            "name": top.Entity.name,
            "reputation_score": top.CompetitorBenchmark.reputation_score
        },
        "client_rank": client_rank
    }

@router.get("/{client_id}/executive-candidates", response_model=List[Dict[str, Any]])
def get_client_executive_candidates(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.executive_candidate import ExecutiveCandidate
    
    candidates = db.query(ExecutiveCandidate).filter(
        ExecutiveCandidate.client_id == client_id,
        ExecutiveCandidate.promoted_to_executive_id.is_(None)
    ).order_by(ExecutiveCandidate.mention_count.desc(), ExecutiveCandidate.confidence.desc()).limit(500).all()
    
    return [{
        "id": str(c.id),
        "name": c.name,
        "organization": c.organization,
        "mention_count": c.mention_count,
        "first_seen": c.first_seen.isoformat() if c.first_seen else None,
        "last_seen": c.last_seen.isoformat() if c.last_seen else None,
        "confidence": c.confidence,
        "source_document_count": len(c.source_documents) if c.source_documents else 0
    } for c in candidates]

@router.get("/{client_id}/competitor-candidates", response_model=List[Dict[str, Any]])
def get_client_competitor_candidates(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.competitor_candidate import CompetitorCandidate
    
    candidates = db.query(CompetitorCandidate).filter(
        CompetitorCandidate.client_id == client_id,
        CompetitorCandidate.promoted_to_competitor_id.is_(None)
    ).order_by(CompetitorCandidate.mention_count.desc(), CompetitorCandidate.confidence.desc()).limit(500).all()
    
    return [{
        "id": str(c.id),
        "organization_name": c.organization_name,
        "mention_count": c.mention_count,
        "first_seen": c.first_seen.isoformat() if c.first_seen else None,
        "last_seen": c.last_seen.isoformat() if c.last_seen else None,
        "confidence": c.confidence,
        "source_document_count": len(c.source_documents) if c.source_documents else 0
    } for c in candidates]

@router.post("/{client_id}/promote-competitors", response_model=Dict[str, Any])
def promote_competitor_candidates(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.services.intelligence.entity_discovery import entity_discovery_engine
    
    result = entity_discovery_engine.promote_competitor_candidates(db, str(client_id))
    
    # Refresh matching engine after promotion
    from app.services.matching_engine import engine_instance
    engine_instance.refresh_processor(db)
    
    return result

@router.post("/{client_id}/promote-executives", response_model=Dict[str, Any])
def promote_executive_candidates(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.services.intelligence.entity_discovery import entity_discovery_engine
    
    result = entity_discovery_engine.promote_executive_candidates(db, str(client_id))
    
    # Refresh matching engine after promotion
    from app.services.matching_engine import engine_instance
    engine_instance.refresh_processor(db)
    
    return result

@router.get("/{client_id}/telemetry", response_model=Dict[str, Any])
def get_client_telemetry(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    from app.models.document import Document, DocumentMatch
    from app.models.entity import Entity, EntityMention
    from app.models.topic import DocumentTopic
    from app.models.sentiment import DocumentSentiment
    from app.models.trends import TrendEvent
    from app.models.risk import RiskEvent
    from app.models.alert import Alert
    from app.models.narrative import Narrative
    from app.models.reputation import ReputationScore
    from app.models.executive_reputation import ExecutiveReputationScore
    from app.models.competitor_benchmark import CompetitorBenchmark
    
    docs = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Entity.client_id == client_id
    ).distinct().all()
    
    def format_dt(dt):
        return dt.isoformat() if dt else None
        
    # 1. Entity Matching
    matching_processed = len(docs)
    matching_failed = sum(1 for d in docs if d.processing_status == "FAILED")
    matching_success = matching_processed - matching_failed
    matching_success_rate = f"{(matching_success / matching_processed * 100):.1f}%" if matching_processed > 0 else "N/A"
    matching_times = [d.match_processing_time_ms for d in docs if d.match_processing_time_ms]
    matching_avg_time = sum(matching_times) / len(matching_times) if matching_times else 0.0
    matching_last_run = format_dt(max((d.match_failed_at or d.collected_at) for d in docs if (d.match_failed_at or d.collected_at))) if docs else None

    # 2. Topic Classification
    topic_processed = sum(1 for d in docs if d.topic_processing_status != "PENDING")
    topic_failed = sum(1 for d in docs if d.topic_processing_status == "FAILED")
    topic_success = topic_processed - topic_failed
    topic_success_rate = f"{(topic_success / topic_processed * 100):.1f}%" if topic_processed > 0 else "N/A"
    topic_times = [d.topic_processing_time_ms for d in docs if d.topic_processing_time_ms]
    topic_avg_time = sum(topic_times) / len(topic_times) if topic_times else 0.0
    topic_last_run = format_dt(max((d.topic_failed_at or d.collected_at) for d in docs if (d.topic_failed_at or d.collected_at))) if docs else None

    # 3. Sentiment Analysis
    sentiment_processed = sum(1 for d in docs if d.sentiment_processing_status != "SENTIMENT_PENDING")
    sentiment_failed = sum(1 for d in docs if d.sentiment_processing_status == "FAILED")
    sentiment_success = sentiment_processed - sentiment_failed
    sentiment_success_rate = f"{(sentiment_success / sentiment_processed * 100):.1f}%" if sentiment_processed > 0 else "N/A"
    sentiment_times = [d.sentiment_processing_time_ms for d in docs if d.sentiment_processing_time_ms]
    sentiment_avg_time = sum(sentiment_times) / len(sentiment_times) if sentiment_times else 0.0
    sentiment_last_run = format_dt(max((d.sentiment_failed_at or d.collected_at) for d in docs if (d.sentiment_failed_at or d.collected_at))) if docs else None

    # 4. Trend Detection
    trends = db.query(TrendEvent).filter(TrendEvent.client_id == client_id).all()
    trend_produced = len(trends)
    trend_last_run = format_dt(max(t.created_at for t in trends)) if trends else None

    # 5. Risk Engine
    risks = db.query(RiskEvent).filter(RiskEvent.client_id == client_id).all()
    risk_produced = len(risks)
    risk_last_run = format_dt(max(r.created_at for r in risks)) if risks else None

    # 6. Alert Engine
    alerts = db.query(Alert).filter(Alert.client_id == client_id).all()
    alert_produced = len(alerts)
    alert_last_run = format_dt(max(a.created_at for a in alerts)) if alerts else None

    # 7. Narrative Engine
    narratives = db.query(Narrative).filter(Narrative.client_id == client_id).all()
    narrative_produced = len(narratives)
    narrative_last_run = format_dt(max(n.updated_at for n in narratives)) if narratives else None

    # 8. Reputation Engine
    reps = db.query(ReputationScore).filter(ReputationScore.client_id == client_id).all()
    rep_produced = len(reps)
    rep_times = [r.latency_ms for r in reps if r.latency_ms]
    rep_avg_time = sum(rep_times) / len(rep_times) if rep_times else 0.0
    rep_last_run = format_dt(max(r.created_at for r in reps)) if reps else None

    # 9. Executive Reputation Engine
    exec_reps = db.query(ExecutiveReputationScore).filter(ExecutiveReputationScore.client_id == client_id).all()
    exec_rep_produced = len(exec_reps)
    exec_rep_times = [er.latency_ms for er in exec_reps if er.latency_ms]
    exec_rep_avg_time = sum(exec_rep_times) / len(exec_rep_times) if exec_rep_times else 0.0
    exec_rep_last_run = format_dt(max(er.created_at for er in exec_reps)) if exec_reps else None

    # 10. Benchmark Engine
    benchmarks = db.query(CompetitorBenchmark).filter(CompetitorBenchmark.client_id == client_id).all()
    benchmark_produced = len(benchmarks)
    benchmark_times = [b.latency_ms for b in benchmarks if b.latency_ms]
    benchmark_avg_time = sum(benchmark_times) / len(benchmark_times) if benchmark_times else 0.0
    benchmark_last_run = format_dt(max(b.created_at for b in benchmarks)) if benchmarks else None

    return {
        "matching": {
            "processed": matching_processed,
            "failed": matching_failed,
            "success_rate": matching_success_rate,
            "avg_time_ms": matching_avg_time,
            "last_run": matching_last_run
        },
        "topic": {
            "processed": topic_processed,
            "failed": topic_failed,
            "success_rate": topic_success_rate,
            "avg_time_ms": topic_avg_time,
            "last_run": topic_last_run
        },
        "sentiment": {
            "processed": sentiment_processed,
            "failed": sentiment_failed,
            "success_rate": sentiment_success_rate,
            "avg_time_ms": sentiment_avg_time,
            "last_run": sentiment_last_run
        },
        "trend": {
            "produced": trend_produced,
            "last_run": trend_last_run
        },
        "risk": {
            "produced": risk_produced,
            "last_run": risk_last_run
        },
        "alert": {
            "produced": alert_produced,
            "last_run": alert_last_run
        },
        "narrative": {
            "produced": narrative_produced,
            "last_run": narrative_last_run
        },
        "reputation": {
            "produced": rep_produced,
            "avg_time_ms": rep_avg_time,
            "last_run": rep_last_run
        },
        "exec_reputation": {
            "produced": exec_rep_produced,
            "avg_time_ms": exec_rep_avg_time,
            "last_run": exec_rep_last_run
        },
        "benchmark": {
            "produced": benchmark_produced,
            "avg_time_ms": benchmark_avg_time,
            "last_run": benchmark_last_run
        }
    }