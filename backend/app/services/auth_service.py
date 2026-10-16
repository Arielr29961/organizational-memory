"""Passwords and login sessions (standard library only: scrypt hashing, random opaque tokens)."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models

SESSION_DAYS = 30
MIN_PASSWORD_LENGTH = 8
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def assign_orphan_topics() -> None:
    """Topics created before accounts existed get the default owner (the person is added to the address book if needed)."""
    from ..config import DEFAULT_OWNER_EMAIL, DEFAULT_OWNER_NAME
    from ..database import SessionLocal

    with SessionLocal() as db:
        orphans = db.query(models.Topic).filter(models.Topic.owner_id.is_(None)).all()
        if not orphans:
            return
        owner = db.query(models.Person).filter(models.Person.email == DEFAULT_OWNER_EMAIL.lower()).first()
        if not owner:
            owner = models.Person(email=DEFAULT_OWNER_EMAIL.lower(), name=DEFAULT_OWNER_NAME)
            db.add(owner)
            db.flush()
        for topic in orphans:
            topic.owner_id = owner.id
        db.commit()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, person: models.Person) -> str:
    """Returns the raw token (only its hash is stored)."""
    token = secrets.token_urlsafe(32)
    db.add(models.AuthSession(token_hash=_token_hash(token), person_id=person.id))
    db.commit()
    return token


def person_for_token(db: Session, token: str) -> models.Person | None:
    session = db.query(models.AuthSession).filter(models.AuthSession.token_hash == _token_hash(token)).first()
    if not session:
        return None
    if session.created_at < datetime.utcnow() - timedelta(days=SESSION_DAYS):
        db.delete(session)
        db.commit()
        return None
    return session.person


def delete_session(db: Session, token: str) -> None:
    session = db.query(models.AuthSession).filter(models.AuthSession.token_hash == _token_hash(token)).first()
    if session:
        db.delete(session)
        db.commit()
