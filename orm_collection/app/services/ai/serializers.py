from datetime import datetime
from typing import Any, Dict, List, Optional

def serialize_client(client) -> Dict[str, Any]:
    if not client:
        return {}
    return {
        "id": str(client.id),
        "name": client.name,
        "industry": client.industry,
        "created_at": client.created_at
    }

def serialize_entity(entity) -> Dict[str, Any]:
    if not entity:
        return {}
    return {
        "id": str(entity.id),
        "name": entity.name,
        "entity_type": entity.entity_type,
        "industry": entity.industry
    }

def serialize_reputation(rep) -> Dict[str, Any]:
    if not rep:
        return {}
    return {
        "score": rep.score,
        "grade": rep.grade,
        "sentiment_component": rep.sentiment_component,
        "risk_component": rep.risk_component,
        "narrative_component": rep.narrative_component,
        "trend_component": rep.trend_component,
        "source_component": rep.source_component,
        "visibility_component": rep.visibility_component,
        "confidence_score": rep.confidence_score,
        "reputation_trend": rep.reputation_trend,
        "health_status": rep.health_status,
        "calculation_lineage": rep.calculation_lineage or {}
    }

def serialize_executive_reputation(score) -> Dict[str, Any]:
    if not score:
        return {}
    return {
        "id": str(score.id),
        "executive_name": score.executive_name,
        "score": score.score,
        "grade": score.grade,
        "reputation_trend": score.reputation_trend,
        "health_status": score.health_status
    }

def serialize_benchmark(bench, competitor_name: str) -> Dict[str, Any]:
    if not bench:
        return {}
    return {
        "competitor_name": competitor_name,
        "rank": bench.rank,
        "share_of_voice": bench.share_of_voice,
        "reputation_score": bench.reputation_score,
        "executive_reputation_score": bench.executive_reputation_score,
        "top_narrative": bench.top_narrative
    }

def serialize_risk_event(risk) -> Dict[str, Any]:
    if not risk:
        return {}
    return {
        "id": str(risk.id),
        "risk_score": risk.risk_score,
        "risk_level": risk.risk_level,
        "confidence_score": risk.confidence_score,
        "risk_factors": risk.risk_factors or []
    }

def serialize_alert(alert) -> Dict[str, Any]:
    if not alert:
        return {}
    return {
        "id": str(alert.id),
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "title": alert.title
    }

def serialize_narrative(narrative) -> Dict[str, Any]:
    if not narrative:
        return {}
    return {
        "id": str(narrative.id),
        "narrative_name": narrative.narrative_name,
        "narrative_type": narrative.narrative_type,
        "mention_count": narrative.mention_count,
        "sentiment_score": narrative.sentiment_score,
        "risk_score": narrative.risk_score,
        "trend_strength": narrative.trend_strength,
        "status": narrative.status
    }

def serialize_trend_event(trend) -> Dict[str, Any]:
    if not trend:
        return {}
    return {
        "id": str(trend.id),
        "trend_type": trend.trend_type,
        "percentage_change": trend.percentage_change,
        "severity": trend.severity
    }

def serialize_document(doc, sentiment_score: Optional[float] = None, topic_name: Optional[str] = None) -> Dict[str, Any]:
    if not doc:
        return {}
    return {
        "id": str(doc.id),
        "title": doc.title,
        "url": doc.url,
        "published_at": doc.published_at,
        "sentiment_score": sentiment_score,
        "topic_name": topic_name
    }
