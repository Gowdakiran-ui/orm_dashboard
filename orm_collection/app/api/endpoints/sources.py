from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core.auth import get_current_user, require_super_admin
from app.core.db import get_db
from app.schemas.source import SourceCreate, SourceResponse
from app.models.source import Source
from app.models.user import ROLE_SUPER_ADMIN, User, UserClientAccess

router = APIRouter()

@router.post("/", response_model=SourceResponse)
def create_source(source_in: SourceCreate, db: Session = Depends(get_db), _admin: User = Depends(require_super_admin)):
    """Super admin only. Sources are shared platform configuration; a client user must not add to them. (The router has no PUT or
    DELETE route.)"""
    db_source = Source(**source_in.model_dump())
    db.add(db_source)
    db.commit()
    db.refresh(db_source)
    return db_source

@router.get("/")
def read_sources(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Super admin: every source. A client user: only the sources linked to their own clients, i.e. a source whose url is the
    feed url of one of their clients' feeds (the per-client "<company> RSS Source" / GDELT / HN rows created at onboarding). A
    source linked to nobody, or only to someone else's client, is not listed, so no other client's name (these names carry the
    company name) or id reaches them."""
    from app.models.document import Document
    from app.models.rss_feed import RSSFeed
    from sqlalchemy.sql import func

    query = db.query(
        Source,
        func.count(Document.id).label("doc_count")
    ).outerjoin(
        Document, Document.source_id == Source.id
    )
    if current_user.role != ROLE_SUPER_ADMIN:
        client_ids = [r.client_id for r in db.query(UserClientAccess.client_id).filter(UserClientAccess.user_id == current_user.id).all()]
        own_urls = db.query(RSSFeed.feed_url).filter(RSSFeed.client_id.in_(client_ids)) if client_ids else None
        if own_urls is None:
            query = query.filter(Source.id.is_(None))
        else:
            query = query.filter(Source.url.in_(own_urls))
    results = query.group_by(Source.id).all()

    rss_list = []
    for s, doc_count in results:
        rss_list.append({
            "name": s.name,
            "url": s.url,
            "status": "Active" if s.is_active else "Inactive",
            "articles": doc_count
        })

    return {
        "rss": rss_list,
        "reddit": [],
        "youtube": []
    }
