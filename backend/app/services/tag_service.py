"""Database operations on tags: normalized get-or-create, listing, merging and splitting."""
from sqlalchemy.orm import Session

from .. import models
from . import tag_utils


def get_or_create_tag(db: Session, name: str) -> models.Tag:
    """Return the existing tag with the same normalized key, or create one with the cleaned name."""
    clean = tag_utils.clean_tag(name)
    key = tag_utils.tag_key(clean)
    for tag in db.query(models.Tag).all():
        if tag_utils.tag_key(tag.name) == key:
            return tag
    tag = models.Tag(name=clean)
    db.add(tag)
    db.flush()
    return tag


def add_tag_to_source(db: Session, source: models.Source, raw_name: str, origin: str) -> None:
    """Attach tag(s) to a source. 'a, b' becomes two tags; names are normalized and matched to existing tags."""
    for name in tag_utils.split_tag_input(raw_name):
        tag = get_or_create_tag(db, name)
        exists = (
            db.query(models.SourceTag)
            .filter(models.SourceTag.source_id == source.id, models.SourceTag.tag_id == tag.id)
            .first()
        )
        if not exists:
            db.add(models.SourceTag(source_id=source.id, tag_id=tag.id, origin=origin))


def tags_with_counts(db: Session) -> list[dict]:
    tags = db.query(models.Tag).all()
    results = [{"id": t.id, "name": t.name, "count": len(t.sources)} for t in tags]
    results.sort(key=lambda t: t["count"], reverse=True)
    return results


def _move_links(db: Session, source_tag: models.Tag, target: models.Tag) -> int:
    """Re-point every source link of source_tag to target (skipping sources that already have target)."""
    moved = 0
    for link in list(source_tag.sources):
        existing = (
            db.query(models.SourceTag)
            .filter(models.SourceTag.source_id == link.source_id, models.SourceTag.tag_id == target.id)
            .first()
        )
        if existing:
            if link.origin == "user":
                existing.origin = "user"
            db.delete(link)
        else:
            link.tag_id = target.id
            moved += 1
    return moved


def merge_tags(db: Session, source_tag_id: str, into_tag_id: str) -> dict:
    """Merge one tag into another: its sources move over and the old tag disappears."""
    source_tag = db.get(models.Tag, source_tag_id)
    target = db.get(models.Tag, into_tag_id)
    if not source_tag or not target:
        raise LookupError("התגית לא נמצאה")
    if source_tag.id == target.id:
        raise ValueError("לא ניתן למזג תגית לעצמה")
    moved = _move_links(db, source_tag, target)
    db.flush()
    db.expire(source_tag)
    db.delete(source_tag)
    db.commit()
    return {"merged": source_tag_id, "into": target.id, "sources_moved": moved}


def split_tag(db: Session, tag_id: str) -> dict:
    """Split a joined tag such as 'a, b, c' into separate tags on every source that had it."""
    tag = db.get(models.Tag, tag_id)
    if not tag:
        raise LookupError("התגית לא נמצאה")
    names = tag_utils.split_tag_input(tag.name)
    if len(names) < 2:
        raise ValueError("התגית אינה מורכבת מכמה תגיות")
    targets = [get_or_create_tag(db, n) for n in names]
    targets = [t for t in targets if t.id != tag.id]
    for link in list(tag.sources):
        for target in targets:
            exists = (
                db.query(models.SourceTag)
                .filter(models.SourceTag.source_id == link.source_id, models.SourceTag.tag_id == target.id)
                .first()
            )
            if not exists:
                db.add(models.SourceTag(source_id=link.source_id, tag_id=target.id, origin=link.origin))
        db.delete(link)
    db.flush()
    db.expire(tag)
    db.delete(tag)
    db.commit()
    return {"split": tag_id, "into": [t.name for t in targets]}
