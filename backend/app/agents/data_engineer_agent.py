"""
DataEngineerAgent — Phase 7.

Input  : profile (from DataProfiler) + quality issues (from QualityEngine)
Output : structured recommendations

The LLM is used to INTERPRET pre-computed results and PROPOSE transformations.
It NEVER invents statistics — all numbers come from the profile.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.agents.llm_provider import LLMProvider, get_llm_provider, LLMProviderError
from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """
You are an expert Data Engineer AI assistant.

You will receive:
1. A dataset profile (rows, columns, missing values, duplicates, outliers, categories — all pre-computed by Python).
2. A list of data quality issues.

Your job is to:
- Interpret the profiling results.
- Propose concrete, safe data cleaning and transformation actions.
- Explain WHY each transformation is appropriate given the statistics.
- Estimate the expected impact.

Rules:
- Do NOT invent any numbers. All statistics are provided to you.
- Return ONLY a valid JSON array of recommendation objects.
- Each recommendation must follow this exact schema:
  {
    "issue": string,
    "column": string | null,
    "severity": "low" | "medium" | "high" | "critical",
    "action": string,
    "strategy": string | null,
    "reason": string,
    "expected_impact": string
  }
- Possible actions: fill_missing, clip_outliers, standardise_categories,
  parse_dates, drop_column, remove_duplicates, cast_numeric, drop_high_missing
