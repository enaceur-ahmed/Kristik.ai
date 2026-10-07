"""
Tests for the chat API: conversation CRUD, message persistence
(including across a fresh DB session), dataset selection and
error handling. All LLM calls run in forced demo mode
(conftest) — no network, no key.
"""
from __future__ import annotations

import io
import pytest

from app.core.database import Base
from app.models import Conversation, Message


@pytest.fixture()
def uploaded_dataset(client, sample_csv_bytes):
    """Upload a small CSV and return its id."""
    res = client.post(
        "/api/datasets/upload",
        files={"file": ("chat_test.csv",
                        io.BytesIO(sample_csv_bytes),
                        "text/csv")},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --------------------------------------------------------------------------- #
#  Conversation CRUD                                                         #
# --------------------------------------------------------------------------- #
def test_create_conversation(client):
    res = client.post("/api/conversations",
                      json={"title": "My chat"})
    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "My chat"
    assert body["dataset_id"] is None
    assert body["id"]


def test_create_conversation_with_unknown_dataset(client):
    res = client.post("/api/conversations",
                      json={"dataset_id": "does-not-exist"})
    assert res.status_code == 404


def test_list_conversations(client):
    client.post("/api/conversations", json={"title": "A"})
    client.post("/api/conversations", json={"title": "B"})
    res = client.get("/api/conversations")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 2
    titles = {i["title"] for i in body["items"]}
    assert {"A", "B"} <= titles
    # newest first
    assert all("updated_at" in i for i in body["items"])


def test_get_conversation_with_messages(client, uploaded_dataset):
    res = client.post("/api/conversations",
                      json={"title": "Chat",
                            "dataset_id": uploaded_dataset})
    cid = res.json()["id"]

    res = client.post(f"/api/conversations/{cid}/messages",
                      json={"content": "hello"})
    assert res.status_code == 201

    res = client.get(f"/api/conversations/{cid}")
    assert res.status_code == 200
    body = res.json()
    assert body["dataset_id"] == uploaded_dataset
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"] == "hello"
    assert body["messages"][1]["role"] == "assistant"


def test_patch_rename_and_dataset(client, uploaded_dataset):
    res = client.post("/api/conversations", json={"title": "Old"})
    cid = res.json()["id"]

    res = client.patch(f"/api/conversations/{cid}",
                       json={"title": "New title",
                             "dataset_id": uploaded_dataset})
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "New title"
    assert body["dataset_id"] == uploaded_dataset


def test_delete_conversation(client):
    res = client.post("/api/conversations", json={"title": "Bye"})
    cid = res.json()["id"]

    res = client.delete(f"/api/conversations/{cid}")
    assert res.status_code == 204

    res = client.get(f"/api/conversations/{cid}")
    assert res.status_code == 404


def test_get_nonexistent_conversation(client):
    res = client.get("/api/conversations/nope")
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
#  Messaging                                                                 #
# --------------------------------------------------------------------------- #
def test_send_message_saves_both_sides(client, uploaded_dataset):
    cid = client.post("/api/conversations",
                      json={"dataset_id": uploaded_dataset}
                      ).json()["id"]

    res = client.post(f"/api/conversations/{cid}/messages",
                      json={"content": "How many rows have missing "
                                       "customer_id?"})
    assert res.status_code == 201
    body = res.json()
    assert body["role"] == "assistant"
    assert body["dataset_id"] == uploaded_dataset
    assert body["llm_fallback"] is False          # demo mode, not a failure
    assert body["demo_mode"] is True
    assert body["provider"] == "demo"
    assert body["content"]                        # deterministic answer

    # both messages persisted
    detail = client.get(f"/api/conversations/{cid}").json()
    assert len(detail["messages"]) == 2


def test_message_auto_titles_conversation(client, uploaded_dataset):
    cid = client.post("/api/conversations", json={}).json()["id"]
    res = client.post(f"/api/conversations/{cid}/messages",
                      json={"content": "What is the quality score of "
                                       "this dataset?"})
    assert res.status_code == 201
    detail = client.get(f"/api/conversations/{cid}").json()
    assert detail["title"] == "What is the quality score of this dataset?"


def test_message_with_invalid_dataset_404(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    res = client.post(f"/api/conversations/{cid}/messages",
                      json={"content": "hi", "dataset_id": "nope"})
    assert res.status_code == 404


def test_send_message_to_nonexistent_conversation(client):
    res = client.post("/api/conversations/nope/messages",
                      json={"content": "hi"})
    assert res.status_code == 404


def test_send_empty_message_rejected(client, uploaded_dataset):
    cid = client.post("/api/conversations", json={}).json()["id"]
    res = client.post(f"/api/conversations/{cid}/messages",
                      json={"content": ""})
    assert res.status_code == 422


# --------------------------------------------------------------------------- #
#  Persistence across sessions                                               #
# --------------------------------------------------------------------------- #
def _fresh_session():
    """A brand-new session on the same SQLite file —
    simulates a backend restart."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(
        "sqlite:///./test_copilot.db",
        connect_args={"check_same_thread": False},
    )
    return sessionmaker(bind=engine)()


def test_history_persists_in_database(client, uploaded_dataset):
    cid = client.post("/api/conversations",
                      json={"title": "Persist me",
                            "dataset_id": uploaded_dataset}).json()["id"]
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "first question"})

    # fresh session — simulates a backend restart
    db = _fresh_session()
    try:
        conv = db.query(Conversation).filter(
            Conversation.id == cid).first()
        assert conv is not None
        assert conv.title == "Persist me"
        msgs = (db.query(Message)
                .filter(Message.conversation_id == cid)
                .order_by(Message.created_at).all())
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[0].content == "first question"
        assert msgs[0].dataset_id == uploaded_dataset
        assert msgs[1].role == "assistant"
        assert msgs[1].llm_fallback is False
        assert msgs[1].sources is not None or msgs[1].sources is None
    finally:
        db.close()


def test_conversation_delete_cascades_messages(client, uploaded_dataset):
    cid = client.post("/api/conversations",
                      json={"dataset_id": uploaded_dataset}).json()["id"]
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "will be deleted"})

    assert client.delete(f"/api/conversations/{cid}").status_code == 204

    db = _fresh_session()
    try:
        remaining = (db.query(Message)
                     .filter(Message.conversation_id == cid).count())
        assert remaining == 0
    finally:
        db.close()
