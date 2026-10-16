"""Intake: imported files become proposals (topic, title, date, tags, participants) that the user approves."""
import hashlib
import json
import logging
import re
import shutil
import uuid
from datetime import date as date_type
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models
from ..config import UPLOAD_DIR
from ..database import SessionLocal
from . import access_service, claude_service, file_extraction, people_service, tag_service, tag_utils

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".md", ".eml"}
SOURCE_TYPES = {"meeting_transcript", "meeting_summary", "email", "presentation", "spreadsheet", "document", "other"}
MAX_FILES_PER_BATCH = 50
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_CONTENT_CHARS = 300000
MAX_TOPICS_IN_PROMPT = 60
MAX_PARTICIPANTS = 20


class IntakeError(Exception):
    """A problem the user can read (shown next to the item)."""


# ---------- storing uploads

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create_items(db: Session, user: models.Person, files: list[tuple[str, "object"]]) -> tuple[list[models.IntakeItem], list[dict]]:
    """files: [(original name, binary stream)]. Returns (new items in status 'processing', skipped files with a reason)."""
    created, skipped = [], []
    for name, stream in files[:MAX_FILES_PER_BATCH]:
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            skipped.append({"file_name": name, "reason": "סוג קובץ לא נתמך"})
            continue
        dest = UPLOAD_DIR / f"intake-{uuid.uuid4()}{ext}"
        with dest.open("wb") as out:
            shutil.copyfileobj(stream, out)
        if dest.stat().st_size > MAX_FILE_BYTES:
            dest.unlink(missing_ok=True)
            skipped.append({"file_name": name, "reason": "הקובץ גדול מדי (מעל 20MB)"})
            continue
        digest = _sha256(dest)
        same = db.query(models.IntakeItem).filter(models.IntakeItem.owner_id == user.id, models.IntakeItem.file_hash == digest).first()
        if same and same.status == "approved" and not (same.source_id and db.get(models.Source, same.source_id)):
            db.delete(same)  # imported once, but that source was deleted since: allow importing again
            same = None
        if same:
            dest.unlink(missing_ok=True)
            skipped.append({"file_name": name, "reason": "הקובץ כבר יובא או ממתין בתיבת ההצעות"})
            continue
        item = models.IntakeItem(owner_id=user.id, status="processing", file_name=name, file_path=str(dest), file_hash=digest)
        db.add(item)
        db.flush()  # the session does not autoflush: without this the same file twice in one batch is not noticed
        created.append(item)
    skipped += [{"file_name": n, "reason": f"מעל {MAX_FILES_PER_BATCH} קבצים בהעלאה אחת"} for n, _ in files[MAX_FILES_PER_BATCH:]]
    db.commit()
    return created, skipped


def mark_interrupted() -> None:
    """Items still 'processing' when the server starts lost their worker (restart): the user can retry them."""
    with SessionLocal() as db:
        stuck = db.query(models.IntakeItem).filter(models.IntakeItem.status == "processing").all()
        for item in stuck:
            item.status = "error"
            item.error = "העיבוד הופסק (הפעלה מחדש של השרת). אפשר לנסות שוב."
        if stuck:
            db.commit()


# ---------- the AI proposal

def _editable_topics(db: Session, user: models.Person) -> list[models.Topic]:
    topics = db.query(models.Topic).filter(models.Topic.id.in_(access_service.accessible_topic_ids(db, user))).order_by(models.Topic.created_at.desc()).all()
    return [t for t in topics if access_service.has_role(access_service.role_in_topic(db, user, t), "editor")][:MAX_TOPICS_IN_PROMPT]


