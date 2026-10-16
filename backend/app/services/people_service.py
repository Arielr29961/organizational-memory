import re

from sqlalchemy.orm import Session

from .. import models

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_or_create_person(db: Session, email: str, name: str | None) -> models.Person:
    """Existing address -> its stored person (the stored name wins). New address -> a real e-mail and a name are required."""
    email = normalize_email(email)
    if not EMAIL_RE.match(email):
        raise ValueError(f"כתובת מייל לא תקינה: {email or '(ריקה)'}")
    person = db.query(models.Person).filter(models.Person.email == email).first()
    if person:
        return person
    name = (name or "").strip()
    if not name:
        raise ValueError(f"המייל {email} חדש בספר האנשים — יש להזין גם את השם המלא")
    person = models.Person(email=email, name=name)
    db.add(person)
    db.flush()
    return person


def add_participant(db: Session, source: models.Source, email: str, name: str | None) -> models.Person:
    person = get_or_create_person(db, email, name)
    if not any(sp.person_id == person.id for sp in source.participants):
        db.add(models.SourceParticipant(source_id=source.id, person_id=person.id))
        db.flush()
        db.refresh(source)
    return person
