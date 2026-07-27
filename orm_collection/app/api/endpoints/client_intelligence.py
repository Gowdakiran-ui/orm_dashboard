from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Dict, Any
from app.core.db import get_db
from app.models.client import Client
from app.models.trends import TrendEvent

router = APIRouter()

@router.get("/{client_id}/trends", response_model=Dict[str, Any])
def get_client_trends(client_id: UUID, db: Session = Depends(get_db)):
    """
    @deprecated
    Unused by current dashboard. Preserved for future trend analytics expansion.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get recent trends
    events = db.query(TrendEvent).filter(TrendEvent.client_id == client_id).order_by(TrendEvent.created_at.desc(), TrendEvent.id.desc()).limit(20).all()
    
    # Organize by type
    mention_trends = [{"entity_id": str(e.entity_id), "percentage_change": e.percentage_change, "severity": e.severity} for e in events if e.trend_type == "Mention"]
    topic_trends = [{"topic_id": str(e.topic_id), "percentage_change": e.percentage_change, "severity": e.severity} for e in events if e.trend_type == "Topic"]
    sentiment_trends = [{"percentage_change": e.percentage_change, "severity": e.severity} for e in events if e.trend_type == "Sentiment"]

    return {
        "client_id": str(client.id),
        "mention_trends": mention_trends,
        "topic_trends": topic_trends,
        "sentiment_trends": sentiment_trends
    }

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

@router.get("/{client_id}/risk-events", response_model=List[Dict[str, Any]])
def get_client_risk_events(client_id: UUID, db: Session = Depends(get_db)):
    """
    @deprecated
    Unused by current dashboard. Kept for future detailed risk timeline features.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    events = db.query(RiskEvent).filter(RiskEvent.client_id == client_id).order_by(RiskEvent.created_at.desc(), RiskEvent.id.desc()).limit(100).all()
    results = []
    for e in events:
        results.append({
            "id": str(e.id),
            "document_id": str(e.document_id) if e.document_id else None,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "risk_score": e.risk_score,
            "risk_level": e.risk_level,
            "confidence_score": e.confidence_score,
            "risk_factors": e.risk_factors,
            "created_at": e.created_at.isoformat() if e.created_at else None
        })
    return results

from app.models.alert import Alert

@router.get("/{client_id}/alerts", response_model=List[Dict[str, Any]])
def get_client_alerts(client_id: UUID, db: Session = Depends(get_db)):
    """
    @deprecated
    Unused by current dashboard (active-alerts used instead). Kept for historical alert log features.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    alerts = db.query(Alert).filter(Alert.client_id == client_id).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(100).all()
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

@router.get("/{client_id}/narrative-summary", response_model=Dict[str, Any])
def get_client_narrative_summary(client_id: UUID, db: Session = Depends(get_db)):
    """
    @deprecated
    Unused by current dashboard. Maintained for future top-level narrative reporting.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    narratives = db.query(Narrative).filter(Narrative.client_id == client_id).all()
    return {
        "total": len(narratives),
        "emerging": sum(1 for n in narratives if n.status == "EMERGING"),
        "peak": sum(1 for n in narratives if n.status == "PEAK")
    }

from app.models.reputation import ReputationScore

@router.get("/{client_id}/reputation", response_model=Dict[str, Any])
def get_client_reputation(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    rep = db.query(ReputationScore).filter(ReputationScore.client_id == client_id).order_by(ReputationScore.created_at.desc()).first()
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
    rep = db.query(ReputationScore).filter(ReputationScore.client_id == client_id).order_by(ReputationScore.created_at.desc()).first()
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
        "data_coverage": s.data_coverage
    } for s in scores]

from app.models.competitor_benchmark import CompetitorBenchmark

@router.get("/{client_id}/benchmark", response_model=List[Dict[str, Any]])
def get_client_benchmark(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.entity import Entity
    benchmarks_raw = db.query(CompetitorBenchmark, Entity).join(
        Entity, Entity.id == CompetitorBenchmark.competitor_entity_id
    ).filter(CompetitorBenchmark.client_id == client_id).order_by(CompetitorBenchmark.created_at.desc()).all()
    
    # Deduplicate in Python keeping the first one seen (which is the latest due to DESC order)
    seen_competitors = set()
    benchmarks = []
    for b in benchmarks_raw:
        comp_id = b.CompetitorBenchmark.competitor_entity_id
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
    
    return [{
        "id": str(b.CompetitorBenchmark.id),
        "competitor_id": str(b.CompetitorBenchmark.competitor_entity_id),
        "competitor_name": b.Entity.name,
        "rank": b.CompetitorBenchmark.rank,
        "sov": b.CompetitorBenchmark.share_of_voice,
        "reputation": b.CompetitorBenchmark.reputation_score,
        "sentiment": b.CompetitorBenchmark.sentiment_score,
        "risk": b.CompetitorBenchmark.risk_score,
        "visibility": b.CompetitorBenchmark.visibility_score
    } for b in benchmarks]

@router.get("/{client_id}/competitors", response_model=List[Dict[str, Any]])
def get_client_competitors(client_id: UUID, db: Session = Depends(get_db)):
    """
    @deprecated
    Unused by current dashboard. Retained for future competitor list management features.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.entity import Entity
    competitors = db.query(Entity).filter(
        Entity.client_id == client_id,
        Entity.entity_type == "competitor"
    ).all()
    
    if not competitors or len(competitors) < 2:
        return [{"message": "No competitor intelligence available."}]
    
    return [{"id": str(e.id), "name": e.name} for e in competitors]

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
    TODO: Implement competitive summary analytics.
    Currently a stub returning {"status": "ok"}.
    Disabled/Unused pending full implementation using existing Postgres data.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"status": "ok"}

@router.get("/{client_id}/reputation-advice", response_model=Dict[str, Any])
def get_client_reputation_advice(
    client_id: UUID,
    mode: str = "standard",
    temperature: float = 0.0,
    db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.services.ai.advisor.reputation_advisor import ReputationAdvisor
    advisor = ReputationAdvisor()
    return advisor.generate_reputation_advice(db, str(client_id), mode=mode, temperature=temperature)

@router.get("/{client_id}/crisis-plan", response_model=Dict[str, Any])
def get_client_crisis_plan(
    client_id: UUID,
    mode: str = "standard",
    temperature: float = 0.0,
    db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.services.ai.crisis_planner.crisis_planner import CrisisPlanner
    planner = CrisisPlanner()
    return planner.generate_crisis_plan(db, str(client_id), mode=mode, temperature=temperature)

@router.get("/{client_id}/executive-candidates", response_model=List[Dict[str, Any]])
def get_client_executive_candidates(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models.executive_candidate import ExecutiveCandidate
    
    candidates = db.query(ExecutiveCandidate).filter(
        ExecutiveCandidate.client_id == client_id,
        ExecutiveCandidate.promoted_to_executive_id.is_(None)
    ).order_by(ExecutiveCandidate.mention_count.desc(), ExecutiveCandidate.confidence.desc()).all()
    
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
    ).order_by(CompetitorCandidate.mention_count.desc(), CompetitorCandidate.confidence.desc()).all()
    
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