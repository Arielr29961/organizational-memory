"""Intake: imported files become proposals (topic, title, date, tags, participants) that the user approves."""
import hashlib
import contextlib
import json
import logging
import re
import shutil
import sys
import threading
import time
import uuid
from datetime import date as date_type
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models
from ..config import INBOX_DIR, UPLOAD_DIR
from ..database import SessionLocal
from . import access_service, claude_service, file_extraction, people_service, tag_service, tag_utils

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".md", ".eml", ".msg", ".pptx"}
SOURCE_TYPES = {"meeting_transcript", "meeting_summary", "email", "presentation", "spreadsheet", "document", "other"}
MAX_FILES_PER_BATCH = 50
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_CONTENT_CHARS = 300000
MAX_TOPICS_IN_PROMPT = 60
MAX_PARTICIPANTS = 20
MAX_ATTACHMENTS = 10  # attachments imported per mail
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENT_TEXT = 20000  # characters of one attachment kept in the source
AI_ATTACHMENT_CHARS = 6000  # characters of one attachment shown to the model
AI_TOTAL_CHARS = 30000


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
            skipped.append({"file_name": name, "code": "unsupported", "reason": "סוג קובץ לא נתמך"})
            continue
        dest = UPLOAD_DIR / f"intake-{uuid.uuid4()}{ext}"
        with dest.open("wb") as out:
            shutil.copyfileobj(stream, out)
        if dest.stat().st_size > MAX_FILE_BYTES:
            dest.unlink(missing_ok=True)
            skipped.append({"file_name": name, "code": "too_big", "reason": "הקובץ גדול מדי (מעל 20MB)"})
            continue
        digest = _sha256(dest)
        same = db.query(models.IntakeItem).filter(models.IntakeItem.owner_id == user.id, models.IntakeItem.file_hash == digest).first()
        if same and same.status == "approved" and not (same.source_id and db.get(models.Source, same.source_id)):
            db.delete(same)  # imported once, but that source was deleted since: allow importing again
            same = None
        if same:
            dest.unlink(missing_ok=True)
            skipped.append({"file_name": name, "code": "duplicate", "reason": "הקובץ כבר יובא או ממתין בתיבת ההצעות"})
            continue
        item = models.IntakeItem(owner_id=user.id, status="processing", file_name=name, file_path=str(dest), file_hash=digest)
        db.add(item)
        db.flush()  # the session does not autoflush: without this the same file twice in one batch is not noticed
        created.append(item)
    skipped += [{"file_name": n, "code": "over_limit", "reason": f"מעל {MAX_FILES_PER_BATCH} קבצים בהעלאה אחת"} for n, _ in files[MAX_FILES_PER_BATCH:]]
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
    # an address that comes with a real name wins over a nameless copy of the same address
    candidates = sorted(candidates, key=lambda c: not ((c[0] or "").strip() and (c[0] or "").strip().lower() != (c[1] or "").strip().lower()))
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
    ai_text = None
    attachment_notes: list[str] = []
    _delete_attachments(db, item)  # leftovers of an earlier attempt (retry)
    if ext in file_extraction.MAIL_EXTENSIONS:
        mail = file_extraction.parse_mail(path, with_attachments=True)
        text = file_extraction.eml_to_text(mail, mention_attachments=False)
    else:
        text = file_extraction.extract_text(path, item.file_name)
    if not text.strip() or text.lstrip().startswith("[שגיאה") or text.lstrip().startswith("[לא ניתן"):
        raise IntakeError("לא ניתן היה לחלץ טקסט מהקובץ")
    if mail:
        content_extra, ai_extra, attachment_notes = _ingest_attachments(db, item, mail)
        ai_text = (text[:12000] + ("\n\n" + ai_extra if ai_extra else ""))[:AI_TOTAL_CHARS]
        text = text + ("\n\n" + content_extra if content_extra else "")
    item.content = text[:MAX_CONTENT_CHARS]

    entries = _topic_entries(_editable_topics(db, owner))
    headers = None
    if mail:
        headers = f"נושא: {mail['subject']}; תאריך: {mail['date'] or '-'}"
    raw = claude_service.propose_intake(item.file_name, ai_text or text, entries, _known_tags(db, owner), str(date_type.today()), headers)
    if not isinstance(raw, dict):
        raise IntakeError("תשובת ה-AI לא הייתה תקינה")
    _apply_proposal(db, item, raw, entries, text, mail, attachment_notes)


