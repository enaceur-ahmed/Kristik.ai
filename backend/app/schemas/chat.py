"""
Pydantic v2 schemas for the Discussion (chat) feature.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    dataset_id: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    dataset_id: Optional[str] = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    dataset_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class ConversationListItem(ConversationRead):
    message_count: int = 0
    last_message_at: Optional[datetime] = None


class ConversationList(BaseModel):
    items: list[ConversationListItem]
    total: int


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    dataset_id: Optional[str]
    sources: Optional[list[dict[str, Any]]] = None
    llm_fallback: bool
    llm_error: Optional[str] = None
    created_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead] = []


class MessageSend(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    dataset_id: Optional[str] = None


class MessageGeneration(MessageRead):
    """Assistant message returned by POST /api/conversations/{id}/messages."""
    provider: str
    model: Optional[str] = None
    demo_mode: bool
