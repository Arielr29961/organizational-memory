import uuid
from datetime import datetime, date as date_type

from sqlalchemy import Column, String, Text, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


def gen_id():
    return str(uuid.uuid4())


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    sources = relationship("Source", back_populates="topic", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True, default=gen_id)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # meeting_transcript, email, presentation, spreadsheet, document, meeting_summary, other
    date = Column(Date, default=date_type.today)
    content = Column(Text, default="")
    description = Column(Text, default="")
    file_name = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="sources")
    tags = relationship("SourceTag", back_populates="source", cascade="all, delete-orphan")
    insights = relationship("Insight", back_populates="source", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False, unique=True)

    sources = relationship("SourceTag", back_populates="tag", cascade="all, delete-orphan")


class SourceTag(Base):
    __tablename__ = "source_tags"
    __table_args__ = (UniqueConstraint("source_id", "tag_id", name="uq_source_tag"),)

    id = Column(String, primary_key=True, default=gen_id)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(String, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    origin = Column(String, default="user")  # 'user' or 'ai'

    source = relationship("Source", back_populates="tags")
    tag = relationship("Tag", back_populates="sources")


class Insight(Base):
    __tablename__ = "insights"

    id = Column(String, primary_key=True, default=gen_id)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    insight_type = Column(String, nullable=False)  # fact, decision, hypothesis, open_question, action_item
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="insights")


class Connection(Base):
    __tablename__ = "connections"

    id = Column(String, primary_key=True, default=gen_id)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    related_source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    shared_tags = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
