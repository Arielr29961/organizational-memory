from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..serializers import source_to_out
from ..services import claude_service, tag_service, tag_utils

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagMerge(BaseModel):
    into_id: str


class TagIds(BaseModel):
    tag_ids: list[str]


class TagGroupMerge(BaseModel):
    keep_id: str
    merge_ids: list[str]


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
    unused = [t for t in tags if t["count"] == 0]
    used = [t for t in tags if t["count"] > 0]
    joined = [t for t in used if tag_utils.has_separator(t["name"])]
    single = [t for t in used if not tag_utils.has_separator(t["name"])]  # joined tags are handled by splitting
    return {
        "duplicates": [{"a": a, "b": b, "score": score} for a, b, score in tag_utils.find_duplicate_pairs(single)],
        "joined": joined,
        "unused": unused,
    }


@router.post("/delete-unused")
def delete_unused(payload: TagIds, db: Session = Depends(get_db)):
    """Delete tags that no source uses. Tags that are in use are skipped."""
    return tag_service.delete_unused_tags(db, payload.tag_ids)


@router.post("/synonyms")
def suggest_synonyms(db: Session = Depends(get_db)):
    """Ask Claude which existing tags could be merged. Only suggests: nothing is changed."""
    tags = tag_service.build_ai_tag_input(db)
    if len(tags) < 2:
        return {"groups": [], "tags_checked": len(tags)}
    try:
        raw = claude_service.suggest_tag_groups(tags)
    except claude_service.ClaudeNotConfiguredError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"שגיאה בקריאה ל-AI: {exc}")
    return {"groups": tag_service.validate_tag_groups(raw, tags), "tags_checked": len(tags)}


@router.post("/merge-group")
def merge_group(payload: TagGroupMerge, db: Session = Depends(get_db)):
    try:
        return tag_service.merge_group(db, payload.keep_id, payload.merge_ids)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


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
