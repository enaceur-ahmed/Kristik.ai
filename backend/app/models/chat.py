"""
ORM models for the Discussion (chat) feature: conversations and messages.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, JSON, Boolean
)
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False, default="New chat")
    dataset_id = Column(
        String,
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    messages = relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan", order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(
        String,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String, nullable=False)          # user | assistant
    content = Column(Text, nullable=False)
    dataset_id = Column(
        String,
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    sources = Column(JSON, nullable=True)          # list of {type, label, id}
    llm_fallback = Column(Boolean, default=False)
    llm_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    conversation = relationship("Conversation", back_populates="messages")
