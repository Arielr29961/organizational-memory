"""Request dependencies: who is logged in, and lookups that only succeed for things that belong to them."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .services import auth_service


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


# Anything that exists but belongs to someone else answers 404, the same as "does not exist".

def owned_topic(db: Session, user: models.Person, topic_id: str) -> models.Topic:
    topic = db.get(models.Topic, topic_id)
    if not topic or topic.owner_id != user.id:
        raise HTTPException(404, "הנושא לא נמצא")
    return topic


def owned_source(db: Session, user: models.Person, source_id: str) -> models.Source:
    source = db.get(models.Source, source_id)
    if not source or source.topic.owner_id != user.id:
        raise HTTPException(404, "המקור לא נמצא")
    return source


def owned_chat(db: Session, user: models.Person, chat_id: str) -> models.Chat:
    chat = db.get(models.Chat, chat_id)
    if not chat or chat.topic.owner_id != user.id:
        raise HTTPException(404, "השיחה לא נמצאה")
    return chat
