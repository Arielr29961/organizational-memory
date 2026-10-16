from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..services import people_service

router = APIRouter(tags=["people"])


def _out(p: models.Person) -> dict:
    return {"id": p.id, "email": p.email, "name": p.name, "registered": bool(p.password_hash)}


@router.get("/api/people", response_model=list[schemas.PersonOut])
def list_people(q: str = "", db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    """Address book, optionally filtered by a substring of the name or e-mail."""
    query = db.query(models.Person)
    q = q.strip().lower()
    people = sorted(query.all(), key=lambda p: p.name.lower())
    if q:
        people = [p for p in people if q in p.name.lower() or q in p.email]
    return [_out(p) for p in people]


@router.post("/api/people", response_model=schemas.PersonOut)
def create_person(payload: schemas.PersonIn, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    try:
        person = people_service.get_or_create_person(db, payload.email, payload.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return _out(person)


@router.patch("/api/people/{person_id}", response_model=schemas.PersonOut)
def rename_person(person_id: str, payload: schemas.PersonUpdate, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    person = db.get(models.Person, person_id)
    if not person:
        raise HTTPException(404, "האדם לא נמצא")
    if person.password_hash and person.id != user.id:
        raise HTTPException(403, "אפשר לערוך רק את השם של עצמך, או של אדם שעוד לא נרשם")
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "יש להזין שם")
    person.name = name
    db.commit()
    return _out(person)
