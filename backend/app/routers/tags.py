from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..serializers import source_to_out

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[schemas.TagWithCount])
def list_tags(db: Session = Depends(get_db)):
    tags = db.query(models.Tag).all()
    results = []
    for tag in tags:
        count = db.query(models.SourceTag).filter(models.SourceTag.tag_id == tag.id).count()
        results.append({"id": tag.id, "name": tag.name, "count": count})
    results.sort(key=lambda t: t["count"], reverse=True)
    return results


@router.get("/{tag_name}/sources", response_model=list[schemas.SourceOut])
def sources_by_tag(tag_name: str, db: Session = Depends(get_db)):
    tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
    if not tag:
        return []
    sources = [st.source for st in tag.sources]
    sources.sort(key=lambda s: s.date, reverse=True)
    return [source_to_out(s) for s in sources]
