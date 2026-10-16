"""Database operations on tags: normalized get-or-create, listing, merging and splitting."""
import re

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


def delete_if_unused(db: Session, tag_ids) -> int:
    """Delete these tags if no source uses them any more (tags are shared by all topics, so they would linger)."""
    deleted = 0
    for tag_id in set(tag_ids):
        tag = db.get(models.Tag, tag_id)
        if tag and not tag.sources:
            db.delete(tag)
            deleted += 1
    db.commit()
    return deleted


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
    if not tag.sources:  # nothing to redistribute: splitting would only create new unused tags
        db.delete(tag)
        db.commit()
        return {"split": tag_id, "into": []}
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


MAX_TAGS_FOR_AI = 400


def build_ai_tag_input(db: Session) -> list[dict]:
    """Tags worth sending to the model: in use, not joined, not plain numbers; most used first, with 2 example titles."""
    tags = []
    for tag in db.query(models.Tag).all():
        key = tag_utils.tag_key(tag.name)
        if not tag.sources or tag_utils.has_separator(tag.name) or key.isdigit():
            continue
        links = sorted(tag.sources, key=lambda link: link.source.date, reverse=True)
        tags.append({"name": tag.name, "count": len(tag.sources), "titles": [link.source.title for link in links[:2]], "id": tag.id})
    tags.sort(key=lambda t: t["count"], reverse=True)
    tags = tags[:MAX_TAGS_FOR_AI]
    for i, tag in enumerate(tags, start=1):
        tag["key"] = f"t{i}"
    return tags


def _name_tag_ids(text: str, by_key: dict) -> str:
    """Replace internal ids the model may mention (t1, t18...) with the tag names."""
    return re.sub(r"(?<![\w])t\d+(?![\w])", lambda m: f"#{by_key[m.group(0)]['name']}" if m.group(0) in by_key else m.group(0), text)


def validate_tag_groups(raw: dict, tags: list[dict]) -> list[dict]:
    """Keep only well-formed groups: known ids, 2+ tags, each tag in one group ('same' groups take priority)."""
    by_key = {t["key"]: t for t in tags}
    groups = [g for g in (raw or {}).get("groups", []) if isinstance(g, dict)]
    groups.sort(key=lambda g: 0 if g.get("kind") == "same" else 1)
    used = set()
    result = []
    for group in groups:
        keys = []
        for key in group.get("tag_ids", []) or []:
            if key in by_key and key not in used and key not in keys:
                keys.append(key)
        if len(keys) < 2:
            continue
        used.update(keys)
        members = [{"id": by_key[k]["id"], "name": by_key[k]["name"], "count": by_key[k]["count"]} for k in keys]
        keep = by_key[group["keep"]]["id"] if group.get("keep") in keys else max(members, key=lambda m: m["count"])["id"]
        result.append(
            {
                "kind": "same" if group.get("kind") == "same" else "related",
                "tags": members,
                "keep_id": keep,
                "reason": _name_tag_ids(str(group.get("reason") or ""), by_key)[:300],
            }
        )
    return result


def merge_group(db: Session, keep_id: str, merge_ids: list[str]) -> dict:
    """Merge several tags into the one to keep (each merge commits on its own)."""
    if keep_id in merge_ids:
        raise ValueError("התגית שנשארת לא יכולה להיות גם בין התגיות שימוזגו")
    if not merge_ids:
        raise ValueError("לא נבחרו תגיות למיזוג")
    moved = 0
    for tag_id in merge_ids:
        moved += merge_tags(db, tag_id, keep_id)["sources_moved"]
    return {"kept": keep_id, "merged": merge_ids, "sources_moved": moved}


def delete_unused_tags(db: Session, tag_ids: list[str]) -> dict:
    """Delete the given tags, but only those that really have no sources (re-checked here, not trusted from the UI)."""
    deleted, skipped = 0, 0
    for tag_id in tag_ids:
        tag = db.get(models.Tag, tag_id)
        if tag and not tag.sources:
            db.delete(tag)
            deleted += 1
        else:
            skipped += 1
    db.commit()
    return {"deleted": deleted, "skipped": skipped}
