from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user, get_token
from ..services import auth_service, people_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str
    name: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


def _user_out(p: models.Person) -> dict:
    return {"id": p.id, "email": p.email, "name": p.name}


@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """Creates the account. An address that is already in the address book (not yet registered) is claimed."""
    email = people_service.normalize_email(payload.email)
    name = payload.name.strip()
    if not people_service.EMAIL_RE.match(email):
        raise HTTPException(400, "כתובת מייל לא תקינה")
    if not name:
        raise HTTPException(400, "יש להזין שם מלא")
    if len(payload.password) < auth_service.MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"הסיסמה חייבת להכיל לפחות {auth_service.MIN_PASSWORD_LENGTH} תווים")
    person = db.query(models.Person).filter(models.Person.email == email).first()
    if person and person.password_hash:
        raise HTTPException(400, "המייל הזה כבר רשום, יש להתחבר")
    if not person:
        person = models.Person(email=email, name=name)
        db.add(person)
    person.name = name
    person.password_hash = auth_service.hash_password(payload.password)
    db.commit()
    return {"token": auth_service.create_session(db, person), "user": _user_out(person)}


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    person = db.query(models.Person).filter(models.Person.email == people_service.normalize_email(payload.email)).first()
    if not person or not auth_service.verify_password(payload.password, person.password_hash):
        raise HTTPException(401, "מייל או סיסמה שגויים")
    return {"token": auth_service.create_session(db, person), "user": _user_out(person)}


@router.post("/logout")
def logout(token: str = Depends(get_token), db: Session = Depends(get_db)):
    auth_service.delete_session(db, token)
    return {"ok": True}


@router.get("/me")
def me(user: models.Person = Depends(get_current_user)):
    return _user_out(user)
