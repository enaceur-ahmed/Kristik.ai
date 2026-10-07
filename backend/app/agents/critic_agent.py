"""
Critic Agent — Phase 12.

Reviews AI-generated recommendations for safety and appropriateness.
It does NOT calculate statistics — it reasons about the proposed actions.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.agents.llm_provider import LLMProvider, get_llm_provider, LLMProviderError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

CRITIC_SYSTEM_PROMPT = """
You are a senior Data Engineering reviewer.

You will receive an AI recommendation and the dataset profile that motivated it.

Your task is to review whether the recommendation is:
1. Supported by the provided profiling data.
2. Technically appropriate and safe.
3. Free of risk of data loss or quality degradation.

Return ONLY a valid JSON object with this schema:
{
  "status": "accepted" | "rejected" | "modified",
  "risk": "low" | "medium" | "high",
  "reason": string,
  "alternative": string | null
}
Do not include any text outside the JSON object.
"""


def _demo_critic_review(recommendation: dict, profile: dict) -> dict:
    """
    Deterministic critic review for demo mode.
    Applies conservative rules without LLM.
    """
    action = recommendation.get("action", "")
    column = recommendation.get("column")
    col_profiles = profile.get("column_profiles", {})

    risk = "low"
    status = "accepted"
    reason = "Recommendation is consistent with detected issues."
    alternative = None

    # High-missing-rate columns — warn about drop_rows
    if action == "fill_missing" and column:
        cp = col_profiles.get(column, {})
        pct = cp.get("null_percentage", 0)
        if recommendation.get("strategy") == "drop_rows" and pct > 30:
            status = "modified"
            risk = "high"
            reason = (
                f"Dropping rows for '{column}' ({pct}% missing) would result in significant data loss (>30%)."
            )
            alternative = "Consider filling with median or 'Unknown' instead of dropping rows."

    # Clip outliers on columns with extreme skew
    if action == "clip_outliers" and column:
        cp = col_profiles.get(column, {})
        skew = cp.get("skewness")
        if skew is not None and abs(skew) > 3:
            risk = "medium"
            reason = (
                f"'{column}' is highly skewed (skewness={skew:.2f}). "
                "Clipping may not be the best strategy; consider log transform."
            )
            alternative = "Apply log transformation before or instead of clipping."

    # Remove duplicates — always safe
    if action == "remove_duplicates":
        status = "accepted"
        risk = "low"
        reason = "Removing exact duplicates is always safe."

    return {
        "status": status,
        "risk": risk,
        "reason": reason,
        "alternative": alternative,
    }


def _parse_json_object(raw: str) -> Optional[dict[str, Any]]:
    """
    Parse a JSON object from LLM output.

    Tolerates markdown code fences (```json ... ```) and surrounding prose.
    Returns None when no valid object can be extracted.
    """
    if not raw:
        return None
    text = raw.strip()

    candidates: list[Any] = []

    try:
        candidates.append(json.loads(text))
    except (json.JSONDecodeError, ValueError):
        pass

    if "```" in text:
        for segment in text.split("```"):
            segment = segment.strip()
            if segment.lower().startswith("json"):
                segment = segment[4:].strip()
            if not segment:
                continue
            try:
                candidates.append(json.loads(segment))
            except (json.JSONDecodeError, ValueError):
                pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            candidates.append(json.loads(text[start:end + 1]))
        except (json.JSONDecodeError, ValueError):
            pass

    for data in candidates:
        if isinstance(data, dict):
            return data
    return None


def _valid_critic_review(obj: Any) -> bool:
    """Validate the critic review structure returned by the LLM."""
    return (
        isinstance(obj, dict)
        and obj.get("status") in ("accepted", "rejected", "modified")
        and obj.get("risk") in ("low", "medium", "high")
        and isinstance(obj.get("reason"), str)
    )


def review_recommendation(
    recommendation: dict[str, Any],
    profile: dict[str, Any],
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    """Review a single recommendation. Returns critic review dict."""
    if provider is None:
        provider = get_llm_provider()

    if provider.is_demo():
        return _demo_critic_review(recommendation, profile)

    user_prompt = json.dumps({
        "recommendation": recommendation,
        "profile_summary": {
            "rows": profile.get("rows"),
            "columns": profile.get("columns"),
            "column_profile": profile.get("column_profiles", {}).get(
                recommendation.get("column", ""), {}
            ),
        },
    }, indent=2, default=str)

    try:
        raw = provider.chat(CRITIC_SYSTEM_PROMPT, user_prompt)
        review = _parse_json_object(raw)
        if not _valid_critic_review(review):
            raise ValueError("Critic LLM did not return a valid review object")
        return review
    except Exception as exc:
        logger.error(
            "Critic LLM call failed (%s: %s) — using demo critic.",
            type(exc).__name__, str(exc)[:80],
        )
        fallback = _demo_critic_review(recommendation, profile)
        fallback["llm_fallback"] = True
        fallback["llm_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        return fallback


def review_all_recommendations(
    recommendations: list[dict[str, Any]],
    profile: dict[str, Any],
    provider: LLMProvider | None = None,
) -> list[dict[str, Any]]:
    """Review all recommendations and attach critic feedback."""
    if provider is None:
        provider = get_llm_provider()

    reviewed = []
    for rec in recommendations:
        review = review_recommendation(rec, profile, provider)
        reviewed.append({**rec, "critic_review": review})
    return reviewed
