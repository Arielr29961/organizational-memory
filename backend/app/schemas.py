from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


# ---------- Tags ----------

class TagOut(BaseModel):
    id: str
    name: str
    origin: str

    class Config:
        from_attributes = True


class TagWithCount(BaseModel):
    id: str
    name: str
    count: int


# ---------- Topics ----------

class TopicCreate(BaseModel):
    name: str
    description: Optional[str] = ""


class TopicUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class TopicOut(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    source_count: int = 0
    tags: List[str] = []

    class Config:
        from_attributes = True


# ---------- Sources ----------

class SourceOut(BaseModel):
    id: str
    topic_id: str
    topic_name: Optional[str] = None
    title: str
    source_type: str
    date: date
    content: str
    description: str
    file_name: Optional[str] = None
    created_at: datetime
    tags: List[TagOut] = []

    class Config:
        from_attributes = True


class SourceUpdate(BaseModel):
    title: Optional[str] = None
    source_type: Optional[str] = None
    date: Optional[date] = None
    content: Optional[str] = None
    description: Optional[str] = None


# ---------- AI analysis ----------

class AnalyzeResult(BaseModel):
    suggested_tags: List[TagOut] = []


# ---------- Ask AI ----------

class AskResponse(BaseModel):
    answer: str
    used_sources: List[dict] = []
    chat_id: str
    chat_title: str


class ChatSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime
    message_count: int = 0


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    used_sources: List[dict] = []
    attachment_name: Optional[str] = None
    created_at: datetime


class ChatDetail(BaseModel):
    id: str
    topic_id: str
    title: str
    messages: List[ChatMessageOut] = []


class ChatRename(BaseModel):
    title: str
