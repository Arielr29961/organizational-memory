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
from ..deps import get_current_user, get_topic_as
from ..serializers import participants_text, topic_to_out
from ..config import MAX_CONTEXT_CHARS
from ..services import access_service, claude_service, file_extraction, source_selection, tag_service, tag_utils

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("", response_model=list[schemas.TopicOut])
def list_topics(q: str | None = None, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    query = db.query(models.Topic).filter(models.Topic.id.in_(access_service.accessible_topic_ids(db, user)))
    if q:
        query = query.filter(models.Topic.name.ilike(f"%{q}%"))
    topics = query.order_by(models.Topic.created_at.desc()).all()
    return [topic_to_out(db, t, user) for t in topics]


@router.post("", response_model=schemas.TopicOut)
def create_topic(payload: schemas.TopicCreate, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    topic = models.Topic(name=payload.name, description=payload.description or "", owner_id=user.id)
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic_to_out(db, topic, user)


@router.get("/{topic_id}", response_model=schemas.TopicOut)
def get_topic(topic_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    topic = get_topic_as(db, user, topic_id, "viewer")
    return topic_to_out(db, topic, user)


@router.patch("/{topic_id}", response_model=schemas.TopicOut)
def update_topic(topic_id: str, payload: schemas.TopicUpdate, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    topic = get_topic_as(db, user, topic_id, "owner")
    if payload.name is not None:
        topic.name = payload.name
    if payload.description is not None:
        topic.description = payload.description
    db.commit()
    db.refresh(topic)
    return topic_to_out(db, topic, user)


@router.delete("/{topic_id}")
def delete_topic(topic_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    topic = get_topic_as(db, user, topic_id, "owner")
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


def build_ask_context(db: Session, user: models.Person, topic: models.Topic, question: str, chat, focus_tag: Optional[str]):
    """The text Claude gets as context: the topic's sources (only those with the focus tag when one is set) and sources
    of the user's other accessible topics (those with the same tag in focus mode, otherwise picked by Claude).
    Returns (timeline_text, cross_text, context_sources)."""
    topic_id = topic.id
    focus_key = tag_utils.tag_key(focus_tag) if focus_tag else None
    timeline_sources = sorted(topic.sources, key=lambda s: s.date)
    if focus_key:
        timeline_sources = [s for s in timeline_sources if any(tag_utils.tag_key(st.tag.name) == focus_key for st in s.tags)]
    # Share the context budget between the topic's sources so a big topic cannot overflow the prompt.
    per_source_chars = max(500, min(3000, MAX_CONTEXT_CHARS // max(1, len(timeline_sources))))
    timeline_lines = []
    for s in timeline_sources:
        tag_names = ", ".join(st.tag.name for st in s.tags)
        timeline_lines.append(
            f"[id: {s.id}] [{s.date}] ({s.source_type}) {s.title} | תגיות: {tag_names}{participants_text(s)}\n{s.content[:per_source_chars]}"
        )
    timeline_text = "\n\n".join(timeline_lines) or "(אין עדיין מקורות בנושא זה)"

    context_sources = {
        s.id: {"id": s.id, "title": s.title, "date": str(s.date), "topic_id": topic.id, "topic_name": topic.name}
        for s in timeline_sources
    }

    # Sources of other topics: Claude picks the relevant ones (no shared tag needed); shared tags are the fallback.
    topic_tag_keys = {tag_utils.tag_key(st.tag.name) for s in timeline_sources for st in s.tags}
    index = source_selection.build_index(db, topic_id, topic_tag_keys, access_service.accessible_topic_ids(db, user))
    if focus_key:
        related = source_selection.tagged_sources(index, focus_tag)
    else:
        previous_questions = [m.content for m in chat.messages if m.role == "user"][-2:] if chat else []
        related, _used_ai = source_selection.select_sources(
            index, topic.name, topic.description, [*previous_questions, question]
        )
    cross_lines = []
    for s in related:
        cross_lines.append(
            f"[id: {s.id}] [{s.date}] נושא: {s.topic.name} | {s.title} | תגיות: {', '.join(st.tag.name for st in s.tags)}{participants_text(s)}\n"
            f"תקציר: {s.content[:2000]}"
        )
        context_sources[s.id] = {
            "id": s.id,
            "title": s.title,
            "date": str(s.date),
            "topic_id": s.topic_id,
            "topic_name": s.topic.name,
        }
    cross_text = "\n\n".join(cross_lines)

    return timeline_text, cross_text, context_sources


@router.post("/{topic_id}/ask", response_model=schemas.AskResponse)
def ask_ai(
    topic_id: str,
    question: str = Form(...),
    chat_id: Optional[str] = Form(None),  # continue this chat; a new chat is created when omitted
    tag: Optional[str] = Form(None),  # focus mode: only the sources with this tag
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db), user: models.Person = Depends(get_current_user),
):
    topic = get_topic_as(db, user, topic_id, "viewer")

    attachment_name = attachment_text = None
    if file is not None and file.filename:
        attachment_name, attachment_text = _read_attachment(file)

    chat = None
    if chat_id:
        chat = db.get(models.Chat, chat_id)
        if not chat or chat.topic_id != topic_id or chat.created_by != user.id:
            raise HTTPException(404, "השיחה לא נמצאה")

    focus_tag = tag_utils.clean_tag(tag) if tag and tag.strip() else None
    if focus_tag:
        key = tag_utils.tag_key(focus_tag)
        if not any(tag_utils.tag_key(st.tag.name) == key for s in topic.sources for st in s.tags):
            raise HTTPException(400, "אין בנושא מקורות עם התגית הזו")
    timeline_text, cross_text, context_sources = build_ask_context(db, user, topic, question, chat, focus_tag)

    history = _chat_history(chat) if chat else []
    try:
        answer = claude_service.ask_question(
            topic.name, topic.description, timeline_text, cross_text, question, history,
            attachment_name, attachment_text, focus_tag,
        )
    except claude_service.ClaudeNotConfiguredError as exc:
        raise HTTPException(400, str(exc))

    answer, cited_sources = _resolve_citations(answer, context_sources)

    # Save only after a successful answer, so a failed call never leaves an empty chat behind.
    now = datetime.utcnow()
    if not chat:
        chat = models.Chat(topic_id=topic_id, created_by=user.id, title=question.strip()[:60] or "שיחה חדשה")
        db.add(chat)
        db.flush()
    db.add(
        models.ChatMessage(
            chat_id=chat.id,
            role="user",
            content=question,
            attachment_name=attachment_name,
            attachment_text=attachment_text,
            context_tag=focus_tag,
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
