"""
DataQualityEngine — Deterministic quality scoring.

Score: 0–100. Weights are documented and reproducible.
The LLM is NEVER called from this module.

Scoring weights
---------------
Missing values          : 30 pts (deducted proportionally)
Duplicates              : 20 pts (deducted proportionally)
Outliers                : 15 pts (deducted proportionally)
Inconsistent categories : 15 pts (deducted proportionally)
Invalid / likely-datetime
  stored as object      : 10 pts
Data type anomalies     : 10 pts
"""
from __future__ import annotations

from typing import Any


# --------------------------------------------------------------------------- #
#  Issue severity helpers                                                      #
# --------------------------------------------------------------------------- #

def _severity(pct: float) -> str:
    if pct == 0:
        return "none"
    if pct < 5:
        return "low"
    if pct < 20:
        return "medium"
    if pct < 50:
        return "high"
    return "critical"


# --------------------------------------------------------------------------- #
#  Public API                                                                  #
# --------------------------------------------------------------------------- #

def calculate_quality_score(profile: dict[str, Any]) -> dict[str, Any]:
    """
    Compute quality score from a profile produced by profiler.profile_dataframe.

    Returns:
        {
          "score": float,          # 0–100
          "breakdown": { ... },    # per-dimension sub-scores
          "issues": [ ... ],       # list of issue dicts
        }
    """
    rows: int = profile.get("rows", 1) or 1
    cols: int = profile.get("columns", 1) or 1
    missing: dict = profile.get("missing_values", {})
    outliers: dict = profile.get("outliers", {})
    cat_anomalies: dict = profile.get("categorical_anomalies", {})
    col_profiles: dict = profile.get("column_profiles", {})
    dup_pct: float = profile.get("duplicate_percentage", 0.0)

    issues: list[dict] = []
    breakdown: dict[str, float] = {}

    # ------------------------------------------------------------------ #
    #  1. Missing values  (30 pts)                                         #
    # ------------------------------------------------------------------ #
    total_cells = rows * cols
    total_missing = sum(v["count"] for v in missing.values())
    missing_pct_overall = (total_missing / total_cells * 100) if total_cells > 0 else 0.0

    # Deduct proportionally, but cap at 30
    missing_deduction = min(30.0, missing_pct_overall * 30 / 100 * 3)
    missing_score = max(0.0, 30.0 - missing_deduction)
    breakdown["missing_values"] = round(missing_score, 2)

    for col, info in missing.items():
        if info["percentage"] > 0:
            issues.append({
                "type": "missing_values",
                "column": col,
                "severity": _severity(info["percentage"]),
                "value": info["percentage"],
                "description": f"{info['percentage']}% missing values in '{col}' ({info['count']} rows)",
            })

    # ------------------------------------------------------------------ #
    #  2. Duplicates  (20 pts)                                            #
    # ------------------------------------------------------------------ #
    dup_deduction = min(20.0, dup_pct * 20 / 100 * 5)
    dup_score = max(0.0, 20.0 - dup_deduction)
    breakdown["duplicates"] = round(dup_score, 2)

    if dup_pct > 0:
        issues.append({
            "type": "duplicates",
            "column": None,
            "severity": _severity(dup_pct),
            "value": dup_pct,
            "description": f"{dup_pct}% duplicate rows ({profile.get('duplicate_rows', 0)} rows)",
        })

    # ------------------------------------------------------------------ #
    #  3. Outliers  (15 pts)                                              #
    # ------------------------------------------------------------------ #
    outlier_affected_pcts = [v["percentage"] for v in outliers.values()]
    avg_outlier_pct = (sum(outlier_affected_pcts) / len(outlier_affected_pcts)) if outlier_affected_pcts else 0.0
    outlier_deduction = min(15.0, avg_outlier_pct * 15 / 100 * 3)
    outlier_score = max(0.0, 15.0 - outlier_deduction)
    breakdown["outliers"] = round(outlier_score, 2)

    for col, info in outliers.items():
        issues.append({
            "type": "outliers",
            "column": col,
            "severity": _severity(info["percentage"]),
            "value": info["percentage"],
            "description": (
                f"{info['percentage']}% outliers in '{col}' "
                f"(IQR bounds: [{info.get('lower_bound')}, {info.get('upper_bound')}])"
            ),
        })

    # ------------------------------------------------------------------ #
    #  4. Inconsistent categories  (15 pts)                               #
    # ------------------------------------------------------------------ #
    cat_col_count = len([
        c for c, cp in col_profiles.items()
        if cp.get("column_type") == "categorical"
    ])
    affected_cat_cols = len(cat_anomalies)
    cat_affected_pct = (affected_cat_cols / cat_col_count * 100) if cat_col_count > 0 else 0.0
    cat_deduction = min(15.0, cat_affected_pct * 15 / 100 * 2)
    cat_score = max(0.0, 15.0 - cat_deduction)
    breakdown["inconsistent_categories"] = round(cat_score, 2)

    for col, variants_list in cat_anomalies.items():
        issues.append({
            "type": "inconsistent_categories",
            "column": col,
            "severity": "medium",
            "value": len(variants_list),
            "description": f"{len(variants_list)} inconsistent category variants in '{col}'",
        })

    # ------------------------------------------------------------------ #
    #  5. Likely-datetime stored as string  (10 pts)                      #
    # ------------------------------------------------------------------ #
    likely_dt_cols = [
        col for col, cp in col_profiles.items()
        if cp.get("likely_datetime") is True and cp.get("column_type") == "categorical"
    ]
    dt_affected_pct = (len(likely_dt_cols) / cols * 100) if cols > 0 else 0.0
    dt_deduction = min(10.0, dt_affected_pct * 10 / 100 * 3)
    dt_score = max(0.0, 10.0 - dt_deduction)
    breakdown["invalid_dates"] = round(dt_score, 2)

    for col in likely_dt_cols:
        issues.append({
            "type": "invalid_dates",
            "column": col,
            "severity": "medium",
            "value": None,
            "description": f"Column '{col}' contains date-like strings stored as text",
        })

    # ------------------------------------------------------------------ #
    #  6. Data type anomalies  (10 pts)                                   #
    # ------------------------------------------------------------------ #
    # Columns with very high unique-count that look like IDs stored as object
    type_issues = []
    for col, cp in col_profiles.items():
        if (cp.get("column_type") == "categorical"
                and cp.get("unique_percentage", 0) > 90
                and not cp.get("likely_datetime")):
            type_issues.append(col)

    type_affected_pct = (len(type_issues) / cols * 100) if cols > 0 else 0.0
    type_deduction = min(10.0, type_affected_pct * 10 / 100 * 2)
    type_score = max(0.0, 10.0 - type_deduction)
    breakdown["type_anomalies"] = round(type_score, 2)

    # ------------------------------------------------------------------ #
    #  Total                                                               #
    # ------------------------------------------------------------------ #
    raw_score = sum(breakdown.values())
    final_score = round(min(100.0, max(0.0, raw_score)), 1)

    return {
        "score": final_score,
        "breakdown": breakdown,
        "issues": issues,
    }


def summarise_issues(issues: list[dict]) -> dict[str, int]:
    """Return counts per issue type."""
    summary: dict[str, int] = {}
    for issue in issues:
        t = issue["type"]
        summary[t] = summary.get(t, 0) + 1
    return summary
