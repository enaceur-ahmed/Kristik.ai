"""Integration tests for API endpoints."""
import io
import pytest
import pandas as pd


# ============================================================
#  Health
# ============================================================

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "app" in data
    assert "demo_mode" in data
    assert isinstance(data["demo_mode"], bool)


# ============================================================
#  Upload
# ============================================================

def test_upload_csv(client, sample_csv_bytes):
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("test.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["file_type"] == "csv"
    assert data["original_filename"] == "test.csv"
    assert data["file_size_bytes"] > 0
    assert data["status"] == "uploaded"


def test_upload_xlsx(client, sample_xlsx_bytes):
    """XLSX files are uploaded, profiled, and processed correctly."""
    r = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "test.xlsx",
                io.BytesIO(sample_xlsx_bytes),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["file_type"] == "xlsx"
    assert data["file_size_bytes"] > 0
    dataset_id = data["id"]

    # Profile XLSX — verifies load_dataframe handles xlsx path
    r = client.post(f"/api/datasets/{dataset_id}/profile")
    assert r.status_code == 200
    profile = r.json()
    pj = profile["profile_json"]
    assert pj["rows"] == 30
    assert pj["columns"] == 4
    # 'product' and 'region' should be categorical
    assert "product" in pj["categorical_columns"] or "region" in pj["categorical_columns"]


def test_upload_invalid_type(client):
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 400
    assert "detail" in r.json()


def test_upload_empty_file(client):
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert r.status_code == 400


# ============================================================
#  Dataset list / retrieve / delete
# ============================================================

def test_list_datasets(client, sample_csv_bytes):
    client.post(
        "/api/datasets/upload",
        files={"file": ("list_test.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    r = client.get("/api/datasets")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    item = data["items"][0]
    assert "id" in item
    assert "name" in item
    assert "file_type" in item


def test_get_nonexistent_dataset(client):
    r = client.get("/api/datasets/does-not-exist")
    assert r.status_code == 404


def test_delete_dataset(client, sample_csv_bytes):
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("to_delete.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    r = client.delete(f"/api/datasets/{dataset_id}")
    assert r.status_code == 204
    # Confirm it's gone
    r = client.get(f"/api/datasets/{dataset_id}")
    assert r.status_code == 404


# ============================================================
#  Preview
# ============================================================

def test_preview_endpoint(client, sample_csv_bytes):
    """Preview returns columns, rows, and metadata."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("preview_test.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]

    r = client.get(f"/api/datasets/{dataset_id}/preview")
    assert r.status_code == 200
    data = r.json()
    assert "dataset_id" in data
    assert "columns" in data
    assert "rows" in data
    assert "row_count" in data
    assert "preview_rows" in data
    assert isinstance(data["columns"], list)
    assert isinstance(data["rows"], list)
    assert len(data["columns"]) > 0
    assert len(data["rows"]) <= data["preview_rows"]


def test_preview_custom_limit(client, sample_csv_bytes):
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("prev_limit.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    r = client.get(f"/api/datasets/{dataset_id}/preview?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert len(data["rows"]) <= 5


def test_preview_nonexistent(client):
    r = client.get("/api/datasets/no-such-id/preview")
    assert r.status_code == 404


# ============================================================
#  Full workflow (upload → profile → quality → recs → pipeline → execute → validate)
# ============================================================

def test_full_workflow(client, sample_csv_bytes):
    """Upload → profile → quality → recommendations → pipeline generate → execute → validate."""
    # Upload
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("workflow.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    assert r.status_code == 201
    dataset_id = r.json()["id"]

    # Profile
    r = client.post(f"/api/datasets/{dataset_id}/profile")
    assert r.status_code == 200
    profile = r.json()
    assert "profile_json" in profile
    pj = profile["profile_json"]
    assert pj["rows"] > 0
    assert pj["columns"] > 0
    assert "missing_values" in pj
    assert "outliers" in pj

    # Quality
    r = client.post(f"/api/datasets/{dataset_id}/quality")
    assert r.status_code == 200
    quality = r.json()
    assert 0 <= quality["quality_score"] <= 100
    assert isinstance(quality["issues_json"], list)
    assert "score_breakdown_json" in quality

    # Recommendations
    r = client.post(f"/api/datasets/{dataset_id}/recommendations")
    assert r.status_code == 200
    recs_resp = r.json()
    # Response is an object carrying the recommendations plus LLM metadata
    assert isinstance(recs_resp, dict)
    for key in ("recommendations", "llm_fallback", "llm_error",
                "provider", "model", "demo_mode"):
        assert key in recs_resp, f"Missing key: {key}"
    assert recs_resp["llm_fallback"] is False   # demo mode is deterministic, not a fallback
    assert recs_resp["llm_error"] is None
    assert recs_resp["demo_mode"] is True
    recs = recs_resp["recommendations"]
    assert isinstance(recs, list)
    if recs:
        rec = recs[0]
        assert "action" in rec
        assert "severity" in rec
        assert "reason" in rec

    # Apply first recommendation
    applied_id = None
    if recs:
        rec_id = recs[0]["id"]
        r = client.patch(
            f"/api/datasets/{dataset_id}/recommendations/{rec_id}",
            json={"action": "apply"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "applied"
        applied_id = rec_id

    # Reject second recommendation if it exists
    if len(recs) > 1:
        r = client.patch(
            f"/api/datasets/{dataset_id}/recommendations/{recs[1]['id']}",
            json={"action": "reject"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    # Generate pipeline
    r = client.post(f"/api/datasets/{dataset_id}/pipeline/generate")
    assert r.status_code == 200
    pipeline = r.json()
    assert "steps_json" in pipeline
    assert isinstance(pipeline["steps_json"], list)
    assert "generated_code" in pipeline
    assert pipeline["status"] == "created"
    pipeline_id = pipeline["id"]

    # Execute pipeline
    r = client.post(f"/api/datasets/{dataset_id}/pipeline/{pipeline_id}/execute")
    assert r.status_code == 200
    executed = r.json()
    assert executed["status"] == "completed"
    assert executed["execution_time_s"] is not None
    assert executed["execution_time_s"] >= 0

    # Validation results populated
    r = client.get(f"/api/datasets/{dataset_id}/validation")
    assert r.status_code == 200
    validations = r.json()
    assert len(validations) >= 1
    vr = validations[0]
    assert vr["overall_status"] in ("PASS", "WARNING", "FAILED")
    assert isinstance(vr["checks_json"], list)
    assert len(vr["checks_json"]) > 0
    for check in vr["checks_json"]:
        assert "name" in check
        assert "status" in check
        assert "detail" in check

    # Logs
    r = client.get(f"/api/datasets/{dataset_id}/logs")
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) > 0
    assert "message" in logs[0]
    assert "level" in logs[0]


# ============================================================
#  Pipeline — isolated tests
# ============================================================

def test_pipeline_generate_no_applied_recs(client, sample_csv_bytes):
    """Pipeline with no applied recs generates an empty-step pipeline (not an error)."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("empty_pipe.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    # Profile + quality needed before recommendations
    client.post(f"/api/datasets/{dataset_id}/profile")
    client.post(f"/api/datasets/{dataset_id}/quality")
    # Generate recs but apply none
    client.post(f"/api/datasets/{dataset_id}/recommendations")

    r = client.post(f"/api/datasets/{dataset_id}/pipeline/generate")
    assert r.status_code == 200
    pipeline = r.json()
    assert isinstance(pipeline["steps_json"], list)
    # steps may be empty — that is valid


def test_pipeline_execute_without_generate(client, sample_csv_bytes):
    """Executing a non-existent pipeline returns 404."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("noexec.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    r = client.post(f"/api/datasets/{dataset_id}/pipeline/non-existent-id/execute")
    assert r.status_code == 404


# ============================================================
#  Validation — isolated tests
# ============================================================

def test_validation_no_results_initially(client, sample_csv_bytes):
    """Fresh dataset has no validation results."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("novalidation.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    r = client.get(f"/api/datasets/{dataset_id}/validation")
    assert r.status_code == 200
    assert r.json() == []


# ============================================================
#  Analytics
# ============================================================

def test_analytics_endpoint(client, sample_csv_bytes):
    """Analytics returns all required top-level keys with real computed values."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("analytics.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]

    r = client.get(f"/api/datasets/{dataset_id}/analytics")
    assert r.status_code == 200
    data = r.json()

    # All top-level keys must exist
    for key in ("descriptive_stats", "distributions", "correlations",
                "categorical_summaries", "insights"):
        assert key in data, f"Missing key: {key}"

    # Numerical stats must contain real values
    stats = data["descriptive_stats"]
    assert isinstance(stats, dict)
    # sample_csv has 'age', 'revenue', 'score' as numeric
    for col in stats:
        col_stats = stats[col]
        assert "mean" in col_stats
        # mean must be a real number, not null
        assert col_stats["mean"] is not None

    # Insights are strings
    assert isinstance(data["insights"], list)
    assert all(isinstance(s, str) for s in data["insights"])


def test_analytics_correlations(client, sample_csv_bytes):
    """Correlation matrix only contains numerical columns."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("corr_test.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    data = client.get(f"/api/datasets/{dataset_id}/analytics").json()
    corr = data["correlations"]
    # Keys should be numerical column names
    if corr:
        for col, row in corr.items():
            assert isinstance(row, dict)
            # Self-correlation must be 1.0
            if col in row and row[col] is not None:
                assert abs(row[col] - 1.0) < 0.001


# ============================================================
#  Dashboard
# ============================================================

def test_dashboard_stats(client, sample_csv_bytes):
    r = client.get("/api/datasets/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "total_datasets" in data
    assert "total_issues_detected" in data
    assert "recent_pipelines" in data
    assert data["total_datasets"] >= 0


# ============================================================
#  Error scenarios
# ============================================================

def test_profile_before_upload(client):
    r = client.post("/api/datasets/does-not-exist/profile")
    assert r.status_code == 404


def test_quality_without_profile(client, sample_csv_bytes):
    """Quality endpoint requires profile to exist first."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("no_profile.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    # Call quality WITHOUT profiling first
    r = client.post(f"/api/datasets/{dataset_id}/quality")
    assert r.status_code == 400  # profile required


def test_recommendations_without_quality(client, sample_csv_bytes):
    """Recommendations require both profile and quality."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("no_quality.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    client.post(f"/api/datasets/{dataset_id}/profile")
    # Skip quality — call recommendations directly
    r = client.post(f"/api/datasets/{dataset_id}/recommendations")
    assert r.status_code == 400  # quality required


def test_invalid_recommendation_action(client, sample_csv_bytes):
    """Invalid action value returns 400."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("inv_action.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    client.post(f"/api/datasets/{dataset_id}/profile")
    client.post(f"/api/datasets/{dataset_id}/quality")
    recs = client.post(f"/api/datasets/{dataset_id}/recommendations").json()["recommendations"]
    if recs:
        r = client.patch(
            f"/api/datasets/{dataset_id}/recommendations/{recs[0]['id']}",
            json={"action": "INVALID_ACTION"},
        )
        assert r.status_code == 400


# ============================================================
#  Report
# ============================================================

def test_report_endpoint(client, sample_csv_bytes):
    """Report returns all required top-level keys after a profiled + quality dataset."""
    # Upload + profile + quality
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("report_test.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    client.post(f"/api/datasets/{dataset_id}/profile")
    client.post(f"/api/datasets/{dataset_id}/quality")

    r = client.get(f"/api/datasets/{dataset_id}/report")
    assert r.status_code == 200
    data = r.json()

    for key in ("dataset", "quality_score", "score_breakdown", "issues_detected",
                "recommendations", "pipelines", "validation_results", "profile_summary"):
        assert key in data, f"Missing report key: {key}"

    # Dataset sub-keys
    ds_info = data["dataset"]
    assert "id" in ds_info
    assert "name" in ds_info
    assert "filename" in ds_info

    # Quality score must be a number
    assert isinstance(data["quality_score"], (int, float))
    assert 0 <= data["quality_score"] <= 100

    # Lists
    assert isinstance(data["recommendations"], list)
    assert isinstance(data["pipelines"], list)
    assert isinstance(data["validation_results"], list)
    assert isinstance(data["issues_detected"], list)


def test_report_nonexistent_dataset(client):
    r = client.get("/api/datasets/no-such-id/report")
    assert r.status_code == 404


# ============================================================
#  Benchmark
# ============================================================

def test_benchmark_endpoint(client, sample_csv_bytes):
    """Benchmark returns all three mode results with real measured values."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("bench_test.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]

    r = client.post(f"/api/benchmark/{dataset_id}")
    assert r.status_code == 200
    data = r.json()

    # Top-level keys
    for key in ("baseline_quality_score", "total_issues_detected", "mode_a", "mode_b", "mode_c"):
        assert key in data, f"Missing benchmark key: {key}"

    # Baseline values
    assert isinstance(data["baseline_quality_score"], (int, float))
    assert isinstance(data["total_issues_detected"], int)

    # Each mode must have execution_time_s measured
    for mode_key in ("mode_a", "mode_b", "mode_c"):
        mode = data[mode_key]
        assert "execution_time_s" in mode, f"{mode_key} missing execution_time_s"
        assert isinstance(mode["execution_time_s"], (int, float))
        assert mode["execution_time_s"] >= 0
        assert "llm_fallback" in mode, f"{mode_key} missing llm_fallback"
        assert isinstance(mode["llm_fallback"], bool)


def test_benchmark_nonexistent_dataset(client):
    r = client.post("/api/benchmark/no-such-id")
    assert r.status_code == 404


# ============================================================
# Upload size limit — enforced while streaming (not after read)
# ============================================================

def test_upload_size_limit_enforced(client, sample_csv_bytes, monkeypatch):
    """Files larger than MAX_BYTES are rejected with 413 mid-stream."""
    import app.api.datasets as datasets_module
    monkeypatch.setattr(datasets_module, "MAX_BYTES", 100)

    r = client.post(
        "/api/datasets/upload",
        files={"file": ("too_big.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    assert r.status_code == 413
    assert "limit" in r.json()["detail"].lower()


# ============================================================
# Workflow progress — steps 3-6 advance past "Quality"
# ============================================================

def test_workflow_progress_advances(client, sample_csv_bytes):
    """workflow_progress advances 0 → 2 → 3 → 4 → 5 → 6 as artefacts appear."""
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("progress.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
    )
    dataset_id = r.json()["id"]
    assert r.json()["workflow_progress"] == 0          # Upload active

    client.post(f"/api/datasets/{dataset_id}/profile")
    ds = client.get(f"/api/datasets/{dataset_id}").json()
    assert ds["workflow_progress"] == 2                # Quality next

    client.post(f"/api/datasets/{dataset_id}/quality")
    ds = client.get(f"/api/datasets/{dataset_id}").json()
    assert ds["workflow_progress"] == 3                # AI Recs next

    client.post(f"/api/datasets/{dataset_id}/recommendations")
    ds = client.get(f"/api/datasets/{dataset_id}").json()
    assert ds["workflow_progress"] == 4                # Pipeline next

    # Apply a recommendation so the pipeline has a step
    recs = client.get(f"/api/datasets/{dataset_id}/recommendations").json()
    if recs:
        client.patch(
            f"/api/datasets/{dataset_id}/recommendations/{recs[0]['id']}",
            json={"action": "apply"},
        )

    pipe = client.post(f"/api/datasets/{dataset_id}/pipeline/generate").json()
    ds = client.get(f"/api/datasets/{dataset_id}").json()
    assert ds["workflow_progress"] == 5                # Validate next

    client.post(
        f"/api/datasets/{dataset_id}/pipeline/{pipe['id']}/execute"
    )
    ds = client.get(f"/api/datasets/{dataset_id}").json()
    assert ds["workflow_progress"] == 6                # Analytics next
