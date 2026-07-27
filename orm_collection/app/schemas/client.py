from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class ClientBase(BaseModel):
    name: str
    industry: Optional[str] = None

class ClientCreate(ClientBase):
    pass

class CompetitorData(BaseModel):
    name: str
    website: Optional[str] = None
    domain: Optional[str] = None
    ticker_symbol: Optional[str] = None

class ClientOnboarding(ClientBase):
    # Additional fields to kick off entity and keyword generation
    primary_entity_name: str
    website: Optional[str] = None
    domain: Optional[str] = None
    ticker_symbol: Optional[str] = None
    competitors: Optional[List[Dict[str, Any]]] = None

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None

class ClientResponse(ClientBase):
    id: UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
