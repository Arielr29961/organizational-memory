import json
import re
import shutil
import uuid
from datetime import date as date_type
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import UPLOAD_DIR
from ..database import get_db
from ..serializers import source_to_out
from ..services import claude_service, file_extraction, tag_utils
from ..services.tag_service import add_tag_to_source

router = APIRouter(tags=["sources"])


# Safety net behind the prompt rules: AI tags that are too generic to link sources meaningfully.
GENERIC_TAGS = {
    "חוב", "חובות", "תיקים", "תיק", "kpi", "נתונים", "מידע", "דוח", "דו\"ח", "דוחות", "ניהול", "בעיה", "בעיות",
    "שיפור", "ביצועים", "תהליך", "תהליכים", "עדכון", "סיכום", "ניתוח", "תוצאות", "נושא", "משימות", "החלטות",
    "פגישה", "פגישות", "מייל", "מסמך", "מצגת", "טבלה", "שנה", "חודש", "רבעון", "כללי", "אחר",
}
MAX_AI_TAGS = 5


def _filter_ai_tags(tags: list, topic_name: str = "") -> list[str]:
    """Drop generic/low-value AI tags, dedupe, and cap the count."""
    seen = set()
    kept = []
    for raw in tags:
        if not isinstance(raw, str):
            continue
        t = raw.strip().lstrip("#").strip()
        key = t.lower()
        if (
            len(t) < 2
            or len(t) > 40
            or len(t.split()) > 4
            or key in seen
            or key in GENERIC_TAGS
            or key == topic_name.strip().lower()
            or re.fullmatch(r"[\d\s./\-_,:]+", t)  # numbers, years, dates
        ):
            continue
        seen.add(key)
        kept.append(t)
    return kept[:MAX_AI_TAGS]


