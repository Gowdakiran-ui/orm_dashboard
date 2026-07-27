from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class CitationItem(BaseModel):
    document_ids: List[str] = Field(default_factory=list)
    narrative_ids: List[str] = Field(default_factory=list)
    risk_ids: List[str] = Field(default_factory=list)
    alert_ids: List[str] = Field(default_factory=list)
    trend_ids: List[str] = Field(default_factory=list)

class ActionItem(BaseModel):
    action: str
    priority: str  # HIGH, MEDIUM, LOW
    evidence_backing: str
    citations: CitationItem

class SignalItem(BaseModel):
    signal: str
    impact_score: float  # 0.0 to 10.0
    description: str
    citations: CitationItem

class ExecutiveAnalysisItem(BaseModel):
    executive_name: str
    score: float
    grade: str
    key_drivers: str
    citations: CitationItem

class CompetitorPositionItem(BaseModel):
    competitor_name: str
    rank: int
    share_of_voice: float
    reputation_score: float
    comparison_summary: str
    citations: CitationItem
