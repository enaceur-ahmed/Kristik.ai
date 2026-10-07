"""
scripts/test_llm.py — LLM provider smoke test.

Loads settings, builds the configured provider, sends a one-word prompt,
and reports: provider class, model, base_url, success/failure, latency.

NEVER prints or logs the API key.

Usage (from the backend/ directory):
    python scripts/test_llm.py

To test OpenRouter, set these env vars first (PowerShell):
    $env:LLM_PROVIDER = "openrouter"
    $env:LLM_MODEL    = "<model-id-from-openrouter.ai/models>"
    $env:LLM_API_KEY  = "<your-key>"          # never commit this
    python scripts/test_llm.py
"""
from __future__ import annotations

import sys
import time

# Windows consoles default to cp1252 — the report below uses Unicode
# box-drawing characters, so force UTF-8 output (with safe fallbacks).
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Allow running from the backend/ directory without installing the package
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.agents.llm_provider import (
    get_llm_provider,
    LLMProviderError,
    DemoProvider,
    OpenAICompatibleProvider,
    OllamaProvider,
)


def _mask_key(key: str) -> str:
    """Show only the prefix and last 4 chars — never the full key."""
    if not key:
        return "(not set)"
    if len(key) <= 12:
        return "***"
    return key[:8] + "..." + key[-4:]


def main() -> None:
    print("\n── LLM Provider Smoke Test ──────────────────────────────")
    print(f"  provider : {settings.LLM_PROVIDER}")
    print(f"  model    : {settings.LLM_MODEL or '(empty)'}")
    print(f"  base_url : {settings.LLM_BASE_URL or '(SDK default)'}")
    print(f"  api_key  : {_mask_key(settings.LLM_API_KEY)}")
    print(f"  demo_mode: {not bool(settings.LLM_API_KEY)}")
    print("─────────────────────────────────────────────────────────")

    provider = get_llm_provider()
    print(f"  class    : {type(provider).__name__}")

    system_prompt = "You are a helpful assistant. Reply with a single word only."
    user_prompt   = "Say hi in one word."

    t0 = time.perf_counter()
    try:
        response = provider.chat(system_prompt, user_prompt)
        latency = round(time.perf_counter() - t0, 3)
        print(f"\n  ✅  SUCCESS  latency={latency}s")
        print(f"  response : {response[:120]!r}")

        if isinstance(provider, OpenAICompatibleProvider) and provider.last_usage:
            u = provider.last_usage
            print(f"  tokens   : prompt={u['prompt_tokens']}  "
                  f"completion={u['completion_tokens']}  total={u['total_tokens']}")

    except LLMProviderError as exc:
        latency = round(time.perf_counter() - t0, 3)
        print(f"\n  ❌  FAILED  latency={latency}s")
        print(f"  error    : {exc}")
        sys.exit(1)

    print()

    if isinstance(provider, DemoProvider):
        print("─────────────────────────────────────────────────────────")
        print("  Running in Demo Mode.  To switch to OpenRouter, set:")
        print()
        print("    LLM_PROVIDER = openrouter")
        print("    LLM_MODEL    = <model-id-from-openrouter.ai/models>")
        print("    LLM_API_KEY  = <your-key>   # get one at openrouter.ai/keys")
        print("    LLM_BASE_URL =               # auto-filled for openrouter")
        print()
        print("  PowerShell example:")
        print("    $env:LLM_PROVIDER='openrouter'")
        print("    $env:LLM_MODEL='<model-id>'")
        print("    $env:LLM_API_KEY='<your-key>'")
        print("    python scripts/test_llm.py")
        print("─────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
