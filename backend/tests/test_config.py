"""Config loading tests (no network, no secrets)."""
import pytest

from app.core import config
from app.core.config import Settings


def test_env_file_is_absolute_and_points_at_project_root():
    """config.py must load .env from the project root, derived from __file__,
    regardless of the current working directory."""
    assert config._ENV_FILE.is_absolute()
    assert config._ENV_FILE.name == ".env"
    # <root>/.env — the project root also holds README.md
    assert (config._ENV_FILE.parent / "README.md").exists()
    assert (config._ENV_FILE.parent / "backend" / "app").exists()


def test_openrouter_base_url_default(monkeypatch):
    """LLM_BASE_URL is auto-filled for openrouter when empty."""
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    s = Settings(_env_file=None)
    assert s.LLM_PROVIDER == "openrouter"
    assert s.LLM_BASE_URL == "https://openrouter.ai/api/v1"


def test_openai_base_url_stays_empty(monkeypatch):
    """No auto-fill for other providers — SDK default is used."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    s = Settings(_env_file=None)
    assert s.LLM_BASE_URL == ""


def test_demo_is_default_provider(monkeypatch):
    """demo is the default provider when nothing is configured."""
    for var in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.LLM_PROVIDER == "demo"
    assert s.LLM_API_KEY == ""


def test_settings_ignores_unknown_env_vars(monkeypatch):
    monkeypatch.setenv("TOTALLY_UNKNOWN_VAR", "x")
    s = Settings(_env_file=None)
    assert s.APP_NAME  # still constructs fine
