"""Request dependencies: who is logged in, and lookups that only succeed when the user's role allows it."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .services import access_service, auth_service


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def get_token(authorization: str | None = Header(None)) -> str:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(401, "יש להתחבר")
    return token


def get_current_user(token: str = Depends(get_token), db: Session = Depends(get_db)) -> models.Person:
    person = auth_service.person_for_token(db, token)
    if not person:
        raise HTTPException(401, "ההתחברות פגה, יש להתחבר מחדש")
    return person


# A topic the user has no access to answers 404 (same as "does not exist"); one they can see but may not change
# answers 403.

def get_topic_as(db: Session, user: models.Person, topic_id: str, minimum: str = "viewer") -> models.Topic:
    topic = db.get(models.Topic, topic_id)
    role = access_service.role_in_topic(db, user, topic) if topic else None
    if role is None:
        raise HTTPException(404, "הנושא לא נמצא")
    if not access_service.has_role(role, minimum):
        raise HTTPException(403, "אין לך הרשאה לבצע פעולה זו בנושא")
    return topic


def get_source_as(db: Session, user: models.Person, source_id: str, minimum: str = "viewer") -> models.Source:
    source = db.get(models.Source, source_id)
    role = access_service.role_in_topic(db, user, source.topic) if source else None
    if role is None:
        raise HTTPException(404, "המקור לא נמצא")
    if not access_service.has_role(role, minimum):
        raise HTTPException(403, "אין לך הרשאה לבצע פעולה זו בנושא")
    return source


def get_chat_for(db: Session, user: models.Person, chat_id: str) -> models.Chat:
    """Chats are personal: only their author, and only while the author still has access to the topic."""
    chat = db.get(models.Chat, chat_id)
    if not chat or chat.created_by != user.id or access_service.role_in_topic(db, user, chat.topic) is None:
        raise HTTPException(404, "השיחה לא נמצאה")
    return chat
