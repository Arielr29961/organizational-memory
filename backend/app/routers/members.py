from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user, get_topic_as
from ..services import access_service, people_service

router = APIRouter(prefix="/api/topics/{topic_id}/members", tags=["members"])


class MemberIn(BaseModel):
    email: str
    name: str | None = None  # required only for an address that is not in the address book yet
    role: str = "viewer"


class MemberRole(BaseModel):
    role: str


def _check_role(role: str) -> None:
    if role not in access_service.MEMBER_ROLES:
        raise HTTPException(400, "תפקיד לא תקין (צופה או עורך)")


def _person_out(p: models.Person, role: str) -> dict:
    return {"person_id": p.id, "email": p.email, "name": p.name, "role": role, "registered": bool(p.password_hash)}


def _members_out(db: Session, topic: models.Topic) -> list[dict]:
    out = [_person_out(topic.owner, "owner")] if topic.owner else []
    members = db.query(models.TopicMember).filter(models.TopicMember.topic_id == topic.id).all()
    out += [_person_out(m.person, m.role) for m in sorted(members, key=lambda m: m.person.name.lower())]
    return out


@router.get("")
def list_members(topic_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    return _members_out(db, get_topic_as(db, user, topic_id, "viewer"))


@router.post("")
def add_member(topic_id: str, payload: MemberIn, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    """Share the topic with a person (owner only). Someone who has not registered yet sees it once they do."""
    topic = get_topic_as(db, user, topic_id, "owner")
    _check_role(payload.role)
    try:
        person = people_service.get_or_create_person(db, payload.email, payload.name)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    if person.id == topic.owner_id:
        raise HTTPException(400, "הבעלים כבר משויך לנושא")
    member = (
        db.query(models.TopicMember)
        .filter(models.TopicMember.topic_id == topic.id, models.TopicMember.person_id == person.id)
        .first()
    )
    if member:
        member.role = payload.role
    else:
        db.add(models.TopicMember(topic_id=topic.id, person_id=person.id, role=payload.role))
    db.commit()
    db.refresh(topic)
    return _members_out(db, topic)


@router.patch("/{person_id}")
def change_role(topic_id: str, person_id: str, payload: MemberRole, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    topic = get_topic_as(db, user, topic_id, "owner")
    _check_role(payload.role)
    member = (
        db.query(models.TopicMember)
        .filter(models.TopicMember.topic_id == topic.id, models.TopicMember.person_id == person_id)
        .first()
    )
    if not member:
        raise HTTPException(404, "החבר לא נמצא")
    member.role = payload.role
    db.commit()
    return _members_out(db, topic)


@router.delete("/{person_id}")
def remove_member(topic_id: str, person_id: str, db: Session = Depends(get_db), user: models.Person = Depends(get_current_user)):
    """The owner removes anyone; a member can remove themselves (leave the topic)."""
    topic = get_topic_as(db, user, topic_id, "viewer")
    if person_id == topic.owner_id:
        raise HTTPException(400, "אי אפשר להסיר את הבעלים")
    if person_id != user.id and topic.owner_id != user.id:
        raise HTTPException(403, "רק הבעלים יכול להסיר חברים אחרים")
    member = (
        db.query(models.TopicMember)
        .filter(models.TopicMember.topic_id == topic.id, models.TopicMember.person_id == person_id)
        .first()
    )
    if member:
        db.delete(member)
        db.commit()
    db.refresh(topic)
    return _members_out(db, topic) if topic.owner_id == user.id else []
