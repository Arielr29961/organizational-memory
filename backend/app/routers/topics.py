import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..serializers import topic_to_out
from ..services import claude_service, file_extraction, tag_service, tag_utils

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("", response_model=list[schemas.TopicOut])
def list_topics(q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Topic)
    if q:
        query = query.filter(models.Topic.name.ilike(f"%{q}%"))
    topics = query.order_by(models.Topic.created_at.desc()).all()
    return [topic_to_out(db, t) for t in topics]


@router.post("", response_model=schemas.TopicOut)
def create_topic(payload: schemas.TopicCreate, db: Session = Depends(get_db)):
    topic = models.Topic(name=payload.name, description=payload.description or "")
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic_to_out(db, topic)


@router.get("/{topic_id}", response_model=schemas.TopicOut)
def get_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    return topic_to_out(db, topic)


@router.patch("/{topic_id}", response_model=schemas.TopicOut)
def update_topic(topic_id: str, payload: schemas.TopicUpdate, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    if payload.name is not None:
        topic.name = payload.name
    if payload.description is not None:
        topic.description = payload.description
    db.commit()
    db.refresh(topic)
    return topic_to_out(db, topic)


@router.delete("/{topic_id}")
def delete_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    tag_ids = {st.tag_id for source in topic.sources for st in source.tags}
    db.delete(topic)
    db.commit()
    tag_service.delete_if_unused(db, tag_ids)
    return {"ok": True}


CITATION_RE = re.compile(r"\[\[\s*(?:id:\s*)?([0-9a-fA-F-]{36})\s*\]\]")


def _resolve_citations(answer: str, context_sources: dict) -> tuple[str, list[dict]]:
    """Keep only [[id]] markers that point to a source we actually sent; return those sources in citation order."""
    cited: dict[str, dict] = {}

    def replace(match: re.Match) -> str:
        source_id = match.group(1).lower()
        source = context_sources.get(source_id)
        if not source:
            return ""
        cited.setdefault(source_id, source)
        return f"[[{source_id}]]"

    return CITATION_RE.sub(replace, answer), list(cited.values())


MAX_HISTORY_MESSAGES = 10
ATTACHMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".md"}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENT_CHARS = 30000


def _read_attachment(file: UploadFile) -> tuple[str, str]:
    """Extract text from a file attached to a chat message. The file is not kept on disk."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ATTACHMENT_EXTENSIONS:
        raise HTTPException(400, "סוג הקובץ אינו נתמך. ניתן לצרף PDF, Word, Excel, CSV או קובץ טקסט")
    data = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(400, "הקובץ גדול מדי (מעל 10MB)")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        text = file_extraction.extract_text(path, file.filename)
    if text.startswith("[שגיאה") or not text.strip():
        raise HTTPException(400, "לא ניתן היה לחלץ טקסט מהקובץ")
    if len(text) > MAX_ATTACHMENT_CHARS:
        text = text[:MAX_ATTACHMENT_CHARS] + "\n[... הקובץ קוצר עקב אורכו ...]"
    return file.filename, text


def _chat_history(chat: models.Chat) -> list[dict]:
    """The last few messages of a chat, as plain role/content pairs for the model (must start with a user turn)."""
    messages = [
        {
            "role": m.role,
            "content": (
                f"[קובץ מצורף: {m.attachment_name}]\n{m.attachment_text}\n\n{m.content}"
                if m.attachment_text
                else m.content
            ),
        }
        for m in chat.messages
    ][-MAX_HISTORY_MESSAGES:]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


@router.post("/{topic_id}/ask", response_model=schemas.AskResponse)
def ask_ai(
    topic_id: str,
    question: str = Form(...),
    chat_id: Optional[str] = Form(None),  # continue this chat; a new chat is created when omitted
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")

    attachment_name = attachment_text = None
    if file is not None and file.filename:
        attachment_name, attachment_text = _read_attachment(file)

    chat = None
    if chat_id:
        chat = db.get(models.Chat, chat_id)
        if not chat or chat.topic_id != topic_id:
            raise HTTPException(404, "השיחה לא נמצאה")

    timeline_sources = sorted(topic.sources, key=lambda s: s.date)
    timeline_lines = []
    for s in timeline_sources:
        tag_names = ", ".join(st.tag.name for st in s.tags)
        timeline_lines.append(
            f"[id: {s.id}] [{s.date}] ({s.source_type}) {s.title} | תגיות: {tag_names}\n{s.content[:3000]}"
        )
    timeline_text = "\n\n".join(timeline_lines) or "(אין עדיין מקורות בנושא זה)"

    topic_tag_keys = {tag_utils.tag_key(st.tag.name) for s in timeline_sources for st in s.tags}
    cross_lines = []
    context_sources = {
        s.id: {"id": s.id, "title": s.title, "date": str(s.date), "topic_id": topic.id, "topic_name": topic.name}
        for s in timeline_sources
    }
    if topic_tag_keys:
        other_sources = (
            db.query(models.Source)
            .filter(models.Source.topic_id != topic_id)
            .all()
        )
        for s in other_sources:
            shared = {st.tag.name for st in s.tags if tag_utils.tag_key(st.tag.name) in topic_tag_keys}
            if shared:
                cross_lines.append(
                    f"[id: {s.id}] [{s.date}] נושא: {s.topic.name} | {s.title} | תגיות משותפות: {', '.join(shared)}\n"
                    f"תקציר: {s.content[:800]}"
                )
                context_sources[s.id] = {
                    "id": s.id,
                    "title": s.title,
                    "date": str(s.date),
                    "topic_id": s.topic_id,
                    "topic_name": s.topic.name,
                }
    cross_text = "\n\n".join(cross_lines)

    history = _chat_history(chat) if chat else []
    try:
        answer = claude_service.ask_question(
            topic.name, topic.description, timeline_text, cross_text, question, history,
            attachment_name, attachment_text,
        )
    except claude_service.ClaudeNotConfiguredError as exc:
        raise HTTPException(400, str(exc))

    answer, cited_sources = _resolve_citations(answer, context_sources)

    # Save only after a successful answer, so a failed call never leaves an empty chat behind.
    now = datetime.utcnow()
    if not chat:
        chat = models.Chat(topic_id=topic_id, title=question.strip()[:60] or "שיחה חדשה")
        db.add(chat)
        db.flush()
    db.add(
        models.ChatMessage(
            chat_id=chat.id,
            role="user",
            content=question,
            attachment_name=attachment_name,
            attachment_text=attachment_text,
            created_at=now,
        )
    )
    db.add(
        models.ChatMessage(
            chat_id=chat.id,
            role="assistant",
            content=answer,
            used_sources=json.dumps(cited_sources, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
    )
    chat.updated_at = datetime.utcnow()
    db.commit()

    return {"answer": answer, "used_sources": cited_sources, "chat_id": chat.id, "chat_title": chat.title}
