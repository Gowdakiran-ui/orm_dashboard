from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.db import get_db
from app.schemas.feed import RSSFeedCreate, RSSFeedResponse
from app.models.rss_feed import RSSFeed

router = APIRouter()

@router.post("/", response_model=RSSFeedResponse)
def create_feed(feed_in: RSSFeedCreate, db: Session = Depends(get_db)):
    db_feed = RSSFeed(**feed_in.model_dump())
    db.add(db_feed)
    db.commit()
    db.refresh(db_feed)
    return db_feed

@router.get("/", response_model=List[RSSFeedResponse])
def read_feeds(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(RSSFeed).order_by(RSSFeed.created_at.desc(), RSSFeed.id.desc()).offset(skip).limit(limit).all()

@router.delete("/{feed_id}")
def delete_feed(feed_id: UUID, db: Session = Depends(get_db)):
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    db.delete(feed)
    db.commit()
    return {"status": "deleted"}
