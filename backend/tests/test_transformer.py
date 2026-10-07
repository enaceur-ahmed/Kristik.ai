"""Tests for cleaning transformations."""
import pandas as pd
import numpy as np
import pytest
from app.services.transformer import apply_pipeline


def make_df():
    return pd.DataFrame({
        "age": [25.0, None, 30.0, None, 22.0],
        "country": ["France", "france", "FRANCE", "germany", "Germany"],
        "revenue": [100.0, 200.0, 9999.0, 150.0, 175.0],
        "date_str": ["2023-01-15", "2023-02-20", "2023-03-10", "2023-04-05", "2023-05-01"],
    })


def test_remove_duplicates():
    df = pd.DataFrame({"a": [1, 2, 2, 3], "b": ["x", "y", "y", "z"]})
    steps = [{"step": 1, "operation": "remove_duplicates"}]
    result, logs = apply_pipeline(df, steps)
    assert len(result) == 3
    assert logs[0]["status"] == "success"


def test_fill_missing_median():
    df = make_df()
    steps = [{"step": 1, "operation": "fill_missing", "column": "age", "strategy": "median"}]
    result, logs = apply_pipeline(df, steps)
    assert result["age"].isna().sum() == 0
    assert logs[0]["status"] == "success"


def test_fill_missing_mode():
    df = make_df()
    steps = [{"step": 1, "operation": "fill_missing", "column": "country", "strategy": "mode"}]
    result, logs = apply_pipeline(df, steps)
    assert result["country"].isna().sum() == 0


def test_clip_outliers():
    df = make_df()
    steps = [{"step": 1, "operation": "clip_outliers", "column": "revenue"}]
    result, logs = apply_pipeline(df, steps)
    assert result["revenue"].max() < 9999.0
    assert logs[0]["status"] == "success"


def test_standardise_categories():
    df = make_df()
    steps = [{"step": 1, "operation": "standardise_categories", "column": "country"}]
    result, logs = apply_pipeline(df, steps)
    unique_vals = result["country"].unique().tolist()
    # After title() all should be consistent
    for v in unique_vals:
        assert v == v.title()


def test_parse_dates():
    df = make_df()
    steps = [{"step": 1, "operation": "parse_dates", "column": "date_str"}]
    result, logs = apply_pipeline(df, steps)
    assert str(result["date_str"].dtype).startswith("datetime")


def test_unknown_operation_skipped():
    df = make_df()
    steps = [{"step": 1, "operation": "nonexistent_op"}]
    result, logs = apply_pipeline(df, steps)
    assert logs[0]["status"] == "skipped"
    assert len(result) == len(df)


def test_pipeline_multi_step():
    df = pd.DataFrame({
        "val": [1.0, None, 3.0, 1.0, 2.0, None],
        "cat": ["A", "a", "B", "B", "A", "a"],
    })
    steps = [
        {"step": 1, "operation": "remove_duplicates"},
        {"step": 2, "operation": "fill_missing", "column": "val", "strategy": "median"},
        {"step": 3, "operation": "standardise_categories", "column": "cat"},
    ]
    result, logs = apply_pipeline(df, steps)
    assert result["val"].isna().sum() == 0
    assert all(s["status"] == "success" for s in logs)


# ------------------------------------------------------------------ #
#  fill_missing — remaining strategies                               #
# ------------------------------------------------------------------ #

def test_fill_missing_zero():
    df = make_df()
    steps = [{"step": 1, "operation": "fill_missing", "column": "age", "strategy": "zero"}]
    result, logs = apply_pipeline(df, steps)
    assert result["age"].isna().sum() == 0
    assert 0.0 in result["age"].values
    assert logs[0]["status"] == "success"


def test_fill_missing_unknown():
    df = pd.DataFrame({"cat": ["A", None, "B", None, "C"]})
    steps = [{"step": 1, "operation": "fill_missing", "column": "cat", "strategy": "unknown"}]
    result, logs = apply_pipeline(df, steps)
    assert result["cat"].isna().sum() == 0
    assert "Unknown" in result["cat"].values
    assert logs[0]["status"] == "success"


def test_fill_missing_ffill():
    df = pd.DataFrame({"val": [1.0, None, None, 4.0, None]})
    steps = [{"step": 1, "operation": "fill_missing", "column": "val", "strategy": "ffill"}]
    result, logs = apply_pipeline(df, steps)
    # rows 1 and 2 forward-filled from 1.0; row 4 still None (no prior after 4.0)
    assert result["val"].iloc[1] == 1.0
    assert result["val"].iloc[2] == 1.0
    assert logs[0]["status"] == "success"


