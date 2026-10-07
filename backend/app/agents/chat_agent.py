"""
Chat agent — answers questions about a selected dataset using RAG
(retrieved chunks + an optional safe query plan executed with
pandas). Falls back to a deterministic answer built from the
retrieved chunks in demo mode or when the LLM call fails.

Design rule: the LLM never invents statistics — every number in
the prompt comes from pandas/NumPy or the stored DB artefacts.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models import Dataset
from app.agents.llm_provider import LLMProvider, get_llm_provider
from app.services.rag import (
    retrieve, extract_plan_heuristic, validate_plan, execute_plan,
    MAX_CHUNK_CHARS,
)

logger = get_logger(__name__)

CHAT_SYSTEM_PROMPT = """\
You are a data engineering copilot. You answer questions about the \
provided dataset context.

Rules:
- Answer ONLY from the provided context (retrieved chunks and the \
computed result). Cite the chunk ids you used, e.g. [schema] or \
[rows 120-130].
- If the answer is not in the context, say "I don't know — this is \
not in the data".
- Never invent statistics. Use the numbers in the context exactly.
- If a computed result is provided, use it as the authoritative \
answer and do not recompute or estimate.
- Answer in the language the user writes (French, English or \
Tunisian Arabic).
- Be concise. Use markdown tables when they help (columns, groups, \
comparisons)."""

PLAN_SYSTEM_PROMPT = """\
You translate data questions into a small JSON query plan that will \
be executed with pandas. Answer with ONLY the JSON object, no prose.

Allowed operations: count, sum, mean, min, max, groupby_count, \
groupby_mean, value_counts, filter_count.
- "column" must be a column name from the schema.
- "group_by" (optional) is a column name.
- "filter" (optional) is {"column": ..., "operator": one of isna, \
notna, equals, not_equals, gt, lt, gte, lte, "value": ...}.

If the question does NOT require computing over the data (it is \
descriptive, or already answerable from the context), return \
{"plan": null}. Otherwise return {"plan": { ... }}.

Schema:
{schema}"""

PLAN_USER_PROMPT = """\
Question: {question}

Return the JSON plan (or {{"plan": null}})."""

CHAT_USER_PROMPT = """\
Dataset context (retrieved chunks — cite them by id):
{context}

{computed_section}\
Conversation history (most recent last):
{history}

User question: {question}

