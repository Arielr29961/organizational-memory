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
from ..deps import get_current_user, get_source_as, get_topic_as
from ..serializers import source_to_out
from ..services import access_service, claude_service, file_extraction, people_service, tag_utils
from ..services.tag_service import add_tag_to_source, delete_if_unused

router = APIRouter(tags=["sources"])


@router.get("/api/topics/{topic_id}/sources", response_model=list[schemas.SourceOut])
def list_sources(topic_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    topic = get_topic_as(db, user, topic_id, "viewer")
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
    participants: str = Form("[]"),  # JSON list of {"email", "name"}
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db), user: models.Person = Depends(get_current_user),
):
    topic = get_topic_as(db, user, topic_id, "editor")

    try:
        participant_list = json.loads(participants) if participants else []
        if not isinstance(participant_list, list):
            raise ValueError("participants must be a list")
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "פורמט משתתפים לא תקין")

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
        for p in participant_list:
            people_service.add_participant(db, source, p.get("email", ""), p.get("name"))
    except (ValueError, AttributeError) as exc:
        db.rollback()
        if file_path_str:
            Path(file_path_str).unlink(missing_ok=True)
        raise HTTPException(400, str(exc))

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
def get_source(source_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    source = get_source_as(db, user, source_id, "viewer")
    return source_to_out(source)


@router.patch("/api/sources/{source_id}", response_model=schemas.SourceOut)
def update_source(source_id: str, payload: schemas.SourceUpdate, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    source = get_source_as(db, user, source_id, "editor")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source_to_out(source)


@router.delete("/api/sources/{source_id}")
def delete_source(source_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    source = get_source_as(db, user, source_id, "editor")
    if source.file_path:
        try:
            Path(source.file_path).unlink(missing_ok=True)
        except Exception:
            pass
    tag_ids = {st.tag_id for st in source.tags}
    db.delete(source)
    db.commit()
    delete_if_unused(db, tag_ids)
    return {"ok": True}


@router.post("/api/sources/{source_id}/tags", response_model=schemas.SourceOut)
def add_tag(source_id: str, payload: dict, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    source = get_source_as(db, user, source_id, "editor")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "יש להזין שם תגית")
    add_tag_to_source(db, source, name, "user")
    db.commit()
    db.refresh(source)
    return source_to_out(source)


@router.delete("/api/sources/{source_id}/tags/{tag_id}", response_model=schemas.SourceOut)
def remove_tag(source_id: str, tag_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    source = get_source_as(db, user, source_id, "editor")
    link = (
        db.query(models.SourceTag)
        .filter(models.SourceTag.source_id == source_id, models.SourceTag.tag_id == tag_id)
        .first()
    )
    if link:
        db.delete(link)
        db.commit()
        delete_if_unused(db, [tag_id])
    db.refresh(source)
    return source_to_out(source)


@router.post("/api/sources/{source_id}/participants", response_model=schemas.SourceOut)
def add_participant(source_id: str, payload: schemas.PersonIn, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    source = get_source_as(db, user, source_id, "editor")
    try:
        people_service.add_participant(db, source, payload.email, payload.name)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    db.commit()
    db.refresh(source)
    return source_to_out(source)


@router.delete("/api/sources/{source_id}/participants/{person_id}", response_model=schemas.SourceOut)
def remove_participant(source_id: str, person_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    source = get_source_as(db, user, source_id, "editor")
    link = (
        db.query(models.SourceParticipant)
        .filter(models.SourceParticipant.source_id == source_id, models.SourceParticipant.person_id == person_id)
        .first()
    )
    if link:
        db.delete(link)
        db.commit()
    db.refresh(source)
    return source_to_out(source)


@router.post("/api/sources/{source_id}/analyze", response_model=schemas.AnalyzeResult)
def analyze_source(source_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    source = get_source_as(db, user, source_id, "editor")
    topic = source.topic

    existing_tags = [st.tag.name for st in source.tags]

    known_tags = [
        name
        for name, _ in (
            db.query(models.Tag.name, func.count(models.SourceTag.source_id).label("n"))
            .join(models.SourceTag, models.SourceTag.tag_id == models.Tag.id)
            .join(models.Source, models.Source.id == models.SourceTag.source_id)
            .join(models.Topic, models.Topic.id == models.Source.topic_id)
            .filter(models.Topic.id.in_(access_service.accessible_topic_ids(db, user)))
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
            known_tags,
            [sp.person.name for sp in source.participants],
        )
    except claude_service.ClaudeNotConfiguredError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"שגיאה בניתוח ה-AI: {exc}")

    suggested_tags = tag_utils.filter_ai_tags(result.get("suggested_tags", []) or [], topic.name)
    for t in suggested_tags:
        add_tag_to_source(db, source, t, "ai")
    db.commit()
    db.refresh(source)

    suggested_keys = {tag_utils.tag_key(n) for t in suggested_tags for n in tag_utils.split_tag_input(t)}
    return {
        "suggested_tags": [
            t for t in source_to_out(source)["tags"] if t["origin"] == "ai" and tag_utils.tag_key(t["name"]) in suggested_keys
        ],
    }
