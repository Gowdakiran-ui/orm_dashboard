from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core.db import get_db
from app.schemas.source import SourceCreate, SourceResponse
from app.models.source import Source

router = APIRouter()

@router.post("/", response_model=SourceResponse)
def create_source(source_in: SourceCreate, db: Session = Depends(get_db)):
    db_source = Source(**source_in.model_dump())
    db.add(db_source)
    db.commit()
    db.refresh(db_source)
    return db_source

@router.get("/")
def read_sources(db: Session = Depends(get_db)):
    from app.models.document import Document
    from sqlalchemy.sql import func
    
    results = db.query(
        Source,
        func.count(Document.id).label("doc_count")
    ).outerjoin(
        Document, Document.source_id == Source.id
    ).group_by(
        Source.id
    ).all()
    
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
