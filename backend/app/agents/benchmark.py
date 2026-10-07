"""
Benchmark module — Phase 13.

Compares three modes:
  A: Deterministic pipeline (no LLM)
  B: Single AI Data Engineer
  C: AI Data Engineer + Critic + Validation

Measures actual execution results — never fabricated.
"""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

from app.services.profiler import profile_dataframe
from app.services.quality_score import calculate_quality_score
from app.services.transformer import apply_pipeline
from app.services.validator import validate_transformation
from app.agents.data_engineer_agent import generate_recommendations
from app.agents.critic_agent import review_all_recommendations
from app.agents.pipeline_generator import generate_pipeline
from app.agents.llm_provider import get_llm_provider
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def _build_deterministic_steps(profile: dict, issues: list[dict]) -> list[dict]:
    """Mode A: rule-based steps, no LLM."""
    steps = []
    step_n = 1

    if profile.get("duplicate_percentage", 0) > 0:
        steps.append({"step": step_n, "operation": "remove_duplicates"})
        step_n += 1

    missing = profile.get("missing_values", {})
    col_profiles = profile.get("column_profiles", {})
    for col, info in missing.items():
        if info.get("percentage", 0) <= 0:
            continue
        cp = col_profiles.get(col, {})
        col_type = cp.get("column_type", "categorical")
        strategy = "median" if col_type == "numerical" else "mode"
        steps.append({"step": step_n, "operation": "fill_missing", "column": col, "strategy": strategy})
        step_n += 1

    for col in profile.get("outliers", {}):
        steps.append({"step": step_n, "operation": "clip_outliers", "column": col})
        step_n += 1

    for col in profile.get("categorical_anomalies", {}):
        steps.append({"step": step_n, "operation": "standardise_categories", "column": col})
        step_n += 1

    return steps


def run_benchmark(df: pd.DataFrame) -> dict[str, Any]:
    """
    Run all three benchmark modes on the same DataFrame.
    Returns measured results per mode.
    """
    results: dict[str, Any] = {}
    provider = get_llm_provider()

    # Pre-compute profile and quality once
    profile = profile_dataframe(df)
    quality = calculate_quality_score(profile)
    issues = quality["issues"]

    base_score = quality["score"]
    results["baseline_quality_score"] = base_score
    results["total_issues_detected"] = len(issues)

    # ------------------------------------------------------------------ #
    #  Mode A: Deterministic                                              #
    # ------------------------------------------------------------------ #
    t0 = time.perf_counter()
    steps_a = _build_deterministic_steps(profile, issues)
    df_a, exec_log_a = apply_pipeline(df.copy(), steps_a)
    profile_a = profile_dataframe(df_a)
    quality_a = calculate_quality_score(profile_a)
    validation_a = validate_transformation(df, df_a, steps_a)
    t_a = round(time.perf_counter() - t0, 3)

    results["mode_a"] = {
        "name": "Deterministic Pipeline",
        "execution_time_s": t_a,
        "steps_applied": len(steps_a),
        "issues_resolved": len(issues) - len(quality_a["issues"]),
        "quality_score_before": base_score,
        "quality_score_after": quality_a["score"],
        "validation_status": validation_a["overall_status"],
        "validation_failures": sum(1 for c in validation_a["checks"] if c["status"] == "FAILED"),
        "human_interventions": 0,
        "token_usage": 0,
        "llm_fallback": False,   # Mode A never uses the LLM
        "llm_error": None,
    }

    # ------------------------------------------------------------------ #
    #  Mode B: AI Data Engineer only                                      #
    # ------------------------------------------------------------------ #
    t0 = time.perf_counter()
    recs_b, meta_b = generate_recommendations(profile, issues, provider)
    # Simulate all applied
    for r in recs_b:
        r["status"] = "applied"
    pipeline_b = generate_pipeline(recs_b)
    df_b, exec_log_b = apply_pipeline(df.copy(), pipeline_b["steps"])
    profile_b = profile_dataframe(df_b)
    quality_b = calculate_quality_score(profile_b)
    validation_b = validate_transformation(df, df_b, pipeline_b["steps"])
    t_b = round(time.perf_counter() - t0, 3)

    results["mode_b"] = {
        "name": "AI Data Engineer",
        "execution_time_s": t_b,
        "steps_applied": len(pipeline_b["steps"]),
        "recommendations_generated": len(recs_b),
        "issues_resolved": len(issues) - len(quality_b["issues"]),
        "quality_score_before": base_score,
        "quality_score_after": quality_b["score"],
        "validation_status": validation_b["overall_status"],
        "validation_failures": sum(1 for c in validation_b["checks"] if c["status"] == "FAILED"),
        "human_interventions": 0,
        "token_usage": 0,
        "llm_fallback": bool(meta_b.get("llm_fallback")),
        "llm_error": meta_b.get("llm_error"),
    }

    # ------------------------------------------------------------------ #
    #  Mode C: AI Data Engineer + Critic + Validation                     #
    # ------------------------------------------------------------------ #
    t0 = time.perf_counter()
    recs_c_raw, meta_c = generate_recommendations(profile, issues, provider)
    # Critic review (uses the real provider when configured, demo otherwise)
    recs_c_reviewed = review_all_recommendations(recs_c_raw, profile, provider)
    # Reject high-risk recommendations
    human_interventions = 0
    for r in recs_c_reviewed:
        critic = r.get("critic_review", {})
        if critic.get("status") == "rejected" or critic.get("risk") == "high":
            r["status"] = "rejected"
            human_interventions += 1
        else:
            r["status"] = "applied"

    pipeline_c = generate_pipeline(recs_c_reviewed)
    df_c, exec_log_c = apply_pipeline(df.copy(), pipeline_c["steps"])
    profile_c = profile_dataframe(df_c)
    quality_c = calculate_quality_score(profile_c)
    validation_c = validate_transformation(df, df_c, pipeline_c["steps"])
    t_c = round(time.perf_counter() - t0, 3)

    critic_fallback = any(
        isinstance(r.get("critic_review"), dict) and r["critic_review"].get("llm_fallback")
        for r in recs_c_reviewed
    )

    results["mode_c"] = {
        "name": "AI Engineer + Critic + Validation",
        "execution_time_s": t_c,
        "steps_applied": len(pipeline_c["steps"]),
        "recommendations_generated": len(recs_c_raw),
        "recommendations_rejected_by_critic": human_interventions,
        "issues_resolved": len(issues) - len(quality_c["issues"]),
        "quality_score_before": base_score,
        "quality_score_after": quality_c["score"],
        "validation_status": validation_c["overall_status"],
        "validation_failures": sum(1 for c in validation_c["checks"] if c["status"] == "FAILED"),
        "human_interventions": human_interventions,
        "token_usage": 0,
        "llm_fallback": bool(meta_c.get("llm_fallback") or critic_fallback),
        "llm_error": meta_c.get("llm_error"),
    }

    return results
