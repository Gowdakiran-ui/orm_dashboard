from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class CitationItem(BaseModel):
    document_ids: List[str] = Field(default_factory=list)
    narrative_ids: List[str] = Field(default_factory=list)
    risk_ids: List[str] = Field(default_factory=list)
    alert_ids: List[str] = Field(default_factory=list)
    trend_ids: List[str] = Field(default_factory=list)

class CrisisActionItem(BaseModel):
    action: str
    priority: str  # HIGH, MEDIUM, LOW
    evidence_backing: str
    citations: CitationItem

class CrisisDriver(BaseModel):
    driver: str
    impact_score: float
    description: str
    citations: CitationItem

class StakeholderActionItem(BaseModel):
    stakeholder_group: str  # e.g. Customers, Investors, Employees
    strategy: str
    action_steps: List[str]
    citations: CitationItem
