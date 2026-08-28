from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.auth import get_current_user, require_client_access, user_has_client_access
from app.core.db import get_db
from app.schemas.feed import RSSFeedCreate, RSSFeedResponse
from app.models.rss_feed import RSSFeed
from app.models.user import User

router = APIRouter()


def _get_client_scoped_feed(db: Session, feed_id: UUID, current_user: User) -> RSSFeed:
    """Look up feed_id and verify the caller is authorized for its client_id
    (TASK.md P0 #1-3 -- GET/POST/DELETE were fully unscoped, same bug class
    as the already-fixed /collection/status leak). Mirrors entities.py's
    _get_client_scoped_entity, since feed_id (not client_id) is the path param.
    """
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    if not user_has_client_access(db, current_user.id, feed.client_id):
        raise HTTPException(status_code=403, detail="Not authorized for this client")
    return feed

@router.post("/", response_model=RSSFeedResponse)
def create_feed(
    feed_in: RSSFeedCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # client_id arrives as a body field, not path/query, so it's checked
    # explicitly rather than via the require_client_access Depends (same
    # pattern as entities.py's create_new_entity).
    if not user_has_client_access(db, current_user.id, feed_in.client_id):
        raise HTTPException(status_code=403, detail="Not authorized for this client")
    db_feed = RSSFeed(**feed_in.model_dump())
    db.add(db_feed)
    db.commit()
    db.refresh(db_feed)
    return db_feed

@router.get("/", response_model=List[RSSFeedResponse])
def read_feeds(
    client_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _access: UUID = Depends(require_client_access),
):
    return db.query(RSSFeed).filter(RSSFeed.client_id == client_id).order_by(RSSFeed.created_at.desc(), RSSFeed.id.desc()).offset(skip).limit(limit).all()

@router.delete("/{feed_id}")
def delete_feed(
    feed_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feed = _get_client_scoped_feed(db, feed_id, current_user)
    db.delete(feed)
    db.commit()
    return {"status": "deleted"}