def _ingest_attachments(db: Session, item: models.IntakeItem, mail: dict) -> tuple[str, str, list[str]]:
    """Stores the mail's attachments for download and reads the ones that have text. Returns (text sections for the
    source content, shorter sections for the model, notes about what could not be used)."""
    files = mail.get("attachment_files") or []
    notes: list[str] = []
    if len(files) > MAX_ATTACHMENTS:
        notes.append(f"{len(files) - MAX_ATTACHMENTS} קבצים מצורפים נוספים לא יובאו (מעל {MAX_ATTACHMENTS} למייל)")
        files = files[:MAX_ATTACHMENTS]
    content_parts, ai_parts = [], []
    for f in files:
        name = Path(f["name"]).name or "attachment"
        data = f["data"]
        if len(data) > MAX_ATTACHMENT_BYTES:
            notes.append(f"{name}: גדול מדי (מעל 20MB), לא יובא")
            continue
        ext = Path(name).suffix.lower()
        dest = UPLOAD_DIR / f"att-{uuid.uuid4()}{ext}"
        dest.write_bytes(data)
        db.add(models.IntakeAttachment(item_id=item.id, file_name=name, file_path=str(dest), size=len(data)))
        if ext not in ALLOWED_EXTENSIONS:
            notes.append(f"{name}: סוג קובץ שאינו נקרא, נשמר להורדה בלבד")
            continue
        text = file_extraction.extract_text(dest, name)
        if text.lstrip().startswith(("[שגיאה", "[לא ניתן")):
            notes.append(f"{name}: לא ניתן היה לקרוא את הטקסט, נשמר להורדה בלבד")
        elif not text.strip():
            notes.append(f"{name}: לא נמצא בו טקסט (אולי סריקה), נשמר להורדה בלבד")
        else:
            cut = text[:MAX_ATTACHMENT_TEXT] + ("\n[... הקובץ קוצר עקב אורכו ...]" if len(text) > MAX_ATTACHMENT_TEXT else "")
            content_parts.append(f"--- קובץ מצורף: {name} ---\n{cut}")
            ai_parts.append(f"--- קובץ מצורף: {name} ---\n{text[:AI_ATTACHMENT_CHARS]}")
    for name in mail.get("attachment_skipped") or []:
        notes.append(f"{name}: לא ניתן היה לשלוף את הקובץ (למשל הודעה מוטמעת), לא יובא")
    db.flush()
    return "\n\n".join(content_parts), "\n\n".join(ai_parts), notes


def _delete_attachments(db: Session, item: models.IntakeItem) -> None:
    """Removes the stored attachments of a proposal (rows and files)."""
    for a in list(item.attachments):
        Path(a.file_path).unlink(missing_ok=True)
        db.delete(a)
    db.flush()


def _apply_proposal(db: Session, item: models.IntakeItem, raw: dict, entries: list[dict], text: str, mail: dict | None, extra_notes: list[str] | None = None) -> None:
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
    # Header people first (mail files), then people the model found whose address literally appears in the text -
    # for a mail that includes the senders of quoted/forwarded messages in the body.
    candidates = (mail["from"] + mail["to"] + mail["cc"]) if mail else []
    lowered = text.lower()
    for p in raw.get("participants") or []:
        if isinstance(p, dict) and isinstance(p.get("email"), str) and p["email"].strip().lower() in lowered:
            name = str(p.get("name") or "").strip()
            if name.lower() not in lowered:
                name = ""  # a name the model made up (e.g. from the address) is not a name found in the file
            candidates.append((name, p["email"]))
    item.participants = json.dumps(_person_pairs(candidates, db, notes), ensure_ascii=False)
    notes.extend(extra_notes or [])
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

    for a in list(item.attachments):  # the files stay where they are; they now belong to the source
        db.add(models.SourceAttachment(source_id=source.id, file_name=a.file_name, file_path=a.file_path, size=a.size))
        db.delete(a)

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
        for a in item.attachments:
            Path(a.file_path).unlink(missing_ok=True)
    db.delete(item)