def _topic_entries(topics: list[models.Topic]) -> list[dict]:
    entries = []
    for i, t in enumerate(topics, start=1):
        recent = sorted(t.sources, key=lambda s: s.date, reverse=True)[:5]
        tag_counts: dict[str, int] = {}
        for s in t.sources:
            for st in s.tags:
                tag_counts[st.tag.name] = tag_counts.get(st.tag.name, 0) + 1
        top = sorted(tag_counts, key=lambda n: tag_counts[n], reverse=True)[:8]
        entries.append({"key": f"t{i}", "topic": t, "name": t.name, "description": (t.description or "")[:300], "recent_titles": [s.title for s in recent], "top_tags": top})
    return entries


def _known_tags(db: Session, user: models.Person) -> list[str]:
    return [t["name"] for t in tag_service.tags_with_counts(db, access_service.accessible_topic_ids(db, user))[:60]]


def _person_pairs(candidates: list[tuple[str, str]], db: Session, notes: list[str]) -> list[dict]:
    """(display name, e-mail) -> participants. A known address uses the stored name; a new one needs a real name."""
    result, seen = [], set()
    for name, email in candidates:
        email = people_service.normalize_email(email)
        if not people_service.EMAIL_RE.match(email) or email in seen:
            continue
        seen.add(email)
        known = db.query(models.Person).filter(models.Person.email == email).first()
        display = known.name if known else (name or "").strip()
        if not display or display.lower() == email:
            notes.append(f"{email}: לא נמצא שם, לא נוסף כמשתתף")
            continue
        result.append({"email": email, "name": display})
    return result[:MAX_PARTICIPANTS]


def process_items(item_ids: list[str]) -> None:
    """Background worker: one file after the other (a click on 'upload' is the only trigger)."""
    for item_id in item_ids:
        with SessionLocal() as db:
            item = db.get(models.IntakeItem, item_id)
            if not item or item.status != "processing":
                continue
            try:
                _process(db, item)
            except claude_service.ClaudeNotConfiguredError as exc:
                item.status, item.error = "error", str(exc)
            except IntakeError as exc:
                item.status, item.error = "error", str(exc)
            except Exception as exc:  # network, bad JSON, corrupt file...
                log.exception("intake processing failed for %s", item_id)
                item.status, item.error = "error", f"שגיאה בעיבוד הקובץ: {exc}"
            db.commit()


def _process(db: Session, item: models.IntakeItem) -> None:
    owner = db.get(models.Person, item.owner_id)
    path = Path(item.file_path)
    ext = path.suffix.lower()

    mail = None
    if ext == ".eml":
        mail = file_extraction.parse_eml(path)
        text = file_extraction.eml_to_text(mail)
    else:
        text = file_extraction.extract_text(path, item.file_name)
    if not text.strip() or text.lstrip().startswith("[שגיאה") or text.lstrip().startswith("[לא ניתן"):
        raise IntakeError("לא ניתן היה לחלץ טקסט מהקובץ")
    item.content = text[:MAX_CONTENT_CHARS]

    entries = _topic_entries(_editable_topics(db, owner))
    headers = None
    if mail:
        headers = f"נושא: {mail['subject']}; תאריך: {mail['date'] or '-'}"
    raw = claude_service.propose_intake(item.file_name, text, entries, _known_tags(db, owner), str(date_type.today()), headers)
    if not isinstance(raw, dict):
        raise IntakeError("תשובת ה-AI לא הייתה תקינה")
    _apply_proposal(db, item, raw, entries, text, mail)


