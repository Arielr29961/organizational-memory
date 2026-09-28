from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..serializers import topic_to_out
from ..services import claude_service

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("", response_model=list[schemas.TopicOut])
def list_topics(q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Topic)
    if q:
        query = query.filter(models.Topic.name.ilike(f"%{q}%"))
    topics = query.order_by(models.Topic.created_at.desc()).all()
    return [topic_to_out(db, t) for t in topics]


@router.post("", response_model=schemas.TopicOut)
def create_topic(payload: schemas.TopicCreate, db: Session = Depends(get_db)):
    topic = models.Topic(name=payload.name, description=payload.description or "")
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic_to_out(db, topic)


@router.get("/{topic_id}", response_model=schemas.TopicOut)
def get_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    return topic_to_out(db, topic)


@router.patch("/{topic_id}", response_model=schemas.TopicOut)
def update_topic(topic_id: str, payload: schemas.TopicUpdate, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    if payload.name is not None:
        topic.name = payload.name
    if payload.description is not None:
        topic.description = payload.description
    db.commit()
    db.refresh(topic)
    return topic_to_out(db, topic)


@router.delete("/{topic_id}")
def delete_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    db.delete(topic)
    db.commit()
    return {"ok": True}


@router.get("/{topic_id}/insights", response_model=list[schemas.InsightOut])
def topic_insights(topic_id: str, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    results = []
    for source in sorted(topic.sources, key=lambda s: s.date):
        for insight in source.insights:
            results.append({
                "id": insight.id,
                "source_id": source.id,
                "insight_type": insight.insight_type,
                "content": insight.content,
                "source_title": source.title,
                "source_date": source.date,
            })
    return results


@router.get("/{topic_id}/connections", response_model=list[schemas.ConnectionOut])
def topic_connections(topic_id: str, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")
    source_ids = {s.id for s in topic.sources}
    sources_by_id = {s.id: s for s in topic.sources}
    results = []
    seen = set()
    connections = (
        db.query(models.Connection)
        .filter(models.Connection.source_id.in_(source_ids))
        .all()
    )
    for conn in connections:
        key = tuple(sorted([conn.source_id, conn.related_source_id])) + (conn.description,)
        if key in seen:
            continue
        seen.add(key)
        related = db.get(models.Source, conn.related_source_id)
        src = sources_by_id.get(conn.source_id)
        results.append({
            "id": conn.id,
            "source_id": conn.source_id,
            "related_source_id": conn.related_source_id,
            "description": conn.description,
            "shared_tags": conn.shared_tags or "",
            "source_title": src.title if src else None,
            "related_title": related.title if related else None,
            "related_topic_name": related.topic.name if related else None,
            "related_topic_id": related.topic_id if related else None,
        })
    return results


@router.post("/{topic_id}/ask", response_model=schemas.AskResponse)
def ask_ai(topic_id: str, payload: schemas.AskRequest, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(404, "הנושא לא נמצא")

    timeline_sources = sorted(topic.sources, key=lambda s: s.date)
    timeline_lines = []
    for s in timeline_sources:
        tag_names = ", ".join(st.tag.name for st in s.tags)
        timeline_lines.append(
            f"[{s.date}] ({s.source_type}) {s.title} | תגיות: {tag_names}\n{s.content[:3000]}"
        )
    timeline_text = "\n\n".join(timeline_lines) or "(אין עדיין מקורות בנושא זה)"

    topic_tag_names = {st.tag.name for s in timeline_sources for st in s.tags}
    cross_lines = []
    used_sources = [{"id": s.id, "title": s.title, "date": str(s.date), "topic_name": topic.name} for s in timeline_sources]
    if topic_tag_names:
        other_sources = (
            db.query(models.Source)
            .filter(models.Source.topic_id != topic_id)
            .all()
        )
        for s in other_sources:
            s_tags = {st.tag.name for st in s.tags}
            shared = topic_tag_names & s_tags
            if shared:
                cross_lines.append(
                    f"[{s.date}] נושא: {s.topic.name} | {s.title} | תגיות משותפות: {', '.join(shared)}\n"
                    f"תקציר: {s.content[:800]}"
                )
                used_sources.append({"id": s.id, "title": s.title, "date": str(s.date), "topic_name": s.topic.name})
    cross_text = "\n\n".join(cross_lines)

    try:
        answer = claude_service.ask_question(
            topic.name, topic.description, timeline_text, cross_text, payload.question
        )
    except claude_service.ClaudeNotConfiguredError as exc:
        raise HTTPException(400, str(exc))

    return {"answer": answer, "used_sources": used_sources}
