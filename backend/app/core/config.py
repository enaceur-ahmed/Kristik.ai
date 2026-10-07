"""
Application configuration loaded from environment variables.
All secrets must be set in .env — never hardcoded here.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from pathlib import Path

# .env lives at the project root, regardless of the current working directory.
# This file is <root>/backend/app/core/config.py, so the root is parents[3].
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "AI Data Engineering Copilot"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./data/copilot.db"

    # --- File Upload ---
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # --- LLM Provider ---
    # demo | openai | openrouter | ollama
    # Leave LLM_API_KEY empty (or set LLM_PROVIDER=demo) for offline Demo Mode.
    LLM_PROVIDER: str = "demo"
    LLM_MODEL: str = ""          # set via .env — no default model hardcoded here
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""       # auto-defaults to OpenRouter URL when provider=openrouter
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 4000

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @model_validator(mode="after")
    def _apply_provider_defaults(self) -> "Settings":
        """Auto-fill LLM_BASE_URL when provider=openrouter and it wasn't set."""
        if self.LLM_PROVIDER.lower() == "openrouter" and not self.LLM_BASE_URL:
            self.LLM_BASE_URL = "https://openrouter.ai/api/v1"
        return self


settings = Settings()
