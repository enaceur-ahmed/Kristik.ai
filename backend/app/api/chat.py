"""
API endpoints for the Discussion (chat) feature.

Prefix: /api/conversations
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging_config import get_logger
from app.models import Conversation, Message, Dataset
from app.schemas.chat import (
    ConversationCreate,
    ConversationUpdate,
    ConversationRead,
    ConversationListItem,
    ConversationList,
    ConversationDetail,
    MessageRead,
    MessageSend,
    MessageGeneration,
)
from app.agents.chat_agent import answer_question
from app.agents.llm_provider import get_llm_provider

logger = get_logger(__name__)

router = APIRouter(prefix="/api/conversations",
                   tags=["conversations"])


def _get_conversation_or_404(conversation_id: str,
                               db: Session) -> Conversation:
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id).first()
    if conv is None:
        raise HTTPException(status_code=404,
                            detail="Conversation not found")
    return conv


def _resolve_dataset(dataset_id: Optional[str],
                       db: Session) -> Optional[Dataset]:
    if dataset_id is None:
        return None
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if ds is None:
        raise HTTPException(status_code=404,
                            detail=f"Dataset '{dataset_id}' not found")
    return ds


# --------------------------------------------------------------------------- #
#  CRUD                                                                       #
# --------------------------------------------------------------------------- #
@router.get("", response_model=ConversationList)
def list_conversations(db: Session = Depends(get_db)):
    """List conversations (newest first) with message counts."""
    convs = (db.query(Conversation)
             .order_by(Conversation.updated_at.desc())
             .all())
    items: list[ConversationListItem] = []
    for c in convs:
        count = (db.query(func.count(Message.id))
                 .filter(Message.conversation_id == c.id)
                 .scalar() or 0)
        last = (db.query(func.max(Message.created_at))
                .filter(Message.conversation_id == c.id)
                .scalar())
        items.append(ConversationListItem(
            id=c.id,
            title=c.title,
            dataset_id=c.dataset_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=int(count),
            last_message_at=last,
        ))
    return ConversationList(items=items, total=len(items))


@router.post("", response_model=ConversationRead, status_code=201)
def create_conversation(body: ConversationCreate,
                          db: Session = Depends(get_db)):
    """Create a conversation (optionally with a title and dataset)."""
    if body.dataset_id is not None:
        _resolve_dataset(body.dataset_id, db)
    conv = Conversation(
        title=(body.title or "New chat")[:200],
        dataset_id=body.dataset_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str,
                       db: Session = Depends(get_db)):
    """Get a conversation with all its messages."""
    conv = _get_conversation_or_404(conversation_id, db)
    return conv


@router.patch("/{conversation_id}", response_model=ConversationRead)
def update_conversation(conversation_id: str,
                          body: ConversationUpdate,
                          db: Session = Depends(get_db)):
    """Rename a conversation and/or change its dataset."""
    conv = _get_conversation_or_404(conversation_id, db)
    if body.title is not None:
        conv.title = body.title[:200] or "New chat"
    if body.dataset_id is not None:
        _resolve_dataset(body.dataset_id, db)
    conv.dataset_id = body.dataset_id
    db.commit()
    db.refresh(conv)
    return conv


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str,
                          db: Session = Depends(get_db)):
    """Delete a conversation (messages cascade)."""
    conv = _get_conversation_or_404(conversation_id, db)
    db.delete(conv)
    db.commit()
    return None


# --------------------------------------------------------------------------- #
#  Messaging                                                                  #
# --------------------------------------------------------------------------- #
@router.post("/{conversation_id}/messages",
             response_model=MessageGeneration, status_code=201)
def send_message(conversation_id: str,
                   body: MessageSend,
                   db: Session = Depends(get_db)):
    """
    Send a user message. The user message is saved first, the
    assistant answer is generated (RAG + optional LLM) and saved
    after, so the history survives refreshes and restarts.
    """
    conv = _get_conversation_or_404(conversation_id, db)

    # The message's dataset: explicit body value wins, else the
    # conversation's current dataset.
    dataset_id = body.dataset_id if body.dataset_id is not None \
        else conv.dataset_id
    dataset = _resolve_dataset(dataset_id, db)

    # --- save the user message BEFORE the LLM call ---
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=body.content,
        dataset_id=dataset.id if dataset is not None else None,
        llm_fallback=False,
    )
    db.add(user_msg)

    # Auto-title from the first user message (no LLM call).
    if not conv.title or conv.title == "New chat":
        conv.title = body.content[:50]
    conv.dataset_id = dataset.id if dataset is not None else None
    db.commit()
    db.refresh(conv)

    # --- build history from persisted messages ---
    history = [
        {"role": m.role, "content": m.content}
        for m in (db.query(Message)
                  .filter(Message.conversation_id == conv.id)
                  .order_by(Message.created_at)
                  .limit(10)
                  .all())
    ]

    # --- generate the assistant answer ---
    try:
        provider = get_llm_provider()
        result = answer_question(
            question=body.content,
            history=history,
            dataset=dataset,
            db=db,
            provider=provider,
        )
    except Exception as exc:
        # Last-resort guard: never fail the request — save a
        # fallback assistant message instead.
        logger.error("Chat answer generation failed (%s: %s)",
                     type(exc).__name__, str(exc)[:120])
        result = {
            "content": "Sorry, answer generation failed. "
                       "The conversation is saved — try again.",
            "sources": [],
            "llm_fallback": True,
            "llm_error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "provider": "unknown",
            "model": None,
            "demo_mode": False,
        }

    # --- save the assistant message AFTER the LLM call ---
    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=result["content"],
        dataset_id=dataset.id if dataset is not None else None,
        sources=result.get("sources"),
        llm_fallback=bool(result.get("llm_fallback")),
        llm_error=result.get("llm_error"),
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return MessageGeneration(
        id=assistant_msg.id,
        conversation_id=assistant_msg.conversation_id,
        role=assistant_msg.role,
        content=assistant_msg.content,
        dataset_id=assistant_msg.dataset_id,
        sources=assistant_msg.sources,
        llm_fallback=assistant_msg.llm_fallback,
        llm_error=assistant_msg.llm_error,
        created_at=assistant_msg.created_at,
        provider=result.get("provider", "unknown"),
        model=result.get("model"),
        demo_mode=bool(result.get("demo_mode")),
    )