def _apply_proposal(db: Session, item: models.IntakeItem, raw: dict, entries: list[dict], text: str, mail: dict | None) -> None:
    by_key = {e["key"]: e for e in entries}
    chosen = by_key.get(raw.get("topic")) if isinstance(raw.get("topic"), str) else None
    item.topic_id = chosen["topic"].id if chosen else None
    new_name = raw.get("new_topic_name")
    item.new_topic_name = new_name.strip()[:100] if (not chosen and isinstance(new_name, str) and new_name.strip()) else None

    confidence = raw.get("confidence") if raw.get("confidence") in ("high", "medium", "low") else "low"
    item.confidence = confidence if chosen else "low"
    item.reason = str(raw.get("reason") or "")[:500]

    title = str(raw.get("title") or "").strip()
    if mail and mail["subject"]:
        title = title or mail["subject"]
    item.title = (title or Path(item.file_name).stem)[:200]
    item.description = str(raw.get("description") or "")[:1000]

    if mail:
        item.source_type = "email"
    else:
        item.source_type = raw.get("source_type") if raw.get("source_type") in SOURCE_TYPES else "document"

    parsed = None
    if mail and mail["date"]:
        parsed = mail["date"]  # the e-mail's own header is more reliable than anything the model reads from the text
    else:
        try:
            parsed = date_type.fromisoformat(str(raw.get("date"))) if raw.get("date") else None
        except ValueError:
            parsed = None
    item.date = parsed or date_type.today()

    item.tags = json.dumps(tag_utils.filter_ai_tags(raw.get("tags") or [], chosen["name"] if chosen else ""), ensure_ascii=False)

    notes: list[str] = []
    if mail:
        candidates = mail["from"] + mail["to"] + mail["cc"]
    else:
        lowered = text.lower()
        candidates = []
        for p in raw.get("participants") or []:
            if isinstance(p, dict) and isinstance(p.get("email"), str) and p["email"].strip().lower() in lowered:
                candidates.append((str(p.get("name") or ""), p["email"]))
    item.participants = json.dumps(_person_pairs(candidates, db, notes), ensure_ascii=False)
    if mail and mail["attachments"]:
        notes.append("קבצים מצורפים למייל לא נקראו: " + ", ".join(mail["attachments"]))
    item.notes = json.dumps(notes, ensure_ascii=False)
    item.status = "pending"
    item.error = None


# ---------- approving / rejecting

def approve_item(db: Session, user: models.Person, item: models.IntakeItem) -> models.Source:
    """Creates the real source. Raises IntakeError with a readable message; the caller rolls back."""
    if item.status != "pending":
        raise IntakeError("ההצעה אינה ממתינה לאישור")
    title = (item.title or "").strip()
    if not title:
        raise IntakeError("חסרה כותרת")
    if item.source_type not in SOURCE_TYPES:
        raise IntakeError("סוג המקור לא תקין")
    if not item.date:
        raise IntakeError("חסר תאריך")

    if item.topic_id:
        topic = db.get(models.Topic, item.topic_id)
        if not topic or not access_service.has_role(access_service.role_in_topic(db, user, topic), "editor"):
            raise IntakeError("אין לך הרשאת עריכה בנושא שנבחר")
    elif (item.new_topic_name or "").strip():
        topic = models.Topic(name=item.new_topic_name.strip(), description="", owner_id=user.id)
        db.add(topic)
        db.flush()
    else:
        raise IntakeError("יש לבחור נושא (או לתת שם לנושא חדש)")

    source = models.Source(
        topic_id=topic.id,
        title=title,
        source_type=item.source_type,
        date=item.date,
        content=item.content or "",
        description=item.description or "",
        file_name=item.file_name,
        file_path=item.file_path,
    )
    db.add(source)
    db.flush()
    try:
        for p in json.loads(item.participants or "[]"):
            people_service.add_participant(db, source, p.get("email", ""), p.get("name"))
    except (ValueError, AttributeError) as exc:
        raise IntakeError(str(exc))
    for tag in json.loads(item.tags or "[]"):
        tag_service.add_tag_to_source(db, source, tag, "ai")

    item.status = "approved"
    item.source_id = source.id
    item.topic_id = topic.id
    item.new_topic_name = None
    item.content = ""  # it now lives in the source
    return source


def delete_item(db: Session, item: models.IntakeItem) -> None:
    """Reject: the proposal and its stored file are removed (an approved item's file belongs to its source)."""
    if item.status != "approved":
        Path(item.file_path).unlink(missing_ok=True)
    db.delete(item)
