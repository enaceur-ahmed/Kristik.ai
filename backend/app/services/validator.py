"""
Validator — Phase 9.

Compares before/after DataFrames and produces a structured validation report.
Pure Python/Pandas — no LLM involvement.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.profiler import profile_dataframe


def validate_transformation(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    pipeline_steps: list[dict],
) -> dict[str, Any]:
    """
    Compare before/after DataFrames and emit validation checks.

    Returns:
        {
          "before": summary_before,
          "after": summary_after,
          "checks": [ {name, status, detail}, ... ],
          "overall_status": "PASS" | "WARNING" | "FAILED",
        }
    """
    checks: list[dict] = []

    # ------------------------------------------------------------------ #
    #  Quick summaries (lightweight — not full profiling)                 #
    # ------------------------------------------------------------------ #
    def _quick_summary(df: pd.DataFrame) -> dict:
        return {
            "rows": len(df),
            "columns": len(df.columns),
            "missing_total": int(df.isna().sum().sum()),
            "duplicate_rows": int(df.duplicated().sum()),
            "column_names": list(df.columns),
        }

    before_summary = _quick_summary(df_before)
    after_summary = _quick_summary(df_after)

    # ------------------------------------------------------------------ #
    #  Check 1: Row count                                                 #
    # ------------------------------------------------------------------ #
    row_diff = after_summary["rows"] - before_summary["rows"]
    row_loss_pct = abs(row_diff) / before_summary["rows"] * 100 if before_summary["rows"] > 0 else 0
    if row_diff == 0:
        checks.append({"name": "Row count", "status": "PASS",
                        "detail": f"Rows unchanged: {before_summary['rows']}"})
    elif row_loss_pct <= 10:
        checks.append({"name": "Row count", "status": "WARNING",
                        "detail": f"Rows changed: {before_summary['rows']} → {after_summary['rows']} ({row_loss_pct:.1f}% change)"})
    else:
        checks.append({"name": "Row count", "status": "FAILED",
                        "detail": f"Significant row loss: {before_summary['rows']} → {after_summary['rows']} ({row_loss_pct:.1f}%)" })

    # ------------------------------------------------------------------ #
    #  Check 2: Column count                                              #
    # ------------------------------------------------------------------ #
    col_diff = after_summary["columns"] - before_summary["columns"]
    if col_diff == 0:
        checks.append({"name": "Column count", "status": "PASS",
                        "detail": f"Columns unchanged: {before_summary['columns']}"})
    else:
        removed = set(before_summary["column_names"]) - set(after_summary["column_names"])
        added = set(after_summary["column_names"]) - set(before_summary["column_names"])
        detail = f"Columns changed: {before_summary['columns']} → {after_summary['columns']}"
        if removed:
            detail += f" | Removed: {list(removed)}"
        if added:
            detail += f" | Added: {list(added)}"
        checks.append({"name": "Column count", "status": "WARNING", "detail": detail})

    # ------------------------------------------------------------------ #
    #  Check 3: Missing values                                            #
    # ------------------------------------------------------------------ #
    miss_before = before_summary["missing_total"]
    miss_after = after_summary["missing_total"]
    if miss_after < miss_before:
        checks.append({"name": "Missing values", "status": "PASS",
                        "detail": f"Missing values reduced: {miss_before} → {miss_after} ({miss_before - miss_after} fixed)"})
    elif miss_after == miss_before:
        checks.append({"name": "Missing values", "status": "PASS" if miss_after == 0 else "WARNING",
                        "detail": f"Missing values unchanged: {miss_after}"})
    else:
        checks.append({"name": "Missing values", "status": "FAILED",
                        "detail": f"Missing values increased: {miss_before} → {miss_after}"})

    # ------------------------------------------------------------------ #
    #  Check 4: Duplicates                                                #
    # ------------------------------------------------------------------ #
    dup_before = before_summary["duplicate_rows"]
    dup_after = after_summary["duplicate_rows"]
    if dup_after <= dup_before:
        checks.append({"name": "Duplicates", "status": "PASS",
                        "detail": f"Duplicates: {dup_before} → {dup_after}"})
    else:
        checks.append({"name": "Duplicates", "status": "FAILED",
                        "detail": f"Duplicates increased: {dup_before} → {dup_after}"})

    # ------------------------------------------------------------------ #
    #  Check 5: Data integrity (no new nulls in key numerical cols)      #
    # ------------------------------------------------------------------ #
    num_cols_before = df_before.select_dtypes(include="number").columns.tolist()
    new_null_cols = []
    for col in num_cols_before:
        if col in df_after.columns:
            n_before = int(df_before[col].isna().sum())
            n_after = int(df_after[col].isna().sum())
            if n_after > n_before:
                new_null_cols.append(f"{col} (+{n_after - n_before})")

    if not new_null_cols:
        checks.append({"name": "Data integrity", "status": "PASS",
                        "detail": "No unexpected new nulls introduced in numerical columns."})
    else:
        checks.append({"name": "Data integrity", "status": "WARNING",
                        "detail": f"New nulls introduced in: {new_null_cols}"})

    # ------------------------------------------------------------------ #
    #  Check 6: Schema changes                                            #
    # ------------------------------------------------------------------ #
    dtype_changes = []
    for col in before_summary["column_names"]:
        if col in df_after.columns:
            bt = str(df_before[col].dtype)
            at = str(df_after[col].dtype)
            if bt != at:
                dtype_changes.append(f"{col}: {bt}→{at}")

    if not dtype_changes:
        checks.append({"name": "Schema", "status": "PASS",
                        "detail": "No dtype changes."})
    else:
        checks.append({"name": "Schema", "status": "WARNING",
                        "detail": f"Dtype changes: {dtype_changes}"})

    # ------------------------------------------------------------------ #
    #  Overall status                                                      #
    # ------------------------------------------------------------------ #
    statuses = [c["status"] for c in checks]
    if "FAILED" in statuses:
        overall = "FAILED"
    elif "WARNING" in statuses:
        overall = "WARNING"
    else:
        overall = "PASS"

    return {
        "before": before_summary,
        "after": after_summary,
        "checks": checks,
        "overall_status": overall,
    }
