"""
DataProfiler — Pure Python / Pandas / NumPy / SciPy.

ALL numerical results are computed here.
The LLM is NEVER called from this module.
"""
from __future__ import annotations

import math
import json
from typing import Any

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _safe_float(v: Any) -> float | None:
    """Convert numpy scalars to plain Python float, return None for NaN/Inf."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _sanitize_for_json(obj: Any) -> Any:
    """
    Recursively convert numpy types to plain Python types so the
    result can be stored in SQLAlchemy JSON columns without errors.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [_sanitize_for_json(v) for v in obj.tolist()]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _value_counts_top(series: pd.Series, n: int = 10) -> list[dict]:
    vc = series.value_counts(dropna=False).head(n)
    return [{"value": str(k), "count": int(v)} for k, v in vc.items()]


def _try_parse_datetime(series: pd.Series) -> bool:
    """
    Try to parse a string series as datetime. Pandas 3.x compatible.

    Tries explicit common formats first before falling back to 'mixed' or
    dateutil inference, eliminating the pandas UserWarning about format
    inference.
    """
    # Common explicit formats to try first — fastest path, no warnings
    _EXPLICIT_FORMATS = [
        "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y",
        "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
        "%d-%b-%Y", "%B %d, %Y", "%b %d, %Y",
    ]
    clean = series.dropna().astype(str)
    if len(clean) == 0:
        return False

    for fmt in _EXPLICIT_FORMATS:
        try:
            result = pd.to_datetime(clean, format=fmt, errors="coerce")
            if result.notna().mean() >= 0.8:
                return True
        except Exception:
            continue

    # Fall back to mixed-format parsing (pandas 3 compatible, no warning)
    try:
        result = pd.to_datetime(clean, format="mixed", errors="coerce")
        if result.notna().mean() >= 0.8:
            return True
    except Exception:
        pass

    return False


# --------------------------------------------------------------------------- #
#  Main profiler                                                               #
# --------------------------------------------------------------------------- #

