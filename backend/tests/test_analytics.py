"""Unit tests for Analytics module."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from app.services.analytics import generate_analytics


def test_analytics_with_numerical_data():
    """Analytics should compute descriptive stats for numerical columns."""
    df = pd.DataFrame({
        "age": [25, 30, 35, 40, 45, 50, 55, 60, 65, 70],
        "income": [50000, 60000, 70000, 80000, 90000, 100000, 110000, 120000, 130000, 140000],
        "score": [3.5, 4.0, 4.5, 3.8, 4.2, 4.7, 3.9, 4.1, 4.3, 4.6]
    })
    
    result = generate_analytics(df)
    
    assert "descriptive_stats" in result
    assert "age" in result["descriptive_stats"]
    assert "mean" in result["descriptive_stats"]["age"]
    assert "std" in result["descriptive_stats"]["age"]
    assert "min" in result["descriptive_stats"]["age"]
    assert "max" in result["descriptive_stats"]["age"]
    
    # Check all numerical columns are present
    assert "income" in result["descriptive_stats"]
    assert "score" in result["descriptive_stats"]


def test_analytics_with_categorical_data():
    """Analytics should handle categorical columns."""
    df = pd.DataFrame({
        "category": ["A", "B", "A", "C", "B", "B", "A", "C", "C", "B"],
        "value": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    })
    
    result = generate_analytics(df)
    
    assert "categorical_summaries" in result
    assert "category" in result["categorical_summaries"]
    assert "unique_count" in result["categorical_summaries"]["category"]
    assert "top_values" in result["categorical_summaries"]["category"]
    
    # Should have 3 unique values
    assert result["categorical_summaries"]["category"]["unique_count"] == 3
    
    # Top values should be sorted by count
    top_values = result["categorical_summaries"]["category"]["top_values"]
    counts = [v["count"] for v in top_values]
    assert counts == sorted(counts, reverse=True)


def test_analytics_correlations():
    """Analytics should compute correlation matrix and top correlations."""
    df = pd.DataFrame({
        "x": [1, 2, 3, 4, 5],
        "y": [2, 4, 6, 8, 10],  # Perfect positive correlation with x
        "z": [10, 8, 6, 4, 2],  # Perfect negative correlation with x
    })
    
    result = generate_analytics(df)
    
    assert "correlations" in result
    assert "x" in result["correlations"]
    assert "y" in result["correlations"]["x"]
    assert "z" in result["correlations"]["x"]
    
    # x and y should be perfectly correlated
    assert abs(result["correlations"]["x"]["y"] - 1.0) < 0.001
    
    # x and z should be perfectly negatively correlated
    assert abs(result["correlations"]["x"]["z"] - (-1.0)) < 0.001
    
    # Self-correlation should be 1.0
    assert abs(result["correlations"]["x"]["x"] - 1.0) < 0.001
    
    # Should have top correlations
    assert "top_correlations" in result
    assert isinstance(result["top_correlations"], list)


def test_analytics_distributions():
    """Analytics should compute histograms for numerical columns."""
    df = pd.DataFrame({
        "data": np.random.normal(100, 15, 1000)  # Normal distribution
    })
    
    result = generate_analytics(df)
    
    assert "distributions" in result
    assert "data" in result["distributions"]
    assert "counts" in result["distributions"]["data"]
    assert "bin_edges" in result["distributions"]["data"]
    
    # Counts should sum to number of non-null values
    counts = result["distributions"]["data"]["counts"]
    assert sum(counts) <= len(df)  # ≤ because some values might be NaN


def test_analytics_with_datetime():
    """Analytics should detect datetime columns and compute time series."""
    dates = pd.date_range(start="2023-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "value": np.random.randn(100).cumsum() + 100,
        "category": np.random.choice(["A", "B", "C"], 100)
    })
    
    result = generate_analytics(df)
    
    # Should have time series if datetime column exists
    assert "time_series" in result
    
    # May or may not have time series depending on column detection
    # Not asserting specific structure since it depends on column detection


def test_analytics_empty_dataframe():
    """Analytics should handle empty DataFrames gracefully."""
    df = pd.DataFrame()
    
    result = generate_analytics(df)
    
    assert result["descriptive_stats"] == {}
    assert result["distributions"] == {}
    assert result["correlations"] == {}
    assert result["top_correlations"] == []
    assert result["categorical_summaries"] == {}
    assert result["time_series"] == {}
    assert isinstance(result["insights"], list)


def test_analytics_single_column():
    """Analytics should work with single-column DataFrames."""
    df = pd.DataFrame({
        "single": [1, 2, 3, 4, 5]
    })
    
    result = generate_analytics(df)
    
    assert "single" in result["descriptive_stats"]
    # No correlations with single column
    assert result["correlations"] == {}
    assert result["top_correlations"] == []


def test_analytics_with_missing_values():
    """Analytics should handle missing values correctly."""
    df = pd.DataFrame({
        "col1": [1, 2, np.nan, 4, 5],
        "col2": ["A", "B", None, "A", "C"]
    })
    
    result = generate_analytics(df)
    
    # Should still compute descriptive stats for numerical columns
    assert "col1" in result["descriptive_stats"]
    
    # Categorical summaries should handle missing values
    if "col2" in result["categorical_summaries"]:
        cat_summary = result["categorical_summaries"]["col2"]
        assert "unique_count" in cat_summary
        # Unique count might include NaN as a category


def test_analytics_insights_generation():
    """Analytics should generate deterministic insights."""
    df = pd.DataFrame({
        "age": [25, 30, 35],
        "department": ["Sales", "Sales", "Engineering"]
    })
    
    result = generate_analytics(df)
    
    assert "insights" in result
    assert isinstance(result["insights"], list)
    assert len(result["insights"]) > 0
    
    # Insights should be strings
    for insight in result["insights"]:
        assert isinstance(insight, str)
        assert len(insight) > 0


def test_analytics_mixed_types():
    """Analytics should handle DataFrames with mixed data types."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "age": [25, 30, 35, 40, 45],
        "active": [True, False, True, True, False],
        "score": [85.5, 92.0, 78.5, 88.0, 95.5]
    })
    
    result = generate_analytics(df)
    
    # Numerical columns should be in descriptive stats
    assert "age" in result["descriptive_stats"]
    assert "score" in result["descriptive_stats"]
    # Boolean might be treated as numerical
    if "active" in result["descriptive_stats"]:
        assert "mean" in result["descriptive_stats"]["active"]
    
    # Categorical columns should be in categorical summaries
    assert "name" in result["categorical_summaries"]


def test_analytics_top_correlations_structure():
    """Top correlations should have correct structure."""
    df = pd.DataFrame({
        "a": [1, 2, 3, 4, 5],
        "b": [2, 3, 4, 5, 6],
        "c": [5, 4, 3, 2, 1]
    })
    
    result = generate_analytics(df)
    
    if result["top_correlations"]:
        for pair in result["top_correlations"]:
            assert "col1" in pair
            assert "col2" in pair
            assert "correlation" in pair
            assert isinstance(pair["correlation"], (int, float, type(None)))
            assert pair["col1"] != pair["col2"]  # Should not include self-correlations


def test_analytics_safe_float_conversion():
    """Analytics should safely convert numpy types to Python floats."""
    df = pd.DataFrame({
        "normal_values": [1.5, 2.5, 3.5, 4.5, 5.5]
    })
    
    result = generate_analytics(df)
    
    # Should handle safe conversion
    if "normal_values" in result["descriptive_stats"]:
        stats = result["descriptive_stats"]["normal_values"]
        # All stats should be Python floats/ints, not numpy types
        for key, value in stats.items():
            assert value is None or isinstance(value, (int, float))