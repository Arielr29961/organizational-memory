from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import Base, engine, ensure_columns
from .routers import auth, chats, members, people, sources, tags, topics
from .services import access_service, auth_service

Base.metadata.create_all(bind=engine)
ensure_columns(
    {
        "chat_messages": {"attachment_name": "VARCHAR", "attachment_text": "TEXT", "context_tag": "VARCHAR"},
        "people": {"password_hash": "VARCHAR"},
        "topics": {"owner_id": "VARCHAR REFERENCES people(id)"},
        "chats": {"created_by": "VARCHAR REFERENCES people(id)"},
    }
)
auth_service.assign_orphan_topics()
access_service.backfill_chat_authors()

app = FastAPI(title="זיכרון ארגוני - Organizational Memory POC")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(topics.router)
app.include_router(members.router)
app.include_router(sources.router)
app.include_router(tags.router)
app.include_router(chats.router)
app.include_router(people.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
