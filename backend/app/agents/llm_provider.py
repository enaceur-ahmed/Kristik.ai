"""
LLM Provider abstraction.

Supports:
  demo       — deterministic local logic, no API key needed
  openai     — OpenAI-compatible API
  openrouter — OpenRouter (same protocol as OpenAI, different base_url)
  ollama     — Local Ollama instance

Provider is selected via LLM_PROVIDER env var.
API keys are NEVER logged, printed, or committed.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Custom exception                                                            #
# --------------------------------------------------------------------------- #

class LLMProviderError(RuntimeError):
    """Raised when the configured LLM provider fails.  Never contains the key."""
    pass


# --------------------------------------------------------------------------- #
#  Base provider                                                               #
# --------------------------------------------------------------------------- #

class LLMProvider:
    """Abstract base."""

    def is_demo(self) -> bool:
        return False

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
#  Demo provider — deterministic, no network                                  #
# --------------------------------------------------------------------------- #

class DemoProvider(LLMProvider):
    """Deterministic fallback.  No LLM call is made."""

    def is_demo(self) -> bool:
        return True

    def chat(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
        return json.dumps({"demo_mode": True,
                           "message": "Demo mode — LLM not configured."})


# --------------------------------------------------------------------------- #
#  OpenAI / OpenRouter provider                                               #
# --------------------------------------------------------------------------- #

def _build_httpx_client():
    """
    Return an httpx.Client with the best available SSL configuration.
    On Windows the system CA store is required for some CAs (e.g. DigiCert).
    On other platforms (Linux/macOS) the default certifi bundle is used.
    """
    import httpx
    import ssl

    # Try Windows system store first
    try:
        ctx = ssl.create_default_context()
        ctx.load_default_certs()
        return httpx.Client(verify=ctx)
    except Exception:
        pass

    # Fall back to httpx default (certifi)
    return httpx.Client()


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package not installed — run: pip install openai")

        http_client = _build_httpx_client()

        extra_headers: dict[str, str] = {}
        if settings.LLM_PROVIDER.lower() == "openrouter":
            extra_headers["HTTP-Referer"] = "http://localhost:5173"
            extra_headers["X-Title"] = "AI Data Engineering Copilot"

        kwargs: dict[str, Any] = {
            "api_key": settings.LLM_API_KEY,
            "http_client": http_client,
            "timeout": 60.0,
            "max_retries": 2,
        }
        if settings.LLM_BASE_URL:
            kwargs["base_url"] = settings.LLM_BASE_URL
        if extra_headers:
            kwargs["default_headers"] = extra_headers

        self._client = OpenAI(**kwargs)
        self.last_usage: dict[str, Any] = {}

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        t0 = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
        except Exception as exc:
            latency = round(time.perf_counter() - t0, 3)
            logger.error(
                "LLM call failed — provider=%s model=%s base_url=%s "
                "error_type=%s message=%s latency=%.3fs",
                settings.LLM_PROVIDER,
                settings.LLM_MODEL,
                settings.LLM_BASE_URL,
                type(exc).__name__,
                str(exc)[:120],
                latency,
            )
            raise LLMProviderError(
                f"{type(exc).__name__}: {str(exc)[:120]}"
            ) from exc

        latency = round(time.perf_counter() - t0, 3)
        usage = response.usage
        self.last_usage = {
            "provider":          settings.LLM_PROVIDER,
            "model":             settings.LLM_MODEL,
            "prompt_tokens":     usage.prompt_tokens     if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "total_tokens":      usage.total_tokens      if usage else None,
            "latency_s":         latency,
        }
        logger.info(
            "LLM call OK — provider=%s model=%s tokens=%s latency=%.3fs",
            settings.LLM_PROVIDER,
            settings.LLM_MODEL,
            self.last_usage.get("total_tokens"),
            latency,
        )
        return response.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
#  Ollama provider                                                             #
# --------------------------------------------------------------------------- #

class OllamaProvider(LLMProvider):
    def __init__(self):
        self._base_url = settings.LLM_BASE_URL or "http://localhost:11434"

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "model":  settings.LLM_MODEL,
            "prompt": f"<system>{system_prompt}</system>\n\n{user_prompt}",
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            return data.get("response", "")
        except Exception as exc:
            raise LLMProviderError(f"Ollama error: {type(exc).__name__}: {exc}") from exc


# --------------------------------------------------------------------------- #
#  Factory                                                                     #
# --------------------------------------------------------------------------- #

def get_llm_provider() -> LLMProvider:
    provider_name = settings.LLM_PROVIDER.lower().strip()

    if provider_name == "demo" or not settings.LLM_API_KEY:
        if provider_name != "demo" and not settings.LLM_API_KEY:
            logger.warning(
                "LLM_API_KEY not set — falling back to Demo Mode. "
                "Set LLM_PROVIDER=demo to suppress this warning."
            )
        logger.info(
            "LLM provider selected: DemoProvider (provider=%s key_set=%s)",
            provider_name,
            bool(settings.LLM_API_KEY),
        )
        return DemoProvider()

    if provider_name in ("openai", "openrouter"):
        logger.info(
            "LLM provider selected: OpenAICompatibleProvider "
            "(provider=%s model=%s base_url=%s)",
            provider_name,
            settings.LLM_MODEL,
            settings.LLM_BASE_URL or "(using SDK default)",
        )
        return OpenAICompatibleProvider()

    if provider_name == "ollama":
        logger.info(
            "LLM provider selected: OllamaProvider (model=%s base_url=%s)",
            settings.LLM_MODEL,
            settings.LLM_BASE_URL or "http://localhost:11434",
        )
        return OllamaProvider()

    logger.warning("Unknown LLM_PROVIDER '%s' — using Demo Mode.", provider_name)
    return DemoProvider()
