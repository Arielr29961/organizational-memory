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
    owner_id = Column(String, ForeignKey("people.id"), nullable=True)

    sources = relationship("Source", back_populates="topic", cascade="all, delete-orphan")
    chats = relationship("Chat", back_populates="topic", cascade="all, delete-orphan")


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
    participants = relationship("SourceParticipant", back_populates="source", cascade="all, delete-orphan")


class Person(Base):
    """Internal address book: one real e-mail address and the full name that belongs to it."""

    __tablename__ = "people"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, nullable=False, unique=True)  # stored lower-case
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)  # set when the person registers; people without one are only in the address book

    sources = relationship("SourceParticipant", back_populates="person", cascade="all, delete-orphan")


class SourceParticipant(Base):
    """A participant / recipient of a source (meeting attendee, e-mail sender or recipient)."""

    __tablename__ = "source_participants"
    __table_args__ = (UniqueConstraint("source_id", "person_id", name="uq_source_person"),)

    id = Column(String, primary_key=True, default=gen_id)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(String, ForeignKey("people.id", ondelete="CASCADE"), nullable=False)

    source = relationship("Source", back_populates="participants")
    person = relationship("Person", back_populates="sources")


class AuthSession(Base):
    """A login: only the hash of the token is stored."""

    __tablename__ = "auth_sessions"

    id = Column(String, primary_key=True, default=gen_id)
    token_hash = Column(String, nullable=False, unique=True)
    person_id = Column(String, ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    person = relationship("Person")


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


class Chat(Base):
    """A saved Ask-AI conversation about one topic."""

    __tablename__ = "chats"

    id = Column(String, primary_key=True, default=gen_id)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="chats")
    messages = relationship(
        "ChatMessage", back_populates="chat", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=gen_id)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    used_sources = Column(Text, default="[]")  # JSON list of cited sources (assistant messages only)
    attachment_name = Column(String, nullable=True)  # file the user attached to this message (user messages only)
    attachment_text = Column(Text, nullable=True)  # text extracted from it; the file itself is not stored
    created_at = Column(DateTime, default=datetime.utcnow)

    chat = relationship("Chat", back_populates="messages")