def test_fill_missing_bfill():
    df = pd.DataFrame({"val": [None, None, 3.0, None, 5.0]})
    steps = [{"step": 1, "operation": "fill_missing", "column": "val", "strategy": "bfill"}]
    result, logs = apply_pipeline(df, steps)
    assert result["val"].iloc[0] == 3.0
    assert result["val"].iloc[1] == 3.0
    assert logs[0]["status"] == "success"


def test_fill_missing_drop_rows():
    df = pd.DataFrame({"age": [25.0, None, 30.0, None, 22.0], "x": [1, 2, 3, 4, 5]})
    steps = [{"step": 1, "operation": "fill_missing", "column": "age", "strategy": "drop_rows"}]
    result, logs = apply_pipeline(df, steps)
    assert result["age"].isna().sum() == 0
    assert len(result) == 3
    assert logs[0]["status"] == "success"


# ------------------------------------------------------------------ #
#  drop_column / rename_column / cast_numeric / drop_high_missing    #
# ------------------------------------------------------------------ #

def test_drop_column():
    df = make_df()
    steps = [{"step": 1, "operation": "drop_column", "column": "country"}]
    result, logs = apply_pipeline(df, steps)
    assert "country" not in result.columns
    assert len(result.columns) == len(df.columns) - 1
    assert logs[0]["status"] == "success"


def test_rename_column():
    df = make_df()
    steps = [{"step": 1, "operation": "rename_column", "column": "age", "new_name": "customer_age"}]
    result, logs = apply_pipeline(df, steps)
    assert "customer_age" in result.columns
    assert "age" not in result.columns
    assert logs[0]["status"] == "success"


def test_cast_numeric():
    df = pd.DataFrame({"amount": ["10", "20", "abc", "30", None]})
    steps = [{"step": 1, "operation": "cast_numeric", "column": "amount"}]
    result, logs = apply_pipeline(df, steps)
    assert pd.api.types.is_float_dtype(result["amount"]) or pd.api.types.is_integer_dtype(result["amount"])
    # "abc" should become NaN
    assert result["amount"].isna().sum() >= 1
    assert logs[0]["status"] == "success"


def test_drop_high_missing():
    df = pd.DataFrame({
        "good": [1, 2, 3, 4, 5],
        "bad":  [None, None, None, None, 1],   # 80% missing — above default 50% threshold
    })
    steps = [{"step": 1, "operation": "drop_high_missing"}]
    result, logs = apply_pipeline(df, steps)
    assert "bad" not in result.columns
    assert "good" in result.columns
    assert logs[0]["status"] == "success"


def test_drop_high_missing_custom_threshold():
    df = pd.DataFrame({
        "col_a": [None, 2, 3, 4, 5],          # 20% missing
        "col_b": [None, None, None, 4, 5],     # 60% missing
    })
    steps = [{"step": 1, "operation": "drop_high_missing", "threshold": 0.5}]
    result, logs = apply_pipeline(df, steps)
    assert "col_b" not in result.columns
    assert "col_a" in result.columns


# ------------------------------------------------------------------ #
#  Missing-column guard (all ops that take a column)                 #
# ------------------------------------------------------------------ #

def test_missing_column_guard():
    """All column ops should skip gracefully when the column doesn't exist."""
    df = pd.DataFrame({"x": [1, 2, 3]})
    ops_with_col = [
        {"step": 1, "operation": "fill_missing",           "column": "no_such_col", "strategy": "median"},
        {"step": 2, "operation": "clip_outliers",           "column": "no_such_col"},
        {"step": 3, "operation": "standardise_categories", "column": "no_such_col"},
        {"step": 4, "operation": "parse_dates",            "column": "no_such_col"},
        {"step": 5, "operation": "drop_column",            "column": "no_such_col"},
        {"step": 6, "operation": "rename_column",          "column": "no_such_col", "new_name": "y"},
        {"step": 7, "operation": "cast_numeric",           "column": "no_such_col"},
    ]
    result, logs = apply_pipeline(df, ops_with_col)
    # DataFrame must be unchanged
    assert list(result.columns) == ["x"]
    assert len(result) == 3
    # All steps should be "success" (they return a skip message, not an error)
    for log in logs:
        assert log["status"] == "success", f"Expected success (skip), got {log['status']} for {log['operation']}"
