from sqlalchemy.orm import Session

from . import models
from .services import access_service


def topic_to_out(db: Session, topic: models.Topic, user: models.Person) -> dict:
    source_ids = [s.id for s in topic.sources]
    tag_names = set()
    if source_ids:
        rows = (
            db.query(models.Tag.name)
            .join(models.SourceTag, models.SourceTag.tag_id == models.Tag.id)
            .filter(models.SourceTag.source_id.in_(source_ids))
            .distinct()
            .all()
        )
        tag_names = {r[0] for r in rows}
    return {
        "id": topic.id,
        "name": topic.name,
        "description": topic.description or "",
        "created_at": topic.created_at,
        "source_count": len(source_ids),
        "tags": sorted(tag_names),
        "role": access_service.role_in_topic(db, user, topic),
        "owner_name": topic.owner.name if topic.owner else None,
        "owner_email": topic.owner.email if topic.owner else None,
    }


def participants_text(source: models.Source) -> str:
    """' | משתתפים: ...' fragment for AI context lines (empty when the source has no participants)."""
    if not source.participants:
        return ""
    names = ", ".join(f"{sp.person.name} <{sp.person.email}>" for sp in source.participants)
    return f" | משתתפים: {names}"


def utc_iso(moment) -> str | None:
    """Datetimes are stored as naive UTC; the trailing Z lets the browser show them in the viewer's own time zone."""
    return moment.isoformat() + "Z" if moment else None


def source_to_out(source: models.Source) -> dict:
    tags = [
        {"id": st.tag.id, "name": st.tag.name, "origin": st.origin}
        for st in sorted(source.tags, key=lambda t: t.tag.name)
    ]
    participants = [
        {"id": sp.person.id, "email": sp.person.email, "name": sp.person.name, "registered": bool(sp.person.password_hash)}
        for sp in sorted(source.participants, key=lambda p: p.person.name)
    ]
    return {
        "id": source.id,
        "topic_id": source.topic_id,
        "topic_name": source.topic.name if source.topic else None,
        "title": source.title,
        "source_type": source.source_type,
        "date": source.date,
        "content": source.content or "",
        "description": source.description or "",
        "file_name": source.file_name,
        "has_file": bool(source.file_path),
        "created_at": source.created_at,
        "edited_at": utc_iso(source.edited_at),
        "edited_by_name": source.editor.name if source.editor else None,
        "version_count": len(source.versions),
        "tags": tags,
        "participants": participants,
    }
