from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from uuid import UUID
from app.core.db import get_db
from app.models.executive_reputation import ExecutiveReputationScore

router = APIRouter()

@router.get("/{executive_id}/reputation", response_model=Dict[str, Any])
def get_executive_reputation(executive_id: UUID, db: Session = Depends(get_db)):
    rep = db.query(ExecutiveReputationScore).filter(ExecutiveReputationScore.entity_id == executive_id).order_by(ExecutiveReputationScore.created_at.desc()).first()
    if not rep:
        raise HTTPException(status_code=404, detail="Executive reputation not found")
    return {
        "score": rep.score,
        "grade": rep.grade,
        "trend": rep.reputation_trend,
        "top_positive_narrative": rep.top_positive_narrative,
        "top_negative_narrative": rep.top_negative_narrative
    }

@router.get("/{executive_id}/history", response_model=List[Dict[str, Any]])
def get_executive_reputation_history(executive_id: UUID, db: Session = Depends(get_db)):
    reps = db.query(ExecutiveReputationScore).filter(ExecutiveReputationScore.entity_id == executive_id).order_by(ExecutiveReputationScore.created_at.desc(), ExecutiveReputationScore.id.desc()).limit(30).all()
    return [{"date": r.created_at.isoformat() if r.created_at else None, "score": r.score} for r in reps]

@router.get("/{executive_id}/breakdown", response_model=Dict[str, Any])
def get_executive_reputation_breakdown(executive_id: UUID, db: Session = Depends(get_db)):
    rep = db.query(ExecutiveReputationScore).filter(ExecutiveReputationScore.entity_id == executive_id).order_by(ExecutiveReputationScore.created_at.desc()).first()
    if not rep: raise HTTPException(status_code=404, detail="Reputation not found")
    return {
        "sentiment": rep.sentiment_component,
        "risk": rep.risk_component,
        "narrative": rep.narrative_component,
        "trend": rep.trend_component,
        "visibility": rep.visibility_component
    }
