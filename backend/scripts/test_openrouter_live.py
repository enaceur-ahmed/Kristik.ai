"""
Live integration test — OpenRouter + Qwen.

Verifies the REAL execution path:
  upload → profile → quality → recommendations (via OpenRouter → Qwen)

Usage:
  Set environment variables before running, e.g. with PowerShell:
      $env:LLM_API_KEY = "<your-key>"
      $env:LLM_PROVIDER = "openrouter"
      $env:LLM_BASE_URL = "https://openrouter.ai/api/v1"
      $env:LLM_MODEL    = "qwen/qwen3.8-27b:free"
      python test_openrouter_live.py

The API key is read only from the environment — never printed, never logged.
"""
from __future__ import annotations

import io
import os
import sys
import json

# ── Must be set BEFORE importing app so pydantic-settings picks them up ──────
required = ("LLM_API_KEY", "LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL")
missing = [k for k in required if not os.environ.get(k)]
if missing:
    print(
        "ERROR: The following environment variables must be set before running:\n"
        + "\n".join(f"  {k}" for k in missing)
        + "\n\nExample (PowerShell):\n"
        "  $env:LLM_API_KEY  = '<your-openrouter-key>'\n"
        "  $env:LLM_PROVIDER = 'openrouter'\n"
        "  $env:LLM_BASE_URL = 'https://openrouter.ai/api/v1'\n"
        "  $env:LLM_MODEL    = 'qwen/qwen3.8-27b:free'\n"
        "  python test_openrouter_live.py"
    )
    sys.exit(1)

# ── Sanity-check: key must not be empty ──────────────────────────────────────
if not os.environ["LLM_API_KEY"].strip():
    print("ERROR: LLM_API_KEY is set but empty.")
    sys.exit(1)

# ── Key must start with expected prefix (validates format without printing) ──
if not os.environ["LLM_API_KEY"].startswith("sk-or"):
    print("WARNING: LLM_API_KEY does not start with 'sk-or' — may not be an OpenRouter key.")

import tempfile
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Override DATABASE_URL to a fresh temp DB so this test never touches production data
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp_db.name}")

from app.core.database import Base, get_db
from app.main import app

_engine = create_engine(
    f"sqlite:///{_tmp_db.name}",
    connect_args={"check_same_thread": False},
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
Base.metadata.create_all(bind=_engine)

def _get_db_override():
    db = _Session()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = _get_db_override

_upload_dir = tempfile.mkdtemp(prefix="live_test_uploads_")
import app.core.config as _cfg
_cfg.settings.UPLOAD_DIR = _upload_dir

client = TestClient(app, raise_server_exceptions=True)

# ── Helpers ──────────────────────────────────────────────────────────────────

def step(label: str):
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print('─'*60)

def ok(msg: str):
    print(f"  ✅  {msg}")

def fail(msg: str):
    print(f"  ❌  {msg}")

def info(msg: str):
    print(f"  ℹ   {msg}")

# ── Step 0 — confirm provider config (no key value printed) ─────────────────

step("0 — Provider configuration")
from app.core.config import settings as cfg
info(f"LLM_PROVIDER  = {cfg.LLM_PROVIDER}")
info(f"LLM_MODEL     = {cfg.LLM_MODEL}")
info(f"LLM_BASE_URL  = {cfg.LLM_BASE_URL}")
info(f"LLM_API_KEY   = {'SET (value hidden)' if cfg.LLM_API_KEY else 'NOT SET'}")
info(f"demo_mode     = {not bool(cfg.LLM_API_KEY)}")

assert cfg.LLM_PROVIDER == "openrouter", f"Expected openrouter, got {cfg.LLM_PROVIDER}"
assert cfg.LLM_MODEL == "qwen/qwen3.8-27b:free", f"Wrong model: {cfg.LLM_MODEL}"
assert cfg.LLM_BASE_URL == "https://openrouter.ai/api/v1", f"Wrong base URL: {cfg.LLM_BASE_URL}"
assert cfg.LLM_API_KEY, "LLM_API_KEY is empty"
ok("Configuration verified")

# ── Step 1 — health check ────────────────────────────────────────────────────

step("1 — Health check")
r = client.get("/api/health")
assert r.status_code == 200, f"Health returned {r.status_code}"
h = r.json()
ok(f"status={h['status']}  provider={h['llm_provider']}  model={h['llm_model']}  demo_mode={h['demo_mode']}")
assert h["demo_mode"] is False, "demo_mode should be False when key is set"
assert h["llm_provider"] == "openrouter"
assert h["llm_model"] == "qwen/qwen3.8-27b:free"

# ── Step 2 — upload sales_data.csv ──────────────────────────────────────────

step("2 — Upload data/sales_data.csv")
sales_path = Path(__file__).parent.parent / "data" / "sales_data.csv"
assert sales_path.exists(), f"sales_data.csv not found at {sales_path}"
with open(sales_path, "rb") as fh:
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("sales_data.csv", fh, "text/csv")},
    )
