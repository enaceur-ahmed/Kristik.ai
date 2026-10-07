"""Tests for Validator."""
import pandas as pd
from app.services.validator import validate_transformation


def test_pass_when_no_changes():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    result = validate_transformation(df, df.copy(), [])
    assert result["overall_status"] == "PASS"


def test_pass_after_removing_duplicates():
    """Removing exact duplicates causes small row loss — should be WARNING or PASS."""
    # Create a DataFrame where 2 rows duplicate out of 20 = 10% loss → WARNING
    df_before = pd.DataFrame({
        "a": [1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
        "b": ["x"] * 20,
    })
    df_after = df_before.drop_duplicates().reset_index(drop=True)
    result = validate_transformation(df_before, df_after, [])
    assert result["overall_status"] in ("PASS", "WARNING")


def test_failed_when_large_row_loss():
    df_before = pd.DataFrame({"a": range(100)})
    df_after = df_before.head(30)  # 70% row loss
    result = validate_transformation(df_before, df_after, [])
    assert result["overall_status"] == "FAILED"


def test_missing_values_reduced():
    df_before = pd.DataFrame({"val": [None, None, 1.0, 2.0, 3.0]})
    df_after = df_before.fillna(1.5)
    result = validate_transformation(df_before, df_after, [])
    miss_check = next(c for c in result["checks"] if c["name"] == "Missing values")
    assert miss_check["status"] == "PASS"


def test_checks_have_required_fields():
    df = pd.DataFrame({"x": [1, 2, 3]})
    result = validate_transformation(df, df.copy(), [])
    for check in result["checks"]:
        assert "name" in check
        assert "status" in check
        assert "detail" in check
