"""Editing a source: every change to its text keeps the previous text as a version."""
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models

EDITABLE_FIELDS = ("title", "source_type", "date", "description", "content")


def apply_edit(db: Session, source: models.Source, user: models.Person, changes: dict) -> bool:
    """Applies the fields that really differ; returns False (and records nothing) when nothing changes."""
    changed = {k: v for k, v in changes.items() if k in EDITABLE_FIELDS and getattr(source, k) != v}
    if not changed:
        return False
    db.add(
        models.SourceVersion(
            source_id=source.id,
            replaced_by=user.id,
            title=source.title,
            source_type=source.source_type,
            date=source.date,
            description=source.description or "",
            content=source.content or "",
        )
    )
    for key, value in changed.items():
        setattr(source, key, value)
    source.edited_at = datetime.utcnow()
    source.edited_by = user.id
    return True
