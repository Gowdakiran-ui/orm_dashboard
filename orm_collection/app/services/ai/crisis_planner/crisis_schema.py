from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.services.ai.crisis_planner.crisis_models import (
    CitationItem, CrisisActionItem, CrisisDriver, StakeholderActionItem
)

class CrisisPlanResponse(BaseModel):
    executive_summary: str
    current_assessment: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    key_drivers: List[CrisisDriver] = Field(default_factory=list)
    business_impact: str
    immediate_actions_24h: List[CrisisActionItem] = Field(default_factory=list)
    short_term_actions_72h: List[CrisisActionItem] = Field(default_factory=list)
    medium_term_actions_7d: List[CrisisActionItem] = Field(default_factory=list)
    executive_communication: str
    public_communication_strategy: str
    stakeholder_actions: List[StakeholderActionItem] = Field(default_factory=list)
    monitoring_priorities: List[str] = Field(default_factory=list)
    success_metrics: List[str] = Field(default_factory=list)
    confidence: float
    coverage: float
    citations: CitationItem
    metadata: Dict[str, Any] = Field(default_factory=dict)
