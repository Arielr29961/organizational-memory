"""Who may do what with a topic: the owner, plus members with the role 'viewer' or 'editor'."""
from sqlalchemy.orm import Session

from .. import models

ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}
MEMBER_ROLES = ("viewer", "editor")


def role_in_topic(db: Session, user: models.Person, topic: models.Topic) -> str | None:
    """'owner', 'editor', 'viewer', or None when the user has no access."""
    if topic.owner_id == user.id:
        return "owner"
    member = (
        db.query(models.TopicMember)
        .filter(models.TopicMember.topic_id == topic.id, models.TopicMember.person_id == user.id)
        .first()
    )
    return member.role if member else None


def has_role(role: str | None, minimum: str) -> bool:
    return role is not None and ROLE_RANK[role] >= ROLE_RANK[minimum]


def owned_topic_ids(db: Session, user: models.Person) -> set[str]:
    return {t_id for (t_id,) in db.query(models.Topic.id).filter(models.Topic.owner_id == user.id).all()}


def accessible_topic_ids(db: Session, user: models.Person) -> set[str]:
    """Topics the user owns or was shared into."""
    shared = {t_id for (t_id,) in db.query(models.TopicMember.topic_id).filter(models.TopicMember.person_id == user.id).all()}
    return owned_topic_ids(db, user) | shared


def backfill_chat_authors() -> None:
    """Chats saved before sharing existed belong to the owner of their topic."""
    from ..database import SessionLocal

    with SessionLocal() as db:
        chats = db.query(models.Chat).filter(models.Chat.created_by.is_(None)).all()
        for chat in chats:
            if chat.topic.owner_id:
                chat.created_by = chat.topic.owner_id
        if chats:
            db.commit()
