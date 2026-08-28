from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.auth import get_current_user, user_has_client_access
from app.core.db import get_db, SessionLocal
from app.models.user import User
from app.schemas.entity import EntityCreate, EntityResponse, EntityAliasCreate, EntityKeywordCreate, EntityKeywordResponse, EntityAliasResponse
from app.services.entity_service import create_entity, get_entity, add_alias
from app.services.keyword_service import add_keyword
from app.services.matching_engine import engine_instance

router = APIRouter()


def _refresh_matching_engine():
    db = SessionLocal()
    try:
        engine_instance.refresh_processor(db)
    finally:
        db.close()


def _get_client_scoped_entity(db: Session, entity_id: UUID, current_user: User):
    """Look up entity_id and verify the caller is authorized for its
    client_id (TASK_AUTH.md fix #4 -- this endpoint's previously-unscoped
    GET /{entity_id} was the confirmed cross-tenant read gap in the audit).
    Can't use require_client_access as a Depends here since client_id isn't
    a path/query param on these routes -- only entity_id is.
    """
    entity = get_entity(db, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not user_has_client_access(db, current_user.id, entity.client_id):
        raise HTTPException(status_code=403, detail="Not authorized for this client")
    return entity

@router.post("/", response_model=EntityResponse)
def create_new_entity(
    entity_in: EntityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # client_id arrives as a body field here, not path/query, so it's
    # checked explicitly rather than via the require_client_access Depends.
    if not user_has_client_access(db, current_user.id, entity_in.client_id):
        raise HTTPException(status_code=403, detail="Not authorized for this client")
    return create_entity(db, entity_in)

@router.get("/{entity_id}", response_model=EntityResponse)
def read_entity(entity_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _get_client_scoped_entity(db, entity_id, current_user)

@router.post("/{entity_id}/aliases", response_model=EntityAliasResponse)
def create_entity_alias(
    entity_id: UUID,
    alias_in: EntityAliasCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_client_scoped_entity(db, entity_id, current_user)
    return add_alias(db, entity_id, alias_in.alias_text)

@router.post("/{entity_id}/keywords", response_model=EntityKeywordResponse)
def create_entity_keyword(
    entity_id: UUID,
    keyword_in: EntityKeywordCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_client_scoped_entity(db, entity_id, current_user)
    keyword = add_keyword(
        db, 
        str(entity_id), 
        keyword_in.keyword_text, 
        keyword_in.category, 
        keyword_in.priority
    )
    
    # Hot reload the matching engine in the background
    background_tasks.add_task(_refresh_matching_engine)
    
    return keyword
