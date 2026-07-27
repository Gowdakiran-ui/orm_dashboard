from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class ClientContext(BaseModel):
    id: str
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    ticker_symbol: Optional[str] = None
    created_at: datetime

class EntityContext(BaseModel):
    id: str
    name: str
    entity_type: str
    industry: Optional[str] = None

class ReputationContext(BaseModel):
    score: Optional[float] = None
    grade: Optional[str] = None
    sentiment_component: Optional[float] = None
    risk_component: Optional[float] = None
    narrative_component: Optional[float] = None
    trend_component: Optional[float] = None
    source_component: Optional[float] = None
    visibility_component: Optional[float] = None
    confidence_score: Optional[float] = None
    reputation_trend: Optional[str] = None
    health_status: Optional[str] = None
    calculation_lineage: Optional[Dict[str, Any]] = None

class ExecutiveReputationContext(BaseModel):
    id: str
    executive_name: str
    score: Optional[float] = None
    grade: Optional[str] = None
    reputation_trend: Optional[str] = None
    health_status: Optional[str] = None


class BenchmarkContext(BaseModel):
    competitor_name: str
    rank: int
    share_of_voice: float
    reputation_score: float
    executive_reputation_score: float
    top_narrative: Optional[str] = None

class RiskEventContext(BaseModel):
    id: str
    risk_score: float
    risk_level: str
    confidence_score: float
    risk_factors: List[Dict[str, Any]]

class AlertContext(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str

class NarrativeContext(BaseModel):
    id: str
    narrative_name: str
    narrative_type: str
    mention_count: int
    sentiment_score: float
    risk_score: float
    trend_strength: float
    status: str

class TrendEventContext(BaseModel):
    id: str
    trend_type: str
    percentage_change: float
    severity: str

class DocumentContext(BaseModel):
    id: str
    title: Optional[str] = None
    url: str
    published_at: Optional[datetime] = None
    sentiment_score: Optional[float] = None
    topic_name: Optional[str] = None

class ContextStats(BaseModel):
    documents_loaded: int
    risks_loaded: int
    alerts_loaded: int
    narratives_loaded: int
    trends_loaded: int
    executives_loaded: int
    benchmarks_loaded: int
    payload_size_kb: float
    estimated_tokens: int
    actual_tokens: Optional[int] = None
    compression_ratio: float
    context_build_latency: float

class DataCoverage(BaseModel):
    coverage_score: float
    coverage_reason: str
    missing_sources: List[str]
    enabled_sources: List[str]

class ContextMetadata(BaseModel):
    context_version: str
    pipeline_version: str
    generated_at: datetime
    aggregation_run_id: Optional[str] = None
    build_duration_ms: float
    context_uuid: str
    client_last_refresh: Optional[datetime] = None
    stats: ContextStats
    data_coverage: DataCoverage
    context_quality: str  # HIGH, MEDIUM, LOW

class AIContextPayload(BaseModel):
    client: ClientContext
    reputation: Optional[ReputationContext] = None
    entities: List[EntityContext] = Field(default_factory=list)
    executives: List[ExecutiveReputationContext] = Field(default_factory=list)
    benchmarks: List[BenchmarkContext] = Field(default_factory=list)
    risks: List[RiskEventContext] = Field(default_factory=list)
    alerts: List[AlertContext] = Field(default_factory=list)
    narratives: List[NarrativeContext] = Field(default_factory=list)
    trends: List[TrendEventContext] = Field(default_factory=list)
    documents: List[DocumentContext] = Field(default_factory=list)
    history: Optional[Dict[str, Any]] = None
    metadata: ContextMetadata
