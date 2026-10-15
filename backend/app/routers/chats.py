import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(tags=["chats"])


def _get_chat(db: Session, chat_id: str) -> models.Chat:
    chat = db.get(models.Chat, chat_id)
    if not chat:
        raise HTTPException(404, "השיחה לא נמצאה")
    return chat


@router.get("/api/topics/{topic_id}/chats", response_model=list[schemas.ChatSummary])
def list_chats(topic_id: str, db: Session = Depends(get_db)):
    if not db.get(models.Topic, topic_id):
        raise HTTPException(404, "הנושא לא נמצא")
    chats = (
        db.query(models.Chat).filter(models.Chat.topic_id == topic_id).order_by(models.Chat.updated_at.desc()).all()
    )
    return [
        {"id": c.id, "title": c.title, "updated_at": c.updated_at, "message_count": len(c.messages)} for c in chats
    ]


@router.get("/api/chats/{chat_id}", response_model=schemas.ChatDetail)
def get_chat(chat_id: str, db: Session = Depends(get_db)):
    chat = _get_chat(db, chat_id)
    return {
        "id": chat.id,
        "topic_id": chat.topic_id,
        "title": chat.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "used_sources": json.loads(m.used_sources or "[]"),
                "attachment_name": m.attachment_name,
                "created_at": m.created_at,
            }
            for m in chat.messages
        ],
    }


@router.patch("/api/chats/{chat_id}", response_model=schemas.ChatSummary)
def rename_chat(chat_id: str, payload: schemas.ChatRename, db: Session = Depends(get_db)):
    chat = _get_chat(db, chat_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(400, "יש להזין שם לשיחה")
    chat.title = title[:100]
    db.commit()
    return {"id": chat.id, "title": chat.title, "updated_at": chat.updated_at, "message_count": len(chat.messages)}


@router.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, db: Session = Depends(get_db)):
    chat = _get_chat(db, chat_id)
    db.delete(chat)
    db.commit()
    return {"ok": True}