def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """
    Compute a full structured profile of a DataFrame.

    Returns a JSON-serialisable dict with:
      rows, columns, memory_usage_bytes,
      missing_values, duplicates, data_types,
      column_profiles, outliers, categorical_anomalies
    """
    rows, cols = df.shape
    memory_bytes = int(df.memory_usage(deep=True).sum())
    duplicate_rows = int(df.duplicated().sum())

    # ------------------------------------------------------------------ #
    #  Per-column profile                                                  #
    # ------------------------------------------------------------------ #
    column_profiles: dict[str, dict] = {}
    outliers: dict[str, dict] = {}
    categorical_anomalies: dict[str, list] = {}
    missing_values: dict[str, dict] = {}
    data_types: dict[str, str] = {}

    for col in df.columns:
        series = df[col]
        dtype_str = str(series.dtype)
        null_count = int(series.isna().sum())
        null_pct = round(null_count / rows * 100, 2) if rows > 0 else 0.0

        data_types[col] = dtype_str
        missing_values[col] = {"count": null_count, "percentage": null_pct}

        profile: dict[str, Any] = {
            "dtype": dtype_str,
            "null_count": null_count,
            "null_percentage": null_pct,
            "unique_count": int(series.nunique(dropna=False)),
            "unique_percentage": round(series.nunique(dropna=False) / rows * 100, 2) if rows > 0 else 0.0,
        }

        # ---- Numerical ----
        if pd.api.types.is_numeric_dtype(series):
            non_null = series.dropna()
            profile["column_type"] = "numerical"
            profile["min"] = _safe_float(non_null.min()) if len(non_null) else None
            profile["max"] = _safe_float(non_null.max()) if len(non_null) else None
            profile["mean"] = _safe_float(non_null.mean()) if len(non_null) else None
            profile["median"] = _safe_float(non_null.median()) if len(non_null) else None
            profile["std"] = _safe_float(non_null.std()) if len(non_null) else None
            profile["q25"] = _safe_float(non_null.quantile(0.25)) if len(non_null) else None
            profile["q75"] = _safe_float(non_null.quantile(0.75)) if len(non_null) else None
            profile["skewness"] = _safe_float(non_null.skew()) if len(non_null) > 2 else None
            profile["kurtosis"] = _safe_float(non_null.kurtosis()) if len(non_null) > 3 else None
            profile["zeros"] = int((non_null == 0).sum())
            profile["negatives"] = int((non_null < 0).sum())

            # IQR-based outlier detection
            if len(non_null) >= 4:
                q1 = non_null.quantile(0.25)
                q3 = non_null.quantile(0.75)
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outlier_mask = (non_null < lower) | (non_null > upper)
                outlier_count = int(outlier_mask.sum())
                if outlier_count > 0:
                    outliers[col] = {
                        "count": outlier_count,
                        "percentage": round(outlier_count / rows * 100, 2),
                        "lower_bound": _safe_float(lower),
                        "upper_bound": _safe_float(upper),
                    }
                    profile["outlier_count"] = outlier_count
                else:
                    profile["outlier_count"] = 0
            else:
                profile["outlier_count"] = 0

            # Histogram (up to 10 bins)
            if len(non_null) > 0:
                n_bins = min(10, max(1, len(non_null.unique())))
                counts, bin_edges = np.histogram(non_null, bins=n_bins)
                profile["histogram"] = {
                    "counts": [int(c) for c in counts],
                    "bin_edges": [_safe_float(e) for e in bin_edges],
                }

        # ---- Datetime ----
        elif pd.api.types.is_datetime64_any_dtype(series):
            non_null = series.dropna()
            profile["column_type"] = "datetime"
            profile["min"] = str(non_null.min()) if len(non_null) else None
            profile["max"] = str(non_null.max()) if len(non_null) else None
            profile["range_days"] = int((non_null.max() - non_null.min()).days) if len(non_null) > 1 else 0

        # ---- Categorical / Object ----
        elif not pd.api.types.is_datetime64_any_dtype(series):
            non_null = series.dropna().astype(str)
            profile["column_type"] = "categorical"
            profile["top_values"] = _value_counts_top(non_null)

            # Detect inconsistent categories (mixed case variants)
            lower_counts: dict[str, set] = {}
            for val in non_null.unique():
                key = val.strip().lower()
                lower_counts.setdefault(key, set()).add(val)
            inconsistent = {k: list(v) for k, v in lower_counts.items() if len(v) > 1}
            if inconsistent:
                categorical_anomalies[col] = [
                    {"normalised": k, "variants": v}
                    for k, v in list(inconsistent.items())[:20]
                ]
                profile["inconsistent_category_count"] = len(inconsistent)
            else:
                profile["inconsistent_category_count"] = 0

            # Detect date-like strings stored as object (Pandas 3.x compatible)
            if len(non_null) > 0:
                sample = non_null.head(50)
                # Store as int 0/1 to avoid JSON bool serialization issues
                profile["likely_datetime"] = bool(_try_parse_datetime(sample))

        column_profiles[col] = profile

    # ------------------------------------------------------------------ #
    #  Correlation matrix (numerical only)                                #
    # ------------------------------------------------------------------ #
    num_cols = df.select_dtypes(include="number").columns.tolist()
    correlation: dict[str, Any] = {}
    if len(num_cols) >= 2:
        corr_matrix = df[num_cols].corr()
        correlation = {
            col: {
                other: _safe_float(val)
                for other, val in row.items()
            }
            for col, row in corr_matrix.to_dict().items()
        }

    # ------------------------------------------------------------------ #
    #  Date columns detection                                             #
    # ------------------------------------------------------------------ #
    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
    # also flag object columns that look like dates
    for col, cp in column_profiles.items():
        if cp.get("likely_datetime") and col not in date_cols:
            date_cols.append(col)

    return _sanitize_for_json({
        "rows": rows,
        "columns": cols,
        "memory_usage_bytes": memory_bytes,
        "duplicate_rows": duplicate_rows,
        "duplicate_percentage": round(duplicate_rows / rows * 100, 2) if rows > 0 else 0.0,
        "missing_values": missing_values,
        "data_types": data_types,
        "column_profiles": column_profiles,
        "outliers": outliers,
        "categorical_anomalies": categorical_anomalies,
        "correlation": correlation,
        "numerical_columns": [c for c in df.columns if column_profiles[c].get("column_type") == "numerical"],
        "categorical_columns": [c for c in df.columns if column_profiles[c].get("column_type") == "categorical"],
        "date_columns": date_cols,
    })


def load_dataframe(file_path: str, file_type: str) -> pd.DataFrame:
    """Load CSV or XLSX into a DataFrame with type inference."""
    if file_type == "csv":
        df = pd.read_csv(file_path, low_memory=False)
    elif file_type == "xlsx":
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    # Attempt datetime parsing on object/string columns (Pandas 3.x compatible)
    for col in df.select_dtypes(include=["object", "string"]).columns:
        sample = df[col].dropna().head(30).astype(str)
        if len(sample) > 0 and _try_parse_datetime(sample):
            try:
                df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce")
            except Exception:
                pass  # leave column as-is if parsing fails entirely

    return df