# ---------- the "drop here" folder (one per user; a scan is the only trigger)

def user_folder(user: models.Person) -> Path:
    safe = re.sub(r"[^a-z0-9@._+-]", "_", user.email.lower())
    folder = INBOX_DIR / safe
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _folder_files(folder: Path) -> tuple[list[Path], list[str]]:
    """(supported files waiting, names of files that are ignored). Sub-folders, temp files and hidden files are not scanned."""
    waiting, ignored = [], []
    for p in sorted((x for x in folder.iterdir() if x.is_file()), key=lambda x: x.stat().st_mtime):
        if p.name.startswith(("~$", ".")):
            continue
        if p.suffix.lower() in ALLOWED_EXTENSIONS:
            waiting.append(p)
        else:
            ignored.append(p.name)
    return waiting, ignored


def folder_status(user: models.Person) -> dict:
    folder = user_folder(user)
    waiting, ignored = _folder_files(folder)
    return {"path": str(folder), "waiting": len(waiting), "ignored": ignored}


def _raise_explorer_window(folder_name: str, timeout: float = 5.0) -> bool:
    """Windows opens the folder window behind the browser when the request comes from a background process. Find the
    Explorer window (class CabinetWClass) of this folder and bring it to the front. Best effort: returns whether it worked."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value != "CabinetWClass":
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if folder_name.lower() in title.value.lower():
            found.append(hwnd)
            return False
        return True

    deadline = time.time() + timeout
    while time.time() < deadline and not found:
        user32.EnumWindows(enum_proc(visit), 0)
        if not found:
            time.sleep(0.2)
    if not found:
        return False
    hwnd = found[0]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE: un-minimize
    user32.keybd_event(0x12, 0, 0, 0)  # a tap on Alt makes Windows allow SetForegroundWindow from this process
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    return user32.GetForegroundWindow() == hwnd


def open_folder(user: models.Person) -> None:
    """Opens the user's drop folder in the file manager of the machine that runs the backend (a local POC convenience)."""
    import os
    import subprocess

    folder = str(user_folder(user))
    if sys.platform == "win32":
        os.startfile(folder)  # noqa: S606 - a path the app created itself
        threading.Thread(target=_raise_explorer_window, args=(Path(folder).name,), daemon=True).start()
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


def scan_folder(db: Session, user: models.Person) -> tuple[list[models.IntakeItem], list[dict], dict]:
    """Takes up to MAX_FILES_PER_BATCH files of the user's folder into the inbox. Files that were taken in (or already
    imported) move to processed/; unsupported, oversized and surplus files stay where they are."""
    folder = user_folder(user)
    waiting, _ignored = _folder_files(folder)
    batch = waiting[:MAX_FILES_PER_BATCH]
    with contextlib.ExitStack() as stack:
        streams = [(p.name, stack.enter_context(p.open("rb"))) for p in batch]
        created, skipped = create_items(db, user, streams)

    done = {i.file_name for i in created} | {s["file_name"] for s in skipped if s["code"] == "duplicate"}
    processed = folder / "processed"
    not_moved = []
    for p in batch:
        if p.name not in done:
            continue
        try:
            processed.mkdir(exist_ok=True)
            shutil.move(str(p), str(processed / f"{time.strftime('%Y%m%d-%H%M%S')}-{p.name}"))
        except OSError:  # e.g. the file is open in another program
            not_moved.append(p.name)
    return created, skipped, {"remaining": len(waiting) - len(batch), "not_moved": not_moved}
