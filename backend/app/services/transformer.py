"""
Cleaning / Transformation Engine — Phase 6.

Applies structured transformation steps to a DataFrame.
No arbitrary code execution. Each operation is a known,
validated function mapped by name.

Steps are defined as dicts produced by PipelineGenerator.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging_config import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Registry of safe operations                                                 #
# --------------------------------------------------------------------------- #

def op_remove_duplicates(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    before = len(df)
    df = df.drop_duplicates()
    after = len(df)
    return df, f"Removed {before - after} duplicate rows."


def op_fill_missing(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    col: str = step["column"]
    strategy: str = step.get("strategy", "median")
    if col not in df.columns:
        return df, f"Column '{col}' not found — skipped."

    series = df[col]
    null_before = int(series.isna().sum())

    if strategy == "median":
        fill_val = series.median()
    elif strategy == "mean":
        fill_val = series.mean()
    elif strategy == "mode":
        mode_vals = series.mode()
        fill_val = mode_vals.iloc[0] if len(mode_vals) else np.nan
    elif strategy == "zero":
        fill_val = 0
    elif strategy == "ffill":
        df[col] = series.ffill()
        null_after = int(df[col].isna().sum())
        return df, f"Forward-filled '{col}': {null_before} → {null_after} nulls."
    elif strategy == "bfill":
        df[col] = series.bfill()
        null_after = int(df[col].isna().sum())
        return df, f"Backward-filled '{col}': {null_before} → {null_after} nulls."
    elif strategy == "drop_rows":
        df = df.dropna(subset=[col])
        null_after = int(df[col].isna().sum())
        return df, f"Dropped rows with null '{col}': {null_before} → {null_after} nulls."
    elif strategy == "unknown":
        fill_val = "Unknown"
    else:
        fill_val = strategy  # literal value

    df[col] = series.fillna(fill_val)
    null_after = int(df[col].isna().sum())
    return df, f"Filled '{col}' ({strategy}): {null_before} → {null_after} nulls."


def op_clip_outliers(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    col: str = step["column"]
    if col not in df.columns:
        return df, f"Column '{col}' not found — skipped."

    q1 = df[col].quantile(0.25)
    q3 = df[col].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    before = int(((df[col] < lower) | (df[col] > upper)).sum())
    df[col] = df[col].clip(lower=lower, upper=upper)
    return df, f"Clipped outliers in '{col}' to [{lower:.4f}, {upper:.4f}]. {before} values affected."


def op_standardise_categories(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    col: str = step["column"]
    if col not in df.columns:
        return df, f"Column '{col}' not found — skipped."
    before = df[col].nunique()
    df[col] = df[col].astype(str).str.strip().str.title()
    after = df[col].nunique()
    return df, f"Standardised categories in '{col}': {before} → {after} unique values."


def op_parse_dates(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    col: str = step["column"]
    if col not in df.columns:
        return df, f"Column '{col}' not found — skipped."
    before_nulls = int(df[col].isna().sum())
    try:
        df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce")
    except Exception:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    after_nulls = int(df[col].isna().sum())
    return df, f"Parsed '{col}' as datetime. Null change: {before_nulls} → {after_nulls}."


def op_drop_column(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    col: str = step["column"]
    if col not in df.columns:
        return df, f"Column '{col}' not found — skipped."
    df = df.drop(columns=[col])
    return df, f"Dropped column '{col}'."


def op_rename_column(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    col: str = step["column"]
    new_name: str = step["new_name"]
    if col not in df.columns:
        return df, f"Column '{col}' not found — skipped."
    df = df.rename(columns={col: new_name})
    return df, f"Renamed '{col}' → '{new_name}'."


def op_cast_numeric(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    col: str = step["column"]
    if col not in df.columns:
        return df, f"Column '{col}' not found — skipped."
    before_nulls = int(df[col].isna().sum())
    df[col] = pd.to_numeric(df[col], errors="coerce")
    after_nulls = int(df[col].isna().sum())
    return df, f"Cast '{col}' to numeric. Null change: {before_nulls} → {after_nulls}."


def op_drop_high_missing(df: pd.DataFrame, step: dict) -> tuple[pd.DataFrame, str]:
    threshold: float = step.get("threshold", 0.5)
    null_pct = df.isna().mean()
    cols_to_drop = null_pct[null_pct > threshold].index.tolist()
    df = df.drop(columns=cols_to_drop)
    return df, f"Dropped {len(cols_to_drop)} columns with >{threshold*100:.0f}% missing: {cols_to_drop}"


OPERATION_REGISTRY: dict[str, Any] = {
    "remove_duplicates": op_remove_duplicates,
    "fill_missing": op_fill_missing,
    "clip_outliers": op_clip_outliers,
    "standardise_categories": op_standardise_categories,
    "parse_dates": op_parse_dates,
    "drop_column": op_drop_column,
    "rename_column": op_rename_column,
    "cast_numeric": op_cast_numeric,
    "drop_high_missing": op_drop_high_missing,
}


# --------------------------------------------------------------------------- #
#  Executor                                                                    #
# --------------------------------------------------------------------------- #

def apply_pipeline(df: pd.DataFrame, steps: list[dict]) -> tuple[pd.DataFrame, list[dict]]:
    """
    Apply an ordered list of transformation steps.

    Returns the transformed DataFrame and a log of results per step.
    """
    results: list[dict] = []
    current_df = df.copy()

    for step in steps:
        op_name: str = step.get("operation", "")
        func = OPERATION_REGISTRY.get(op_name)

        if func is None:
            msg = f"Unknown operation '{op_name}' — skipped."
            logger.warning(msg)
            results.append({"step": step.get("step", "?"), "operation": op_name,
                            "status": "skipped", "message": msg})
            continue

        try:
            current_df, msg = func(current_df, step)
            results.append({
                "step": step.get("step", "?"),
                "operation": op_name,
                "column": step.get("column"),
                "status": "success",
                "message": msg,
            })
            logger.info("Step %s [%s]: %s", step.get("step"), op_name, msg)
        except Exception as exc:  # noqa: BLE001
            msg = f"Error in step {step.get('step')} [{op_name}]: {exc}"
            logger.error(msg)
            results.append({
                "step": step.get("step", "?"),
                "operation": op_name,
                "column": step.get("column"),
                "status": "error",
                "message": msg,
            })

    return current_df, results