assert r.status_code == 201, f"Upload failed: {r.status_code} — {r.text}"
dataset_id = r.json()["id"]
ok(f"Uploaded — dataset_id={dataset_id}")

# ── Step 3 — profile ─────────────────────────────────────────────────────────

step("3 — Profile")
r = client.post(f"/api/datasets/{dataset_id}/profile")
assert r.status_code == 200, f"Profile failed: {r.status_code} — {r.text}"
pj = r.json()["profile_json"]
ok(f"Profiled — rows={pj['rows']}  columns={pj['columns']}")

# ── Step 4 — quality ─────────────────────────────────────────────────────────

step("4 — Quality score")
r = client.post(f"/api/datasets/{dataset_id}/quality")
assert r.status_code == 200, f"Quality failed: {r.status_code} — {r.text}"
q = r.json()
ok(f"Quality score={q['quality_score']:.1f}  issues={len(q['issues_json'])}")

# ── Step 5 — AI recommendations (real LLM call) ──────────────────────────────

step("5 — AI Recommendations (REAL OpenRouter → Qwen call)")
info("Calling POST /api/datasets/{id}/recommendations ...")
r = client.post(f"/api/datasets/{dataset_id}/recommendations")

if r.status_code != 200:
    fail(f"Recommendations failed: HTTP {r.status_code}")
    print(f"  Response: {r.text[:500]}")
    sys.exit(1)

recs = r.json()
ok(f"HTTP 200 — received {len(recs)} recommendations")

if not recs:
    fail("Empty recommendations list — LLM may have returned nothing parseable")
    sys.exit(1)

# ── Inspect first recommendation ─────────────────────────────────────────────

step("6 — Inspect recommendations (no content logged beyond structure)")
rec0 = recs[0]
required_fields = ("issue", "severity", "action", "reason", "expected_impact")
for field in required_fields:
    assert field in rec0, f"Missing field '{field}' in recommendation"

ok(f"Fields present: {', '.join(required_fields)}")
ok(f"action={rec0['action']}  severity={rec0['severity']}")
info(f"issue={rec0['issue']}")

# Check critic review is attached (from CriticAgent)
if "critic_review" in rec0 and rec0["critic_review"]:
    cr = rec0["critic_review"]
    ok(f"CriticAgent review attached — risk={cr.get('risk')}  status={cr.get('status')}")
else:
    info("critic_review not present on recommendation (may be stored separately)")

# ── Verify provider used (via last_usage on provider instance) ───────────────

step("7 — Verify provider identity and token usage")
from app.agents.llm_provider import get_llm_provider, OpenAICompatibleProvider
live_provider = get_llm_provider()

if isinstance(live_provider, OpenAICompatibleProvider):
    ok("Provider class = OpenAICompatibleProvider  ✅")
    if live_provider.last_usage:
        u = live_provider.last_usage
        ok(f"Diagnostic: provider={u['provider']}  model={u['model']}")
        ok(f"Token usage: prompt={u['prompt_tokens']}  completion={u['completion_tokens']}  total={u['total_tokens']}")
    else:
        info("last_usage not populated (provider instantiated fresh — usage captured at request time)")
else:
    fail(f"Wrong provider class: {type(live_provider).__name__} — expected OpenAICompatibleProvider")
    sys.exit(1)

# ── Final summary ────────────────────────────────────────────────────────────

step("RESULT")
print()
print("  ✅  REAL OpenRouter → Qwen request SUCCEEDED")
print(f"  Provider    : openrouter")
print(f"  Model       : qwen/qwen3.8-27b:free")
print(f"  Endpoint    : https://openrouter.ai/api/v1")
print(f"  HTTP status : 200")
print(f"  Recs parsed : {len(recs)} recommendations")
print(f"  API key     : SET (value never printed)")
print()

# ── Cleanup ──────────────────────────────────────────────────────────────────
import shutil
try:
    os.unlink(_tmp_db.name)
    shutil.rmtree(_upload_dir, ignore_errors=True)
except Exception:
    pass
