from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.db import get_db
from app.schemas.entity import EntityCreate, EntityResponse, EntityAliasCreate, EntityKeywordCreate, EntityKeywordResponse, EntityAliasResponse
from app.services.entity_service import create_entity, get_entity, add_alias
from app.services.keyword_service import add_keyword
from app.services.matching_engine import engine_instance

router = APIRouter()

@router.post("/", response_model=EntityResponse)
def create_new_entity(entity_in: EntityCreate, db: Session = Depends(get_db)):
    return create_entity(db, entity_in)

@router.get("/{entity_id}", response_model=EntityResponse)
def read_entity(entity_id: UUID, db: Session = Depends(get_db)):
    entity = get_entity(db, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity

@router.post("/{entity_id}/aliases", response_model=EntityAliasResponse)
def create_entity_alias(entity_id: UUID, alias_in: EntityAliasCreate, db: Session = Depends(get_db)):
    if not get_entity(db, entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    return add_alias(db, entity_id, alias_in.alias_text)

@router.post("/{entity_id}/keywords", response_model=EntityKeywordResponse)
def create_entity_keyword(
    entity_id: UUID,
    keyword_in: EntityKeywordCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    if not get_entity(db, entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    keyword = add_keyword(
        db, 
        str(entity_id), 
        keyword_in.keyword_text, 
        keyword_in.category, 
        keyword_in.priority
    )
    
    # Hot reload the matching engine in the background
    background_tasks.add_task(engine_instance.refresh_processor, db)
    
    return keyword
