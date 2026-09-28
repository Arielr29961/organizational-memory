from sqlalchemy.orm import Session

from . import models


def topic_to_out(db: Session, topic: models.Topic) -> dict:
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
    }


def source_to_out(source: models.Source) -> dict:
    tags = [
        {"id": st.tag.id, "name": st.tag.name, "origin": st.origin}
        for st in sorted(source.tags, key=lambda t: t.tag.name)
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
        "created_at": source.created_at,
        "tags": tags,
    }