- Possible strategies for fill_missing: median, mean, mode, ffill, bfill, drop_rows, unknown, zero
- Do not include any text outside the JSON array.
"""


def _build_user_prompt(profile: dict, issues: list[dict]) -> str:
    # Trim profile to avoid token overflow
    trimmed = {
        "rows": profile.get("rows"),
        "columns": profile.get("columns"),
        "duplicate_percentage": profile.get("duplicate_percentage"),
        "missing_values": profile.get("missing_values"),
        "outliers": profile.get("outliers"),
        "categorical_anomalies": {
            k: v[:3] for k, v in (profile.get("categorical_anomalies") or {}).items()
        },
        "date_columns": profile.get("date_columns"),
        "numerical_columns": profile.get("numerical_columns"),
        "categorical_columns": profile.get("categorical_columns"),
        "column_profiles": {
            col: {
                "dtype": cp.get("dtype"),
                "column_type": cp.get("column_type"),
                "null_percentage": cp.get("null_percentage"),
                "outlier_count": cp.get("outlier_count"),
                "skewness": cp.get("skewness"),
                "inconsistent_category_count": cp.get("inconsistent_category_count"),
                "likely_datetime": cp.get("likely_datetime"),
            }
            for col, cp in (profile.get("column_profiles") or {}).items()
        },
    }
    return json.dumps({
        "profile": trimmed,
        "quality_issues": issues,
    }, indent=2, default=str)


def _parse_json_array(raw: str) -> Optional[list[dict[str, Any]]]:
    """
    Parse a JSON array from LLM output.

    Tolerates markdown code fences (```json ... ```) and surrounding prose.
    Returns None when no valid array of objects can be extracted.
    """
    if not raw:
        return None
    text = raw.strip()

    candidates: list[Any] = []

    # 1. Direct parse
    try:
        candidates.append(json.loads(text))
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Strip code fences, retry each fenced segment
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

    # 3. Tolerate surrounding text: first '[' to last ']'
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        try:
            candidates.append(json.loads(text[start:end + 1]))
        except (json.JSONDecodeError, ValueError):
            pass

    for data in candidates:
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return data
    return None


def _demo_recommendations(profile: dict, issues: list[dict]) -> list[dict]:
    """
    Deterministic fallback used in Demo Mode.
    Reads the actual profile and issues — does not invent numbers.
    """
    recs: list[dict] = []

    # Deduplicate
    dup_pct = profile.get("duplicate_percentage", 0)
    if dup_pct > 0:
        recs.append({
            "issue": "duplicates",
            "column": None,
            "severity": "high" if dup_pct > 5 else "medium",
            "action": "remove_duplicates",
            "strategy": None,
            "reason": (
                f"The dataset contains {dup_pct}% duplicate rows. "
                "Removing them prevents double-counting and skewed statistics."
            ),
            "expected_impact": "Improved data uniqueness and analytical accuracy.",
        })

    # Missing values
    missing = profile.get("missing_values", {})
    col_profiles = profile.get("column_profiles", {})
    for col, info in missing.items():
        pct = info.get("percentage", 0)
        if pct <= 0:
            continue
        cp = col_profiles.get(col, {})
        col_type = cp.get("column_type", "categorical")
        skewness = cp.get("skewness")

        if col_type == "numerical":
            strategy = "median" if (skewness is not None and abs(skewness) > 1) else "mean"
            reason = (
                f"'{col}' is numerical with {pct}% missing values. "
                + (f"The distribution is skewed (skewness={skewness:.2f}), so median is preferred."
                   if skewness is not None and abs(skewness) > 1
                   else "The distribution is approximately normal, so mean imputation is appropriate.")
            )
        else:
            strategy = "mode" if pct < 30 else "unknown"
            reason = (
                f"'{col}' is categorical with {pct}% missing. "
                + ("Filling with the most frequent value preserves the distribution."
                   if strategy == "mode"
                   else "High missing rate; filling with 'Unknown' avoids data loss.")
            )

        recs.append({
            "issue": "missing_values",
            "column": col,
            "severity": "critical" if pct > 50 else ("high" if pct > 20 else "medium"),
            "action": "fill_missing",
            "strategy": strategy,
            "reason": reason,
            "expected_impact": f"Reduce missing values in '{col}' from {pct}% to 0%.",
        })

    # Outliers
    outliers = profile.get("outliers", {})
    for col, info in outliers.items():
        pct = info.get("percentage", 0)
        recs.append({
            "issue": "outliers",
            "column": col,
            "severity": "high" if pct > 10 else "medium",
            "action": "clip_outliers",
            "strategy": "iqr",
            "reason": (
                f"'{col}' has {pct}% outliers beyond IQR bounds "
                f"[{info.get('lower_bound')}, {info.get('upper_bound')}]. "
                "Clipping preserves the data while removing extreme values."
            ),
            "expected_impact": f"Reduce outliers in '{col}' from {pct}% to 0%.",
        })

    # Inconsistent categories
    cat_anomalies = profile.get("categorical_anomalies", {})
    for col in cat_anomalies:
        recs.append({
            "issue": "inconsistent_categories",
            "column": col,
            "severity": "medium",
            "action": "standardise_categories",
            "strategy": "title_case",
            "reason": (
                f"Column '{col}' contains mixed-case and inconsistent category names. "
                "Standardising to title case will unify variants."
            ),
            "expected_impact": f"Reduce unique category variants in '{col}'.",
        })

    # Date-like strings
    for col, cp in col_profiles.items():
        if cp.get("likely_datetime") and cp.get("column_type") == "categorical":
            recs.append({
                "issue": "invalid_dates",
                "column": col,
                "severity": "medium",
                "action": "parse_dates",
                "strategy": None,
                "reason": (
                    f"Column '{col}' contains date-like strings stored as text. "
                    "Parsing to datetime enables time-series operations."
                ),
                "expected_impact": f"Enable temporal analysis on '{col}'.",
            })

    return recs


def generate_recommendations(
    profile: dict[str, Any],
    issues: list[dict[str, Any]],
    provider: LLMProvider | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Generate AI recommendations.

    Returns (recommendations, meta) where meta contains:
      - llm_fallback: True when the real LLM failed and demo logic was used
      - llm_error:    short "TypeName: message" string (no secrets), else None
      - provider:     provider class name
      - model:        configured model id (None in demo mode)
    """
    if provider is None:
        provider = get_llm_provider()

    meta: dict[str, Any] = {
        "provider": type(provider).__name__,
        "model": None if provider.is_demo() else settings.LLM_MODEL,
        "llm_fallback": False,
        "llm_error": None,
    }

    if provider.is_demo():
        logger.info("Demo mode: generating deterministic recommendations.")
        return _demo_recommendations(profile, issues), meta

    # Real LLM call
    user_prompt = _build_user_prompt(profile, issues)
    try:
        raw = provider.chat(SYSTEM_PROMPT, user_prompt)
        recs = _parse_json_array(raw)
        if recs is None:
            raise ValueError("LLM did not return a valid JSON array of recommendations")
        logger.info("LLM returned %d recommendations.", len(recs))
        return recs, meta
    except Exception as exc:
        logger.error(
            "LLM call failed: %s: %s — falling back to deterministic recommendations.",
            type(exc).__name__, str(exc)[:120],
        )
        meta["llm_fallback"] = True
        meta["llm_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return _demo_recommendations(profile, issues), meta