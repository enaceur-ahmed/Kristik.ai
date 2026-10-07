"""
Tests for the chat agent: deterministic demo answers,
query-plan execution, and LLM failure fallback behaviour.
All LLM calls are mocked — no network, no key.
"""
from __future__ import annotations

import os
import pandas as pd
import pytest

import app.core.config as cfg
from app.agents.chat_agent import answer_question
from app.agents.llm_provider import LLMProviderError
from app.services.rag import _CACHE


class _FakeDataset:
    def __init__(self, df, name="test.csv"):
        self.id = "chat-test-ds"
        self.original_filename = name
        self.file_path = ""
        self.file_type = "csv"
        self.updated_at = "x"
        self._df = df


class _FakeDB:
    """Minimal stand-in for a SQLAlchemy session: no stored
    artefacts, so chunking only produces schema/stats/rows."""

    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

        def order_by(self, *a, **k):
            return self

        def all(self):
            return []

        def limit(self, *a, **k):
            return self

    def query(self, *a, **k):
        return self._Q()


class _StubProvider:
    """Deterministic stub provider — records prompts, returns
    canned answers or raises."""

    def __init__(self, answer="stub answer",
                 raise_exc: Exception | None = None):
        self.answer = answer
        self.raise_exc = raise_exc
        self.calls: list[tuple[str, str]] = []

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.answer


@pytest.fixture(scope="module")
def chat_df() -> pd.DataFrame:
    return pd.DataFrame({
        "id": range(1, 31),
        "country": ["France"] * 12 + ["Germany"] * 10
                   + ["Spain"] * 8,
        "revenue": [100.0 + i for i in range(28)] + [None, None],
    })


@pytest.fixture()
def chat_dataset(chat_df):
    _CACHE.clear()
    ds = _FakeDataset(chat_df)
    from app.services.rag import get_dataframe
    _CACHE[ds.id] = {"df": chat_df, "updated_at": "x"}
    yield ds
    _CACHE.clear()


# --------------------------------------------------------------------------- #
#  Demo mode (conftest forces LLM_PROVIDER=demo, empty key)                #
# --------------------------------------------------------------------------- #
def test_demo_mode_answer_is_deterministic(chat_dataset, chat_df):
    assert cfg.settings.LLM_PROVIDER == "demo"
    result = answer_question(
        "How many rows have missing revenue?",
        history=[], dataset=chat_dataset, db=_FakeDB(),
        provider=_StubProvider())          # stub must NOT be called
    assert result["demo_mode"] is True
    assert result["llm_fallback"] is False
    assert result["llm_error"] is None
    # the computed pandas result is in the answer
    assert "2 of 30" in result["content"]
    assert "missing" in result["content"].lower()


def test_demo_mode_computes_groupby_sum(chat_dataset):
    result = answer_question(
        "Which country has the highest total revenue?",
        history=[], dataset=chat_dataset, db=_FakeDB(),
        provider=_StubProvider())
    assert result["demo_mode"] is True
    assert result["llm_fallback"] is False
    content = result["content"]
    # France has 12 rows (revenue 100..111), Germany 10 (112..121),
    # Spain 8 (122..127 + 2 missing) → France total is highest
    assert "France" in content
    assert "computed with pandas" in content


def test_demo_mode_no_dataset_general_chat():
    result = answer_question(
        "What is data profiling?", history=[], dataset=None,
        db=_FakeDB(), provider=_StubProvider())
    assert result["demo_mode"] is True
    assert result["llm_fallback"] is False
    assert result["content"]               # deterministic generic answer


# --------------------------------------------------------------------------- #
#  Real-LLM path (mocked provider)                                         #
# --------------------------------------------------------------------------- #
def test_llm_success_uses_provider_answer(chat_dataset, monkeypatch):
    monkeypatch.setattr(cfg.settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(cfg.settings, "LLM_API_KEY", "test-key-not-real")
    try:
        stub = _StubProvider(answer="The revenue column has 2 missing values.")
        result = answer_question(
            "How many rows have missing revenue?",
            history=[], dataset=chat_dataset, db=_FakeDB(),
            provider=stub)
        assert result["llm_fallback"] is False
        assert result["llm_error"] is None
        assert result["demo_mode"] is False
        assert result["content"] == stub.answer
        assert len(stub.calls) >= 1
        # heuristic plan matched → no separate plan call needed,
        # and the computed result is injected into the prompt
        assert any("Computed result" in prompt
                   for _, prompt in stub.calls)
        assert any("2" in prompt for _, prompt in stub.calls)
    finally:
        monkeypatch.setattr(cfg.settings, "LLM_PROVIDER", "demo")
        monkeypatch.setattr(cfg.settings, "LLM_API_KEY", "")


def test_llm_failure_falls_back_with_flags(chat_dataset, monkeypatch):
    monkeypatch.setattr(cfg.settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(cfg.settings, "LLM_API_KEY", "test-key-not-real")
    try:
        stub = _StubProvider(
            raise_exc=LLMProviderError("RateLimitError: 429"))
        result = answer_question(
            "Summarize the quality issues",
            history=[], dataset=chat_dataset, db=_FakeDB(),
            provider=stub)
        assert result["llm_fallback"] is True
        assert "RateLimitError" in (result["llm_error"] or "")
        assert result["demo_mode"] is False
        # fallback answer is deterministic and grounded in chunks
        assert result["content"]
        assert "revenue" in result["content"]      # from column stats chunk
        # sources are exposed
        assert result["sources"]
        assert any(s["type"] == "schema" for s in result["sources"])
    finally:
        monkeypatch.setattr(cfg.settings, "LLM_PROVIDER", "demo")
        monkeypatch.setattr(cfg.settings, "LLM_API_KEY", "")


def test_llm_general_chat_failure_falls_back(monkeypatch):
    monkeypatch.setattr(cfg.settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(cfg.settings, "LLM_API_KEY", "test-key-not-real")
    try:
        stub = _StubProvider(raise_exc=LLMProviderError("TimeoutError"))
        result = answer_question(
            "What is ETL?", history=[], dataset=None,
            db=_FakeDB(), provider=stub)
        assert result["llm_fallback"] is True
        assert "TimeoutError" in (result["llm_error"] or "")
        assert "data engineering" in result["content"].lower()
    finally:
        monkeypatch.setattr(cfg.settings, "LLM_PROVIDER", "demo")
        monkeypatch.setattr(cfg.settings, "LLM_API_KEY", "")


def test_history_is_injected_into_prompt(chat_dataset, monkeypatch):
    monkeypatch.setattr(cfg.settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(cfg.settings, "LLM_API_KEY", "test-key-not-real")
    try:
        stub = _StubProvider(answer="ok")
        answer_question(
            "And the second question?",
            history=[
                {"role": "user", "content": "first question"},
                {"role": "assistant", "content": "first answer"},
            ],
            dataset=chat_dataset, db=_FakeDB(), provider=stub)
        assert any("first question" in prompt
                   for _, prompt in stub.calls)
        assert any("And the second question?" in prompt
                   for _, prompt in stub.calls)
    finally:
        monkeypatch.setattr(cfg.settings, "LLM_PROVIDER", "demo")
        monkeypatch.setattr(cfg.settings, "LLM_API_KEY", "")
