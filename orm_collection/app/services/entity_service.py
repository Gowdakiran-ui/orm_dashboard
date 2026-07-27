from sqlalchemy.orm import Session
from uuid import UUID
from app.models.entity import Entity, EntityAlias
from app.schemas.entity import EntityCreate

def create_entity(db: Session, entity_in: EntityCreate) -> Entity:
    db_entity = Entity(
        client_id=entity_in.client_id,
        name=entity_in.name,
        entity_type=entity_in.entity_type,
        website=entity_in.website,
        domain=entity_in.domain,
        linkedin_url=entity_in.linkedin_url,
        ticker_symbol=entity_in.ticker_symbol,
        industry=entity_in.industry
    )
    db.add(db_entity)
    db.commit()
    db.refresh(db_entity)
    return db_entity

def add_alias(db: Session, entity_id: UUID, alias_text: str) -> EntityAlias:
    db_alias = EntityAlias(
        entity_id=entity_id,
        alias_text=alias_text
    )
    db.add(db_alias)
    db.commit()
    db.refresh(db_alias)
    return db_alias

def get_entity(db: Session, entity_id: UUID) -> Entity:
    return db.query(Entity).filter(Entity.id == entity_id).first()
