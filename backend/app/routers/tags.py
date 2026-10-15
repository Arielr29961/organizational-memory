from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..serializers import source_to_out
from ..services import tag_service, tag_utils

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagMerge(BaseModel):
    into_id: str


@router.get("", response_model=list[schemas.TagWithCount])
def list_tags(db: Session = Depends(get_db)):
    return tag_service.tags_with_counts(db)


@router.get("/similar")
def similar_tags(name: str, limit: int = 5, db: Session = Depends(get_db)):
    """Existing tags that look like `name` (typos, spacing/quotes, close wording) - for 'did you mean' hints."""
    return tag_utils.find_similar(name, tag_service.tags_with_counts(db), limit=limit)


@router.get("/cleanup")
def cleanup_candidates(db: Session = Depends(get_db)):
    """Probable duplicate pairs, and tags that are really several tags joined together."""
    tags = tag_service.tags_with_counts(db)
    joined = [t for t in tags if tag_utils.has_separator(t["name"])]
    single = [t for t in tags if not tag_utils.has_separator(t["name"])]  # joined tags are handled by splitting
    return {
        "duplicates": [{"a": a, "b": b, "score": score} for a, b, score in tag_utils.find_duplicate_pairs(single)],
        "joined": joined,
    }


@router.post("/{tag_id}/merge")
def merge_tag(tag_id: str, payload: TagMerge, db: Session = Depends(get_db)):
    try:
        return tag_service.merge_tags(db, tag_id, payload.into_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{tag_id}/split")
def split_tag(tag_id: str, db: Session = Depends(get_db)):
    try:
        return tag_service.split_tag(db, tag_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/{tag_name}/sources", response_model=list[schemas.SourceOut])
def sources_by_tag(tag_name: str, db: Session = Depends(get_db)):
    tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
    if not tag:
        return []
    sources = [st.source for st in tag.sources]
    sources.sort(key=lambda s: s.date, reverse=True)
    return [source_to_out(s) for s in sources]
