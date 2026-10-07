"""Tests for DataQualityEngine and quality scoring."""
import pytest
import pandas as pd
from app.services.profiler import profile_dataframe
from app.services.quality_score import calculate_quality_score, summarise_issues


def test_perfect_dataset_scores_100():
    df = pd.DataFrame({
        "id": range(100),
        "value": [float(i) for i in range(100)],
        "category": ["A"] * 50 + ["B"] * 50,
    })
    profile = profile_dataframe(df)
    result = calculate_quality_score(profile)
    # Should be very high (near 100 since no issues)
    assert result["score"] >= 90


def test_dataset_with_missing_scores_lower():
    df_clean = pd.DataFrame({"val": [1.0] * 100, "cat": ["A"] * 100})
    df_missing = pd.DataFrame({"val": [None] * 40 + [1.0] * 60, "cat": ["A"] * 100})

    profile_clean = profile_dataframe(df_clean)
    profile_missing = profile_dataframe(df_missing)

    score_clean = calculate_quality_score(profile_clean)["score"]
    score_missing = calculate_quality_score(profile_missing)["score"]

    assert score_clean > score_missing


def test_score_is_reproducible(sample_df):
    """Same input must produce same output."""
    profile = profile_dataframe(sample_df)
    r1 = calculate_quality_score(profile)
    r2 = calculate_quality_score(profile)
    assert r1["score"] == r2["score"]


def test_score_between_0_and_100(sample_df):
    profile = profile_dataframe(sample_df)
    result = calculate_quality_score(profile)
    assert 0 <= result["score"] <= 100


def test_breakdown_keys_present(sample_df):
    profile = profile_dataframe(sample_df)
    result = calculate_quality_score(profile)
    assert "breakdown" in result
    for key in ["missing_values", "duplicates", "outliers"]:
        assert key in result["breakdown"]


def test_issues_list_non_empty_for_dirty_data(sample_df):
    profile = profile_dataframe(sample_df)
    result = calculate_quality_score(profile)
    assert len(result["issues"]) > 0


def test_issue_structure(sample_df):
    profile = profile_dataframe(sample_df)
    result = calculate_quality_score(profile)
    for issue in result["issues"]:
        assert "type" in issue
        assert "severity" in issue
        assert "description" in issue


def test_summarise_issues(sample_df):
    profile = profile_dataframe(sample_df)
    result = calculate_quality_score(profile)
    summary = summarise_issues(result["issues"])
    assert isinstance(summary, dict)