@router.get("/api/topics/{topic_id}/sources", response_model=list[schemas.SourceOut])
def list_sources(topic_id: str, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    sources = sorted(topic.sources, key=lambda s: s.date)
    return [source_to_out(s) for s in sources]


@router.post("/api/topics/{topic_id}/sources", response_model=schemas.SourceOut)
async def create_source(
    topic_id: str,
    title: str = Form(...),
    source_type: str = Form(...),
    date: str = Form(...),
    content: str = Form(""),
    description: str = Form(""),
    tags: str = Form("[]"),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")

    file_name = None
    file_path_str = None
    final_content = content or ""

    if file is not None and file.filename:
        ext = Path(file.filename).suffix
        stored_name = f"{uuid.uuid4()}{ext}"
        dest = UPLOAD_DIR / stored_name
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        file_name = file.filename
        file_path_str = str(dest)
        extracted = file_extraction.extract_text(dest, file.filename)
        if extracted.strip():
            final_content = (final_content + "\n\n" + extracted).strip() if final_content else extracted

    try:
        parsed_date = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "פורמט תאריך לא תקין, יש להשתמש ב-YYYY-MM-DD")

    source = models.Source(
        topic_id=topic_id,
        title=title,
        source_type=source_type,
        date=parsed_date,
        content=final_content,
        description=description,
        file_name=file_name,
        file_path=file_path_str,
    )
    db.add(source)
    db.flush()

    try:
        tag_list = json.loads(tags) if tags else []
    except json.JSONDecodeError:
        tag_list = []
    for t in tag_list:
        add_tag_to_source(db, source, t, "user")

    db.commit()
    db.refresh(source)
    return source_to_out(source)


@router.get("/api/sources/{source_id}", response_model=schemas.SourceOut)
def get_source(source_id: str, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "המקור לא נמצא")
    return source_to_out(source)


@router.patch("/api/sources/{source_id}", response_model=schemas.SourceOut)
def update_source(source_id: str, payload: schemas.SourceUpdate, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "המקור לא נמצא")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source_to_out(source)


@router.delete("/api/sources/{source_id}")
def delete_source(source_id: str, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "המקור לא נמצא")
    if source.file_path:
        try:
            Path(source.file_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(source)
    db.commit()
    return {"ok": True}


@router.post("/api/sources/{source_id}/tags", response_model=schemas.SourceOut)
def add_tag(source_id: str, payload: dict, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "המקור לא נמצא")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "יש להזין שם תגית")
    add_tag_to_source(db, source, name, "user")
    db.commit()
    db.refresh(source)
    return source_to_out(source)


@router.delete("/api/sources/{source_id}/tags/{tag_id}", response_model=schemas.SourceOut)
def remove_tag(source_id: str, tag_id: str, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "המקור לא נמצא")
    link = (
        db.query(models.SourceTag)
        .filter(models.SourceTag.source_id == source_id, models.SourceTag.tag_id == tag_id)
        .first()
    )
    if link:
        db.delete(link)
        db.commit()
    db.refresh(source)
    return source_to_out(source)


@router.post("/api/sources/{source_id}/analyze", response_model=schemas.AnalyzeResult)
def analyze_source(source_id: str, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "המקור לא נמצא")
    topic = source.topic

    existing_tags = [st.tag.name for st in source.tags]

    candidates = (
        db.query(models.Source)
        .filter(models.Source.id != source.id)
        .order_by(models.Source.date.desc())
        .limit(40)
        .all()
    )
    candidate_payload = [
        {
            "id": c.id,
            "topic_name": c.topic.name,
            "title": c.title,
            "date": str(c.date),
            "tags": [st.tag.name for st in c.tags],
            "snippet": (c.content or "")[:400],
        }
        for c in candidates
    ]

    known_tags = [
        name
        for name, _ in (
            db.query(models.Tag.name, func.count(models.SourceTag.source_id).label("n"))
            .join(models.SourceTag, models.SourceTag.tag_id == models.Tag.id)
            .group_by(models.Tag.id)
            .order_by(func.count(models.SourceTag.source_id).desc())
            .limit(60)
            .all()
        )
    ]

    try:
        result = claude_service.analyze_source(
            topic.name,
            topic.description,
            source.title,
            source.source_type,
            str(source.date),
            source.content or "",
            existing_tags,
            candidate_payload,
            known_tags,
        )
    except claude_service.ClaudeNotConfiguredError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"שגיאה בניתוח ה-AI: {exc}")

    suggested_tags = _filter_ai_tags(result.get("suggested_tags", []) or [], topic.name)
    for t in suggested_tags:
        add_tag_to_source(db, source, t, "ai")

    db.query(models.Insight).filter(models.Insight.source_id == source.id).delete()
    insight_map = {
        "facts": "fact",
        "decisions": "decision",
        "hypotheses": "hypothesis",
        "open_questions": "open_question",
        "action_items": "action_item",
    }
    created_insights = []
    for json_key, insight_type in insight_map.items():
        for item in result.get(json_key, []) or []:
            insight = models.Insight(source_id=source.id, insight_type=insight_type, content=item)
            db.add(insight)
            created_insights.append(insight)

    db.query(models.Connection).filter(models.Connection.source_id == source.id).delete()
    created_connections = []
    candidates_by_id = {c.id: c for c in candidates}
    for conn in result.get("connections", []) or []:
        related_id = conn.get("source_id")
        related = candidates_by_id.get(related_id)
        if not related:
            continue
        my_keys = {tag_utils.tag_key(n) for n in [*existing_tags, *suggested_tags]}
        shared = {st.tag.name for st in related.tags if tag_utils.tag_key(st.tag.name) in my_keys}
        c = models.Connection(
            source_id=source.id,
            related_source_id=related_id,
            description=conn.get("description", ""),
            shared_tags=", ".join(sorted(shared)),
        )
        db.add(c)
        created_connections.append(c)

    db.commit()
    db.refresh(source)

    suggested_keys = {tag_utils.tag_key(n) for t in suggested_tags for n in tag_utils.split_tag_input(t)}
    return {
        "suggested_tags": [
            t for t in source_to_out(source)["tags"] if t["origin"] == "ai" and tag_utils.tag_key(t["name"]) in suggested_keys
        ],
        "insights": [
            {
                "id": i.id,
                "source_id": source.id,
                "insight_type": i.insight_type,
                "content": i.content,
                "source_title": source.title,
                "source_date": source.date,
            }
            for i in created_insights
        ],
        "connections": [
            {
                "id": c.id,
                "source_id": c.source_id,
                "related_source_id": c.related_source_id,
                "description": c.description,
                "shared_tags": c.shared_tags,
                "source_title": source.title,
                "related_title": candidates_by_id[c.related_source_id].title,
                "related_topic_name": candidates_by_id[c.related_source_id].topic.name,
                "related_topic_id": candidates_by_id[c.related_source_id].topic_id,
            }
            for c in created_connections
        ],
    }
