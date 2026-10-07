"""Unit tests for Critic Agent."""
import pytest
from unittest.mock import Mock, patch
from app.agents.critic_agent import review_recommendation, review_all_recommendations, _demo_critic_review


def test_demo_critic_review_high_missing_drop_rows():
    """Critic should modify high-risk drop_rows strategy."""
    recommendation = {
        "action": "fill_missing",
        "column": "age",
        "strategy": "drop_rows"
    }
    profile = {
        "column_profiles": {
            "age": {"null_percentage": 35.0}
        }
    }
    
    result = _demo_critic_review(recommendation, profile)
    assert result["status"] == "modified"
    assert result["risk"] == "high"
    assert "significant data loss" in result["reason"]
    assert result["alternative"] is not None
    assert "median" in result["alternative"] or "Unknown" in result["alternative"]


def test_demo_critic_review_safe_drop_rows():
    """Critic should accept safe drop_rows strategy."""
    recommendation = {
        "action": "fill_missing",
        "column": "age",
        "strategy": "drop_rows"
    }
    profile = {
        "column_profiles": {
            "age": {"null_percentage": 5.0}  # Low missing rate
        }
    }
    
    result = _demo_critic_review(recommendation, profile)
    assert result["status"] == "accepted"
    assert result["risk"] == "low"


def test_demo_critic_review_clip_outliers_high_skew():
    """Critic should warn about clipping highly skewed columns."""
    recommendation = {
        "action": "clip_outliers",
        "column": "revenue"
    }
    profile = {
        "column_profiles": {
            "revenue": {"skewness": 4.5}  # Highly skewed
        }
    }
    
    result = _demo_critic_review(recommendation, profile)
    assert result["risk"] == "medium"
    assert "highly skewed" in result["reason"]
    assert "log transform" in result.get("alternative", "")


def test_demo_critic_review_remove_duplicates():
    """Critic should always accept duplicate removal as safe."""
    recommendation = {
        "action": "remove_duplicates"
    }
    profile = {
        "column_profiles": {}
    }
    
    result = _demo_critic_review(recommendation, profile)
    assert result["status"] == "accepted"
    assert result["risk"] == "low"
    assert "always safe" in result["reason"]


def test_demo_critic_review_no_column_profile():
    """Critic should handle missing column profile gracefully."""
    recommendation = {
        "action": "fill_missing",
        "column": "unknown_column"
    }
    profile = {
        "column_profiles": {}
    }
    
    result = _demo_critic_review(recommendation, profile)
    assert result["status"] == "accepted"  # Default behavior
    assert result["risk"] == "low"


@patch("app.agents.critic_agent.get_llm_provider")
def test_review_recommendation_demo_mode(mock_get_provider):
    """review_recommendation should use demo critic in demo mode."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = True
    mock_get_provider.return_value = mock_provider
    
    recommendation = {"action": "remove_duplicates"}
    profile = {}
    
    result = review_recommendation(recommendation, profile, mock_provider)
    assert result["status"] == "accepted"
    assert result["risk"] == "low"
    mock_provider.chat.assert_not_called()  # Should not call LLM


@patch("app.agents.critic_agent.get_llm_provider")
@patch("app.agents.critic_agent.json.loads")
def test_review_recommendation_llm_mode(mock_json_loads, mock_get_provider):
    """review_recommendation should call LLM provider in non-demo mode."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = False
    mock_provider.chat.return_value = '{"status": "accepted", "risk": "low", "reason": "OK", "alternative": null}'
    mock_json_loads.return_value = {"status": "accepted", "risk": "low", "reason": "OK", "alternative": None}
    mock_get_provider.return_value = mock_provider
    
    recommendation = {"action": "fill_missing", "column": "age"}
    profile = {"rows": 100, "columns": 5}
    
    result = review_recommendation(recommendation, profile, mock_provider)
    assert result["status"] == "accepted"
    assert result["risk"] == "low"
    mock_provider.chat.assert_called_once()


@patch("app.agents.critic_agent.get_llm_provider")
@patch("app.agents.critic_agent.json.loads")
def test_review_recommendation_llm_failure_falls_back(mock_json_loads, mock_get_provider):
    """review_recommendation should fall back to demo critic on LLM failure."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = False
    mock_provider.chat.side_effect = Exception("LLM error")
    mock_json_loads.side_effect = Exception("JSON error")
    mock_get_provider.return_value = mock_provider
    
    recommendation = {"action": "remove_duplicates"}
    profile = {}
    
    result = review_recommendation(recommendation, profile, mock_provider)
    assert result["status"] == "accepted"  # From demo fallback
    assert result["risk"] == "low"


@patch("app.agents.critic_agent.get_llm_provider")
def test_review_all_recommendations(mock_get_provider):
    """review_all_recommendations should process all recommendations."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = True
    mock_get_provider.return_value = mock_provider
    
    recommendations = [
        {"id": "1", "action": "remove_duplicates"},
        {"id": "2", "action": "fill_missing", "column": "age", "strategy": "drop_rows"}
    ]
    profile = {"column_profiles": {"age": {"null_percentage": 5.0}}}
    
    results = review_all_recommendations(recommendations, profile, mock_provider)
    assert len(results) == 2
    assert "critic_review" in results[0]
    assert "critic_review" in results[1]
    assert results[0]["id"] == "1"
    assert results[1]["id"] == "2"