Answer now, following the system rules. Cite chunk ids."""

HISTORY_LIMIT = 10   # last N messages injected into the prompt
MAX_PROMPT_CHARS = 24000


def _is_demo_mode() -> bool:
    return (settings.LLM_PROVIDER.lower().strip() == "demo"
            or not settings.LLM_API_KEY)


def _truncate(text: str, limit: int = MAX_CHUNK_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "\n…"


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(none)"
    lines = []
    for m in history[-HISTORY_LIMIT:]:
        role = "User" if m.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {m.get('content', '')[:500]}")
    return "\n".join(lines)


def _format_computed(computed: Optional[dict[str, Any]]) -> str:
    if not computed:
        return ""
    return ("Computed result (authoritative — produced by executing \
a validated query plan with pandas; use it verbatim):\n"
            + json.dumps(computed, ensure_ascii=False, indent=2) + "\n\n")


# --------------------------------------------------------------------------- #
#  Deterministic fallback answer                                            #
# --------------------------------------------------------------------------- #
def _deterministic_answer(question: str,
                          chunks: list[dict[str, Any]],
                          computed: Optional[dict[str, Any]],
                          dataset: Optional[Dataset]) -> str:
    """
    Build an answer from the retrieved chunks and the computed
    result only — no LLM. Used in demo mode and on LLM failure.
    """
    parts: list[str] = []

    if computed:
        res = computed.get("result", {})
        op = computed.get("operation")
        col = computed.get("column")
        gb = computed.get("group_by")
        if op == "filter_count":
            parts.append(
                f"{res.get('matching_rows')} of {res.get('total_rows')} "
                f"rows ({res.get('percentage')}%) match the filter on "
                f"'{col}' (missing values).")
        elif op == "count":
            parts.append(f"The dataset has {res.get('row_count')} rows.")
        elif op == "sum" and gb:
            items = sorted((res.get("group_sums") or {}).items(),
                             key=lambda kv: _to_float(kv[1]),
                             reverse=True)
            top = items[0] if items else None
            parts.append(
                "Total '" + str(col) + "' by '" + str(gb) + "' "
                "(computed with pandas): "
                + ", ".join(f"{k}: {v}" for k, v in items[:10]))
            if top:
                parts.append(f"Highest: {top[0]} with {top[1]}.")
        elif op == "sum":
            parts.append(f"Total '{col}': {res.get('sum')} "
                         "(computed with pandas).")
        elif op == "mean":
            parts.append(f"Mean of '{col}': {res.get('mean')} "
                         "(computed with pandas).")
        elif op in ("min", "max"):
            key = "min" if op == "min" else "max"
            parts.append(f"{op.title()} of '{col}': {res.get(key)} "
                         "(computed with pandas).")
        elif op == "value_counts":
            vc = res.get("value_counts") or {}
            parts.append(f"Value counts of '{col}': "
                         + ", ".join(f"{k}={v}"
                                       for k, v in list(vc.items())[:10]))
        elif op in ("groupby_count", "groupby_mean"):
            key = "group_counts" if op == "groupby_count" else "group_means"
            items = list((res.get(key) or {}).items())[:10]
            parts.append(f"{op} on '{gb}': "
                         + ", ".join(f"{k}: {v}" for k, v in items))

    if not parts:
        # Answer from the retrieved chunks (grounded, quoted).
        if dataset is not None:
            parts.append(f"About dataset **{dataset.original_filename}** "
                         "(answer built from the retrieved context):")
        shown = 0
        for c in chunks:
            if shown >= 3:
                break
            text = c["text"]
            # keep the most informative lines
            lines = [ln for ln in text.splitlines()
                     if ln.strip()][:8]
            parts.append(f"[{c['label']}]\n" + "\n".join(lines))
            shown += 1
        parts.append("Sources: "
                     + ", ".join(f"[{c['label']}]" for c in chunks[:6]))

    if _is_demo_mode():
        parts.append("\n(Demo mode — deterministic answer, no LLM call.)")

    return "\n\n".join(parts)


def _to_float(v: Any) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- #
#  LLM plan step                                                            #
# --------------------------------------------------------------------------- #
def _ask_llm_for_plan(provider: LLMProvider, question: str,
                      schema_text: str) -> Optional[dict[str, Any]]:
    """Ask the LLM for a JSON query plan. None on any failure."""
    try:
        raw = provider.chat(
            PLAN_SYSTEM_PROMPT.format(schema=schema_text),
            PLAN_USER_PROMPT.format(question=question),
        )
    except Exception as exc:
        logger.error("Chat plan LLM call failed (%s: %s) — "
                     "continuing without a computed plan.",
                     type(exc).__name__, str(exc)[:120])
        return None
    return _parse_plan(raw)


def _parse_plan(raw: str) -> Optional[dict[str, Any]]:
    """Extract a JSON plan object from an LLM response."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text,
                      re.DOTALL)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    else:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            candidates.append(text[start:end + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("plan"),
                                                 (dict, type(None))):
            return obj["plan"]
    return None


# --------------------------------------------------------------------------- #
#  Main entry point                                                         #
# --------------------------------------------------------------------------- #
def answer_question(
    question: str,
    history: list[dict[str, str]],
    dataset: Optional[Dataset],
    db: Session,
    provider: Optional[LLMProvider] = None,
) -> dict[str, Any]:
    """
    Answer one question. Returns a dict with:
      content, sources, llm_fallback, llm_error, provider, model,
      demo_mode, computed (the executed plan, if any).
    """
    demo_mode = _is_demo_mode()
    if provider is None:
        provider = get_llm_provider()

    chunks: list[dict[str, Any]] = []
    df = None
    schema_text = ""

    if dataset is not None:
        from app.services.rag import get_dataframe
        chunks = retrieve(dataset, db, question)
        df = get_dataframe(dataset)
        schema_chunk = next((c for c in chunks
                               if c["type"] == "schema"), None)
        schema_text = schema_chunk["text"] if schema_chunk else ""

    sources = [{"type": c["type"], "label": c["label"], "id": c["id"]}
               for c in chunks]

    # ---- 1. query plan: heuristic first (free), then LLM ----
    plan = extract_plan_heuristic(question, df) if df is not None \
        else None
    if plan is None and not demo_mode and df is not None:
        plan = _ask_llm_for_plan(provider, question, schema_text)

    computed = None
    if plan is not None and df is not None:
        ok, err = validate_plan(plan, df)
        if ok:
            try:
                computed = execute_plan(plan, df)
                sources.append({"type": "computed",
                                "label": "computed result (pandas)",
                                "id": "computed"})
            except Exception as exc:
                logger.error("Query plan execution failed (%s: %s)",
                             type(exc).__name__, str(exc)[:120])
        else:
            logger.info("Chat query plan rejected: %s", err)

    # ---- 2. demo mode: deterministic answer, no LLM call ----
    if demo_mode:
        content = _deterministic_answer(question, chunks, computed,
                                          dataset)
        return {
            "content": content,
            "sources": sources,
            "llm_fallback": False,
            "llm_error": None,
            "provider": "demo",
            "model": None,
            "demo_mode": True,
            "computed": computed,
        }

    # ---- 3. general chat (no dataset) ----
    if dataset is None:
        context = ("No dataset is selected. This is a general "
                   "conversation about data engineering.")
        user_prompt = (
            f"{context}\n\nConversation history:\n"
            f"{_format_history(history)}\n\nUser question: {question}"
        )
        try:
            content = provider.chat(CHAT_SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            logger.error("Chat LLM call failed (%s: %s) — falling back "
                         "to a deterministic answer.",
                         type(exc).__name__, str(exc)[:120])
            content = ("I am the AI Data Engineering Copilot. I can "
                       "answer questions about data engineering — "
                       "profiling, data quality, cleaning pipelines, "
                       "transformations and validation. Select a "
                       "dataset in the Discussion page and I will "
                       "answer questions grounded in its actual data.")
            return {
                "content": content,
                "sources": [],
                "llm_fallback": True,
                "llm_error": f"{type(exc).__name__}: {str(exc)[:200]}",
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL or None,
                "demo_mode": False,
                "computed": None,
            }
        return {
            "content": content,
            "sources": [],
            "llm_fallback": False,
            "llm_error": None,
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL or None,
            "demo_mode": False,
            "computed": None,
        }

    # ---- 4. dataset-grounded answer via LLM ----
    context = "\n\n---\n\n".join(
        f"[{c['label']} | id: {c['id']}]\n{_truncate(c['text'])}"
        for c in chunks)
    user_prompt = CHAT_USER_PROMPT.format(
        context=context,
        computed_section=_format_computed(computed),
        history=_format_history(history),
        question=question,
    )
    if len(user_prompt) > MAX_PROMPT_CHARS:
        user_prompt = user_prompt[:MAX_PROMPT_CHARS]

    try:
        content = provider.chat(CHAT_SYSTEM_PROMPT, user_prompt)
        return {
            "content": content,
            "sources": sources,
            "llm_fallback": False,
            "llm_error": None,
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL or None,
            "demo_mode": False,
            "computed": computed,
        }
    except Exception as exc:
        logger.error("Chat LLM call failed (%s: %s) — falling back "
                     "to a deterministic answer from retrieved chunks.",
                     type(exc).__name__, str(exc)[:120])
        content = _deterministic_answer(question, chunks, computed,
                                          dataset)
        return {
            "content": content,
            "sources": sources,
            "llm_fallback": True,
            "llm_error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL or None,
            "demo_mode": False,
            "computed": computed,
        }
