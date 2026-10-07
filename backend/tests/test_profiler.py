"""Tests for DataProfiler."""
import pytest
import pandas as pd
from app.services.profiler import profile_dataframe


def test_row_and_column_counts(sample_df):
    profile = profile_dataframe(sample_df)
    assert profile["rows"] == 11
    assert profile["columns"] == 5


def test_missing_values_detected(sample_df):
    profile = profile_dataframe(sample_df)
    age_missing = profile["missing_values"]["age"]
    assert age_missing["count"] > 0
    assert 0 < age_missing["percentage"] < 100


def test_duplicate_detection():
    """Use a DataFrame where rows are truly identical (no unique id column)."""
    df = pd.DataFrame({
        "age": [25, 30, 25, 22, 30],       # rows 0==2, 1==4 are duplicates
        "country": ["France", "Germany", "France", "Spain", "Germany"],
        "revenue": [100.0, 200.0, 100.0, 150.0, 200.0],
    })
    profile = profile_dataframe(df)
    assert profile["duplicate_rows"] >= 2
    assert profile["duplicate_percentage"] > 0


def test_outlier_detection():
    import numpy as np
    df = pd.DataFrame({"val": [10, 11, 12, 10, 11, 12, 10, 11, 12, 1000]})
    profile = profile_dataframe(df)
    assert "val" in profile["outliers"]
    assert profile["outliers"]["val"]["count"] >= 1


def test_categorical_anomaly_detection(sample_df):
    profile = profile_dataframe(sample_df)
    # country has mixed case variants
    assert "country" in profile["categorical_anomalies"]


def test_data_type_detection():
    df = pd.DataFrame({
        "num": [1.0, 2.0, 3.0],
        "cat": ["a", "b", "c"],
    })
    profile = profile_dataframe(df)
    assert profile["column_profiles"]["num"]["column_type"] == "numerical"
    assert profile["column_profiles"]["cat"]["column_type"] == "categorical"


def test_correlation_computed():
    df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10]})
    profile = profile_dataframe(df)
    corr = profile["correlation"]["x"]["y"]
    assert corr is not None
    assert abs(corr - 1.0) < 0.001


def test_numerical_columns_listed(sample_df):
    profile = profile_dataframe(sample_df)
    assert "age" in profile["numerical_columns"] or "revenue" in profile["numerical_columns"]


def test_categorical_columns_listed(sample_df):
    profile = profile_dataframe(sample_df)
    assert "country" in profile["categorical_columns"]