def test_demo_critic_review_invalid_action():
    """Critic should handle invalid/unknown actions gracefully."""
    recommendation = {
        "action": "invalid_action",
        "column": "test"
    }
    profile = {}
    
    result = _demo_critic_review(recommendation, profile)
    assert result["status"] == "accepted"  # Default
    assert result["risk"] == "low"


@patch("app.agents.critic_agent.get_llm_provider")
def test_review_recommendation_without_provider(mock_get_provider):
    """review_recommendation should get default provider if none given."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = True
    mock_get_provider.return_value = mock_provider
    
    recommendation = {"action": "remove_duplicates"}
    profile = {}
    
    result = review_recommendation(recommendation, profile)
    mock_get_provider.assert_called_once()
    assert result["status"] == "accepted"


def test_demo_critic_review_json_structure():
    """Critic review should always return complete JSON structure."""
    test_cases = [
        ({"action": "remove_duplicates"}, {}),
        ({"action": "fill_missing", "column": "age", "strategy": "median"},
         {"column_profiles": {"age": {"null_percentage": 10.0}}}),
        ({"action": "clip_outliers", "column": "revenue"},
         {"column_profiles": {"revenue": {"skewness": 1.5}}}),
    ]

    for rec, prof in test_cases:
        result = _demo_critic_review(rec, prof)
        assert "status" in result
        assert "risk" in result
        assert "reason" in result
        assert "alternative" in result
        assert result["status"] in ("accepted", "modified", "rejected")
        assert result["risk"] in ("low", "medium", "high")


# ============================================================
# No silent fallbacks — LLM failures expose llm_fallback flags
# ============================================================

@patch("app.agents.critic_agent.get_llm_provider")
def test_llm_failure_sets_fallback_flags(mock_get_provider):
    """LLM failure falls back to demo critic AND exposes llm_fallback."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = False
    mock_provider.chat.side_effect = Exception("API down")
    mock_get_provider.return_value = mock_provider

    result = review_recommendation({"action": "remove_duplicates"}, {})
    assert result["status"] == "accepted"      # demo critic values
    assert result["risk"] == "low"
    assert result["llm_fallback"] is True
    assert result["llm_error"] is not None
    assert "Exception" in result["llm_error"]


@patch("app.agents.critic_agent.get_llm_provider")
def test_invalid_review_structure_sets_fallback_flags(mock_get_provider):
    """Structurally invalid critic JSON triggers the fallback path."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = False
    mock_provider.chat.return_value = '{"status": "maybe", "risk": "extreme"}'
    mock_get_provider.return_value = mock_provider

    result = review_recommendation({"action": "remove_duplicates"}, {})
    assert result["llm_fallback"] is True


@patch("app.agents.critic_agent.get_llm_provider")
def test_prose_wrapped_review_parsed(mock_get_provider):
    """Review JSON wrapped in prose is parsed without fallback."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = False
    mock_provider.chat.return_value = (
        'Sure! {"status": "accepted", "risk": "low", '
        '"reason": "safe", "alternative": null}'
    )
    mock_get_provider.return_value = mock_provider

    result = review_recommendation({"action": "remove_duplicates"}, {})
    assert result["status"] == "accepted"
    assert "llm_fallback" not in result


@patch("app.agents.critic_agent.get_llm_provider")
def test_fenced_review_parsed(mock_get_provider):
    """Review JSON inside a ```json fence is parsed without fallback."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = False
    mock_provider.chat.return_value = (
        '```json\n{"status": "rejected", "risk": "high", '
        '"reason": "risky", "alternative": "do not do this"}\n```'
    )
    mock_get_provider.return_value = mock_provider

    result = review_recommendation({"action": "fill_missing",
                                    "column": "age",
                                    "strategy": "drop_rows"}, {})
    assert result["status"] == "rejected"
    assert "llm_fallback" not in result


@patch("app.agents.critic_agent.get_llm_provider")
def test_review_all_marks_fallback_per_recommendation(mock_get_provider):
    """review_all_recommendations keeps per-rec fallback flags."""
    mock_provider = Mock()
    mock_provider.is_demo.return_value = False
    mock_provider.chat.side_effect = Exception("API down")
    mock_get_provider.return_value = mock_provider

    recommendations = [{"action": "remove_duplicates"},
                       {"action": "fill_missing", "column": "age"}]
    results = review_all_recommendations(recommendations, {})
    assert len(results) == 2
    for r in results:
        assert r["critic_review"]["llm_fallback"] is True