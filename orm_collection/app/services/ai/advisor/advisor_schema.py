from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.services.ai.advisor.advisor_models import (
    CitationItem, ActionItem, SignalItem, ExecutiveAnalysisItem, CompetitorPositionItem
)

class ReputationAdvisorResponse(BaseModel):
    overall_assessment: str
    executive_summary: str
    current_reputation: str
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    major_risks: List[ActionItem] = Field(default_factory=list)
    positive_signals: List[SignalItem] = Field(default_factory=list)
    negative_signals: List[SignalItem] = Field(default_factory=list)
    executive_analysis: List[ExecutiveAnalysisItem] = Field(default_factory=list)
    competitor_position: List[CompetitorPositionItem] = Field(default_factory=list)
    trend_analysis: str
    priority_actions_24h: List[ActionItem] = Field(default_factory=list)
    priority_actions_7d: List[ActionItem] = Field(default_factory=list)
    priority_actions_30d: List[ActionItem] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    predicted_business_impact: str
    confidence: float  # 0.0 to 1.0 (corresponds to model confidence)
    coverage: float    # 0.0 to 100.0 (corresponds to data coverage)
    limitations: List[str] = Field(default_factory=list)
    citations: CitationItem
    metadata: Dict[str, Any] = Field(default_factory=dict)
