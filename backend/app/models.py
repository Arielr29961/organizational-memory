import uuid
from datetime import datetime, date as date_type

from sqlalchemy import Column, String, Text, Date, DateTime, ForeignKey, Integer, UniqueConstraint
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
    owner = relationship("Person", foreign_keys=[owner_id])
    members = relationship("TopicMember", back_populates="topic", cascade="all, delete-orphan")


class TopicMember(Base):
    """A person the topic is shared with (the owner is Topic.owner_id and is not listed here)."""

    __tablename__ = "topic_members"
    __table_args__ = (UniqueConstraint("topic_id", "person_id", name="uq_topic_member"),)

    id = Column(String, primary_key=True, default=gen_id)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(String, ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False, default="viewer")  # 'viewer' or 'editor'

    topic = relationship("Topic", back_populates="members")
    person = relationship("Person")


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
    edited_at = Column(DateTime, nullable=True)  # last time title/type/date/description/content was changed
    edited_by = Column(String, ForeignKey("people.id"), nullable=True)

    topic = relationship("Topic", back_populates="sources")
    editor = relationship("Person", foreign_keys=[edited_by])
    versions = relationship("SourceVersion", back_populates="source", cascade="all, delete-orphan", order_by="SourceVersion.replaced_at")
    attachments = relationship("SourceAttachment", back_populates="source", cascade="all, delete-orphan", order_by="SourceAttachment.created_at")
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


class SourceAttachment(Base):
    """A file that came attached to an imported e-mail; stored for download (its text, if readable, is in the source content)."""

    __tablename__ = "source_attachments"

    id = Column(String, primary_key=True, default=gen_id)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    size = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="attachments")


class SourceVersion(Base):
    """The text state of a source just before an edit replaced it (tags, participants and files are not versioned)."""

    __tablename__ = "source_versions"

    id = Column(String, primary_key=True, default=gen_id)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    replaced_at = Column(DateTime, default=datetime.utcnow)  # when the edit that replaced this version happened
    replaced_by = Column(String, ForeignKey("people.id"), nullable=True)  # who made that edit
    title = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    date = Column(Date, nullable=True)
    description = Column(Text, default="")
    content = Column(Text, default="")

    source = relationship("Source", back_populates="versions")
    editor = relationship("Person", foreign_keys=[replaced_by])


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


class IntakeItem(Base):
    """An imported file waiting for the user's approval; approving it creates a regular Source."""

    __tablename__ = "intake_items"

    id = Column(String, primary_key=True, default=gen_id)
    owner_id = Column(String, ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="processing")  # processing, pending, error, approved
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_hash = Column(String, nullable=False)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)  # proposed existing topic
    new_topic_name = Column(String, nullable=True)  # proposed new topic (created only when the item is approved)
    title = Column(String, default="")
    date = Column(Date, nullable=True)
    source_type = Column(String, default="document")
    description = Column(Text, default="")
    content = Column(Text, default="")
    tags = Column(Text, default="[]")  # JSON list of names
    participants = Column(Text, default="[]")  # JSON list of {"email", "name"}
    notes = Column(Text, default="[]")  # JSON list of things the AI could not resolve (e.g. people without an address)
    reason = Column(Text, default="")
    confidence = Column(String, default="low")  # high, medium, low
    error = Column(Text, nullable=True)
    source_id = Column(String, nullable=True)  # the source created on approval
    created_at = Column(DateTime, default=datetime.utcnow)

    attachments = relationship("IntakeAttachment", back_populates="item", cascade="all, delete-orphan")


class IntakeAttachment(Base):
    """An attachment of a proposed e-mail; it becomes a SourceAttachment when the proposal is approved."""

    __tablename__ = "intake_attachments"

    id = Column(String, primary_key=True, default=gen_id)
    item_id = Column(String, ForeignKey("intake_items.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    size = Column(Integer, default=0)

    item = relationship("IntakeItem", back_populates="attachments")


class Chat(Base):
    """A saved Ask-AI conversation about one topic."""

    __tablename__ = "chats"

    id = Column(String, primary_key=True, default=gen_id)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    created_by = Column(String, ForeignKey("people.id"), nullable=True)  # chats are personal to their author
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
    context_tag = Column(String, nullable=True)  # tag the user was focusing on when asking (user messages only)
    created_at = Column(DateTime, default=datetime.utcnow)

    chat = relationship("Chat", back_populates="messages")
