from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from uuid import UUID
from app.core.db import get_db
from app.models.alert import Alert

router = APIRouter()

@router.post("/{alert_id}/acknowledge", response_model=Dict[str, Any])
def acknowledge_alert(alert_id: UUID, client_id: UUID, db: Session = Depends(get_db)):
    # Scoped by client_id (FINAL.md #2) — previously any caller could
    # acknowledge (silence) any client's alert by iterating alert UUIDs.
    # Matches the scoping pattern already used in
    # client_intelligence.py's get_client_active_alerts.
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.client_id == client_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    alert.is_acknowledged = True
    db.commit()
    
    return {"status": "success", "alert_id": str(alert_id), "is_acknowledged": True}
