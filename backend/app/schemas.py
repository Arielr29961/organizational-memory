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


# ---------- Insights ----------

class InsightOut(BaseModel):
    id: str
    source_id: str
    insight_type: str
    content: str
    source_title: Optional[str] = None
    source_date: Optional[date] = None

    class Config:
        from_attributes = True


class ConnectionOut(BaseModel):
    id: str
    source_id: str
    related_source_id: str
    description: str
    shared_tags: str
    source_title: Optional[str] = None
    related_title: Optional[str] = None
    related_topic_name: Optional[str] = None
    related_topic_id: Optional[str] = None


class AnalyzeResult(BaseModel):
    suggested_tags: List[TagOut] = []
    insights: List[InsightOut] = []
    connections: List[ConnectionOut] = []


# ---------- Ask AI ----------

class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    used_sources: List[dict] = []
