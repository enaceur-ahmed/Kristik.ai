"""DataEngineerAgent tests (mocked — no network, no real key)."""
from unittest.mock import Mock

import pytest

from app.agents.data_engineer_agent import (
    _parse_json_array,
    generate_recommendations,
)
from app.agents.llm_provider import DemoProvider


PROFILE = {
    "rows": 100,
    "columns": 3,
    "duplicate_percentage": 5.0,
    "missing_values": {"age": {"count": 5, "percentage": 5.0}},
    "outliers": {},
    "categorical_anomalies": {},
    "column_profiles": {
        "age": {"column_type": "numerical", "skewness": 0.1},
    },
}
ISSUES = [{"type": "missing_values", "column": "age"}]


# ============================================================
# JSON parsing robustness
# ============================================================

def test_parse_json_array_plain():
    assert _parse_json_array('[{"a": 1}]') == [{"a": 1}]


def test_parse_json_array_fenced():
    raw = '```json\n[{"a": 1}]\n```'
    assert _parse_json_array(raw) == [{"a": 1}]


def test_parse_json_array_fenced_no_language():
    raw = '```\n[{"a": 1}]\n```'
    assert _parse_json_array(raw) == [{"a": 1}]


def test_parse_json_array_with_surrounding_prose():
    raw = 'Sure! Here are the recommendations: [{"a": 1}] — hope that helps.'
    assert _parse_json_array(raw) == [{"a": 1}]


def test_parse_json_array_invalid_returns_none():
    assert _parse_json_array("garbage") is None
    assert _parse_json_array("") is None
    assert _parse_json_array(None) is None


def test_parse_json_array_object_not_array_returns_none():
    assert _parse_json_array('{"a": 1}') is None


def test_parse_json_array_non_dict_items_returns_none():
    assert _parse_json_array('[1, 2, 3]') is None


# ============================================================
# generate_recommendations
# ============================================================

def test_demo_mode_returns_deterministic_recs():
    recs, meta = generate_recommendations(PROFILE, ISSUES, DemoProvider())
    assert isinstance(recs, list)
    assert len(recs) > 0
    assert meta["llm_fallback"] is False
    assert meta["llm_error"] is None
    assert meta["provider"] == "DemoProvider"
    assert meta["model"] is None


def test_llm_failure_falls_back_with_flags():
    provider = Mock()
    provider.is_demo.return_value = False
    provider.chat.side_effect = Exception("API down")
    recs, meta = generate_recommendations(PROFILE, ISSUES, provider)
    assert isinstance(recs, list)          # deterministic fallback used
    assert meta["llm_fallback"] is True
    assert meta["llm_error"] is not None
    assert "Exception" in meta["llm_error"]
    assert "API down" in meta["llm_error"]


def test_invalid_json_falls_back_with_flags():
    provider = Mock()
    provider.is_demo.return_value = False
    provider.chat.return_value = "this is not json"
    recs, meta = generate_recommendations(PROFILE, ISSUES, provider)
    assert isinstance(recs, list)
    assert meta["llm_fallback"] is True
    assert "ValueError" in meta["llm_error"]


def test_successful_llm_call_no_fallback():
    provider = Mock()
    provider.is_demo.return_value = False
    provider.chat.return_value = '[{"issue": "x", "action": "fill_missing"}]'
    recs, meta = generate_recommendations(PROFILE, ISSUES, provider)
    assert recs == [{"issue": "x", "action": "fill_missing"}]
    assert meta["llm_fallback"] is False
    assert meta["llm_error"] is None
    assert meta["provider"] == "Mock"
