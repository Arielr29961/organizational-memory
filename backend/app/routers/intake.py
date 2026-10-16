import json
from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user
from ..services import access_service, intake_service, people_service

router = APIRouter(prefix="/api/intake", tags=["intake"])


class IntakeUpdate(BaseModel):
    topic_id: Optional[str] = None
    new_topic_name: Optional[str] = None
    title: Optional[str] = None
    date: Optional[date_type] = None
    source_type: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    participants: Optional[List[dict]] = None  # [{"email", "name"}]
    clear_topic: bool = False  # topic_id/new_topic_name = None means "unchanged", so clearing needs a flag


class IdList(BaseModel):
    ids: List[str]


def _out(item: models.IntakeItem, db: Session) -> dict:
    topic = db.get(models.Topic, item.topic_id) if item.topic_id else None
    return {
        "id": item.id,
        "status": item.status,
        "error": item.error,
        "file_name": item.file_name,
        "topic_id": item.topic_id,
        "topic_name": topic.name if topic else None,
        "new_topic_name": item.new_topic_name,
        "title": item.title or "",
        "date": item.date,
        "source_type": item.source_type,
        "description": item.description or "",
        "tags": json.loads(item.tags or "[]"),
        "participants": json.loads(item.participants or "[]"),
        "notes": json.loads(item.notes or "[]"),
        "reason": item.reason or "",
        "confidence": item.confidence,
        "content_preview": (item.content or "")[:600],
        "content_length": len(item.content or ""),
        "created_at": item.created_at,
    }


def _own_item(db: Session, user: models.Person, item_id: str) -> models.IntakeItem:
    item = db.get(models.IntakeItem, item_id)
    if not item or item.owner_id != user.id:
        raise HTTPException(404, "ההצעה לא נמצאה")
    return item


@router.get("")
def list_items(db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    """The user's open proposals (approved ones are only kept to recognize the same file later)."""
    items = (
        db.query(models.IntakeItem)
        .filter(models.IntakeItem.owner_id == user.id, models.IntakeItem.status != "approved")
        .order_by(models.IntakeItem.created_at.desc())
        .all()
    )
    return [_out(i, db) for i in items]


@router.post("/upload")
def upload(
    background: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: models.Person = Depends(get_current_user),
):
    created, skipped = intake_service.create_items(db, user, [(f.filename or "file", f.file) for f in files])
    if created:
        background.add_task(intake_service.process_items, [i.id for i in created])
    return {"created": len(created), "skipped": skipped}


@router.get("/folder")
def folder(user: models.Person = Depends(get_current_user)):
    """The user's drop folder: where it is and how many supported files wait in it."""
    return intake_service.folder_status(user)


@router.post("/folder/open")
def folder_open(user: models.Person = Depends(get_current_user)):
    try:
        intake_service.open_folder(user)
    except OSError as exc:
        raise HTTPException(500, f"לא ניתן לפתוח את התיקייה: {exc}")
    return {"ok": True}


@router.post("/scan")
def scan(background: BackgroundTasks, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    """'Scan now': take the files waiting in the user's drop folder into the inbox."""
    created, skipped, info = intake_service.scan_folder(db, user)
    if created:
        background.add_task(intake_service.process_items, [i.id for i in created])
    return {"created": len(created), "skipped": skipped, **info}


@router.patch("/{item_id}")
def update_item(item_id: str, payload: IntakeUpdate, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    item = _own_item(db, user, item_id)
    if item.status not in ("pending", "error"):
        raise HTTPException(400, "אי אפשר לערוך הצעה שעדיין מעובדת")
    data = payload.model_dump(exclude_unset=True)
    if "topic_id" in data and data["topic_id"]:
        topic = db.get(models.Topic, data["topic_id"])
        if not topic or not access_service.has_role(access_service.role_in_topic(db, user, topic), "editor"):
            raise HTTPException(403, "אין לך הרשאת עריכה בנושא הזה")
        item.topic_id = topic.id
        item.new_topic_name = None
    if data.get("new_topic_name"):
        item.new_topic_name = data["new_topic_name"].strip()[:100]
        item.topic_id = None
    if data.get("clear_topic"):
        item.topic_id = None
        item.new_topic_name = None
    if "title" in data and data["title"] is not None:
        item.title = data["title"].strip()[:200]
    if "date" in data and data["date"] is not None:
        item.date = data["date"]
    if data.get("source_type"):
        if data["source_type"] not in intake_service.SOURCE_TYPES:
            raise HTTPException(400, "סוג מקור לא תקין")
        item.source_type = data["source_type"]
    if "description" in data and data["description"] is not None:
        item.description = data["description"][:1000]
    if "tags" in data and data["tags"] is not None:
        item.tags = json.dumps([t.strip() for t in data["tags"] if t and t.strip()], ensure_ascii=False)
    if "participants" in data and data["participants"] is not None:
        cleaned = []
        for p in data["participants"]:
            email = people_service.normalize_email(str(p.get("email", "")))
            name = str(p.get("name", "")).strip()
            if not people_service.EMAIL_RE.match(email):
                raise HTTPException(400, f"כתובת מייל לא תקינה: {email or '(ריקה)'}")
            known = db.query(models.Person).filter(models.Person.email == email).first()
            if not known and not name:
                raise HTTPException(400, f"המייל {email} חדש בספר האנשים, יש להזין גם שם")
            cleaned.append({"email": email, "name": known.name if known else name})
        item.participants = json.dumps(cleaned, ensure_ascii=False)
    db.commit()
    return _out(item, db)


@router.post("/approve")
def approve(payload: IdList, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    """Approve several proposals; each one succeeds or fails on its own."""
    results = []
    for item_id in payload.ids:
        item = db.get(models.IntakeItem, item_id)
        if not item or item.owner_id != user.id:
            results.append({"id": item_id, "ok": False, "error": "ההצעה לא נמצאה"})
            continue
        try:
            source = intake_service.approve_item(db, user, item)
            db.commit()
            results.append({"id": item_id, "ok": True, "source_id": source.id, "topic_id": source.topic_id})
        except intake_service.IntakeError as exc:
            db.rollback()
            results.append({"id": item_id, "ok": False, "error": str(exc)})
    return {"results": results}


@router.post("/reject")
def reject(payload: IdList, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    deleted = 0
    for item_id in payload.ids:
        item = db.get(models.IntakeItem, item_id)
        if item and item.owner_id == user.id and item.status != "processing":
            intake_service.delete_item(db, item)
            deleted += 1
    db.commit()
    return {"deleted": deleted}


@router.post("/{item_id}/retry")
def retry(item_id: str, background: BackgroundTasks, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    item = _own_item(db, user, item_id)
    if item.status != "error":
        raise HTTPException(400, "אפשר לנסות שוב רק הצעה שנכשלה")
    item.status = "processing"
    item.error = None
    db.commit()
    background.add_task(intake_service.process_items, [item.id])
    return _out(item, db)
