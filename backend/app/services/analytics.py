"""
Analytics module — Phase 11.

Generates descriptive statistics, distributions, correlations,
categorical summaries and basic business insights.

All numbers come from Pandas/NumPy — no LLM involvement.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import numpy as np

from app.services.profiler import _safe_float


def generate_analytics(df: pd.DataFrame) -> dict[str, Any]:
    """Compute full analytics for a DataFrame."""
    result: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    #  Descriptive statistics                                             #
    # ------------------------------------------------------------------ #
    num_df = df.select_dtypes(include="number")
    if not num_df.empty:
        desc = num_df.describe().to_dict()
        # Convert numpy types to Python
        result["descriptive_stats"] = {
            col: {k: _safe_float(v) for k, v in stats.items()}
            for col, stats in desc.items()
        }
    else:
        result["descriptive_stats"] = {}

    # ------------------------------------------------------------------ #
    #  Distributions (histogram data per numerical column)               #
    # ------------------------------------------------------------------ #
    distributions: dict[str, Any] = {}
    for col in num_df.columns:
        series = num_df[col].dropna()
        if len(series) < 2:
            continue
        counts, bin_edges = np.histogram(series, bins=min(20, len(series.unique())))
        distributions[col] = {
            "counts": [int(c) for c in counts],
            "bin_edges": [_safe_float(e) for e in bin_edges],
        }
    result["distributions"] = distributions

    # ------------------------------------------------------------------ #
    #  Correlations                                                       #
    # ------------------------------------------------------------------ #
    if len(num_df.columns) >= 2:
        corr = num_df.corr()
        result["correlations"] = {
            col: {other: _safe_float(v) for other, v in row.items()}
            for col, row in corr.to_dict().items()
        }
        # Top 5 strongest correlations (excluding self)
        corr_pairs = []
        cols_list = list(corr.columns)
        for i, c1 in enumerate(cols_list):
            for c2 in cols_list[i + 1:]:
                val = _safe_float(corr.loc[c1, c2])
                if val is not None:
                    corr_pairs.append({"col1": c1, "col2": c2, "correlation": val})
        corr_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        result["top_correlations"] = corr_pairs[:10]
    else:
        result["correlations"] = {}
        result["top_correlations"] = []

    # ------------------------------------------------------------------ #
    #  Categorical summaries                                              #
    # ------------------------------------------------------------------ #
    cat_df = df.select_dtypes(include=["object", "string", "category"])
    cat_summaries: dict[str, Any] = {}
    for col in cat_df.columns:
        vc = df[col].value_counts(dropna=False).head(15)
        cat_summaries[col] = {
            "unique_count": int(df[col].nunique(dropna=False)),
            "top_values": [{"value": str(k), "count": int(v), "percentage": round(v / len(df) * 100, 2)}
                           for k, v in vc.items()],
        }
    result["categorical_summaries"] = cat_summaries

    # ------------------------------------------------------------------ #
    #  Time series (if datetime column exists)                           #
    # ------------------------------------------------------------------ #
    dt_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
    time_series: dict[str, Any] = {}
    for dc in dt_cols[:2]:  # max 2 date columns
        # Find first numerical column to aggregate
        if len(num_df.columns) > 0:
            agg_col = num_df.columns[0]
            ts = df.set_index(dc)[agg_col].resample("ME").sum()
            time_series[f"{dc}_{agg_col}_monthly"] = {
                "dates": [str(d.date()) for d in ts.index],
                "values": [_safe_float(v) for v in ts.values],
            }
    result["time_series"] = time_series

    # ------------------------------------------------------------------ #
    #  Basic business insights (rule-based, deterministic)               #
    # ------------------------------------------------------------------ #
    insights: list[str] = []

    total_rows = len(df)
    insights.append(f"Dataset contains {total_rows:,} records across {len(df.columns)} columns.")

    # Completeness
    completeness = (1 - df.isna().mean().mean()) * 100
    insights.append(f"Overall data completeness: {completeness:.1f}%.")

    # Numerical range insights
    for col in num_df.columns[:3]:
        series = num_df[col].dropna()
        if len(series) > 0:
            insights.append(
                f"'{col}' ranges from {_safe_float(series.min())} to {_safe_float(series.max())} "
                f"(mean: {_safe_float(series.mean()):.2f})."
            )

    # Dominant category
    for col in list(cat_df.columns)[:2]:
        vc = df[col].value_counts(dropna=True)
        if len(vc) > 0:
            top_val = vc.index[0]
            top_pct = round(vc.iloc[0] / total_rows * 100, 1)
            insights.append(f"Most common '{col}': '{top_val}' ({top_pct}% of records).")

    result["insights"] = insights

    return result
