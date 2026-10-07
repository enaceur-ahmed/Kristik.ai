"""
Tests for the RAG service: chunking, BM25 retrieval,
query-plan validation/execution, heuristic plan extraction.
Pure Python — no LLM, no network.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services.rag import (
    BM25Index,
    build_chunks,
    execute_plan,
    extract_plan_heuristic,
    retrieve,
    validate_plan,
    _tokenize,
)


@pytest.fixture(scope="module")
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "id": range(1, 41),
        "country": ["France"] * 15 + ["Germany"] * 10
                   + ["Spain"] * 10 + ["Italy"] * 5,
        "revenue": [100.0 + i for i in range(38)]
                   + [None, None],
        "age": [25, None, 30, None, 22] * 8,
    })


class _FakeDB:
    """Minimal stand-in for a SQLAlchemy session: no stored
    artefacts, so build_chunks only produces schema/stats/rows."""

    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

        def order_by(self, *a, **k):
            return self

        def all(self):
            return []

        def limit(self, *a, **k):
            return self

    def query(self, *a, **k):
        return self._Q()


class _FakeDataset:
    def __init__(self, df):
        self.id = "test-ds"
        self.original_filename = "test.csv"
        self.updated_at = "x"
        self._df = df


# --------------------------------------------------------------------------- #
#  Chunking                                                                    #
# --------------------------------------------------------------------------- #
def test_build_chunks_has_schema_chunk(sample_df):
    from app.services.rag import get_dataframe, _CACHE
    _CACHE.clear()
    ds = _FakeDataset(sample_df)
    # patch the dataframe cache so build_chunks uses our df
    import app.services.rag as rag
    rag._CACHE[ds.id] = {"df": sample_df, "updated_at": "x"}
    chunks = build_chunks(ds, _FakeDB())
    rag._CACHE.clear()

    types = [c["type"] for c in chunks]
    assert "schema" in types
    assert "column_stats" in types
    assert "rows" in types
    schema = next(c for c in chunks if c["type"] == "schema")
    assert "40 rows x 4 columns" in schema["text"]
    assert "revenue" in schema["text"]
    # every chunk has the required keys
    for c in chunks:
        assert c["id"] and c["type"] and c["label"] and c["text"]


def test_column_stats_chunk_content(sample_df):
    import app.services.rag as rag
    rag._CACHE.clear()
    ds = _FakeDataset(sample_df)
    rag._CACHE[ds.id] = {"df": sample_df, "updated_at": "x"}
    chunks = build_chunks(ds, _FakeDB())
    rag._CACHE.clear()

    rev = next(c for c in chunks if c["label"] == "column revenue stats")
    assert "missing: 2" in rev["text"]
    assert "min:" in rev["text"] and "max:" in rev["text"]
    assert "mean:" in rev["text"]
    age = next(c for c in chunks if c["label"] == "column age stats")
    assert "missing: 16" in age["text"]


def test_row_chunks_group_20_rows(sample_df):
    import app.services.rag as rag
    rag._CACHE.clear()
    ds = _FakeDataset(sample_df)
    rag._CACHE[ds.id] = {"df": sample_df, "updated_at": "x"}
    chunks = build_chunks(ds, _FakeDB())
    rag._CACHE.clear()

    row_chunks = [c for c in chunks if c["type"] == "rows"]
    assert len(row_chunks) == 2                     # 40 rows / 20
    assert "rows 1-20" in row_chunks[0]["text"]
    assert "rows 21-40" in row_chunks[1]["text"]
    assert "row 1:" in row_chunks[0]["text"]


# --------------------------------------------------------------------------- #
#  BM25 retrieval                                                            #
# --------------------------------------------------------------------------- #
def test_bm25_finds_relevant_chunk():
    docs = [
        "schema: columns id, revenue, country",
        "column revenue stats: missing 2, mean 500, max 999",
        "column age stats: missing 16, mean 30",
        "rows 1-20: row 1: id=1 revenue=100",
    ]
    idx = BM25Index(docs)
    hits = idx.search("revenue missing values", k=3)
    assert hits[0] == 1          # revenue stats chunk ranks first


def test_bm25_tokenize_lowercase():
    assert _tokenize("Hello WORLD foo") == ["hello", "world", "foo"]


def test_retrieve_always_includes_schema(sample_df):
    import app.services.rag as rag
    rag._CACHE.clear()
    ds = _FakeDataset(sample_df)
    df = sample_df
    chunks = []
    # build a real cached index
    schema_text = "schema: columns id, country, revenue, age"
    chunks.append({"id": "a", "type": "schema",
                   "label": "schema", "text": schema_text})
    chunks.append({"id": "b", "type": "column_stats",
                   "label": "column revenue stats",
                   "text": "column revenue: missing 2 mean 500"})
    chunks.append({"id": "c", "type": "column_stats",
                   "label": "column age stats",
                   "text": "column age: missing 16 mean 30"})
    chunks.append({"id": "d", "type": "rows",
                   "label": "rows 1-20", "text": "row 1: revenue 100"})
    rag._CACHE[ds.id] = {
        "df": df, "updated_at": "x",
        "chunks": chunks, "index": BM25Index([c["text"] for c in chunks]),
    }
    result = retrieve(ds, _FakeDB(), "revenue missing mean", k=3)
    rag._CACHE.clear()
    assert result[0]["type"] == "schema"            # schema always first
    assert any(c["label"] == "column revenue stats" for c in result)


# --------------------------------------------------------------------------- #
#  Query plans                                                               #
# --------------------------------------------------------------------------- #
def test_validate_plan_accepts_valid(sample_df):
    ok, err = validate_plan(
        {"operation": "sum", "column": "revenue",
         "group_by": "country"}, sample_df)
    assert ok is True
    assert err is None


def test_validate_plan_rejects_unknown_column(sample_df):
    ok, err = validate_plan({"operation": "mean", "column": "nope"},
                            sample_df)
    assert ok is False
    assert "nope" in err


def test_validate_plan_rejects_unknown_operation(sample_df):
    ok, err = validate_plan(
        {"operation": "drop_table", "column": "revenue"}, sample_df)
    assert ok is False
    assert "whitelist" in err


def test_validate_plan_rejects_unsafe_filter(sample_df):
    ok, err = validate_plan(
        {"operation": "filter_count", "column": "revenue",
         "filter": {"column": "revenue", "operator": "regex",
                    "value": ".*"}},
        sample_df)
    assert ok is False
    assert "operator" in err


def test_execute_plan_filter_count(sample_df):
    res = execute_plan(
        {"operation": "filter_count", "column": "revenue",
         "filter": {"column": "revenue", "operator": "isna"}},
        sample_df)
    assert res["result"]["matching_rows"] == 2
    assert res["result"]["total_rows"] == 40


def test_execute_plan_sum_groupby(sample_df):
    res = execute_plan(
        {"operation": "sum", "column": "revenue",
         "group_by": "country"}, sample_df)
    sums = res["result"]["group_sums"]
    assert float(sums["France"]) == sum(100.0 + i for i in range(15))
    assert float(sums["Italy"]) == sum(100.0 + i for i in range(35, 38))


def test_execute_plan_count_and_value_counts(sample_df):
    res = execute_plan({"operation": "count"}, sample_df)
    assert res["result"]["row_count"] == 40
    res = execute_plan({"operation": "value_counts", "column": "country"},
                       sample_df)
    assert res["result"]["value_counts"]["France"] == 15


def test_execute_plan_groupby_mean(sample_df):
    res = execute_plan(
        {"operation": "groupby_mean", "column": "revenue",
         "group_by": "country"}, sample_df)
    means = res["result"]["group_means"]
    assert float(means["France"]) == pytest.approx(
        sum(100.0 + i for i in range(15)) / 15)


# --------------------------------------------------------------------------- #
#  Heuristic plan extraction                                                 #
# --------------------------------------------------------------------------- #
def test_heuristic_missing_count():
    df = pd.DataFrame({"revenue": [1.0, None, 3.0]})
    plan = extract_plan_heuristic(
        "How many rows have missing revenue?", df)
    assert plan == {"operation": "filter_count", "column": "revenue",
                    "filter": {"column": "revenue",
                               "operator": "isna"}}


def test_heuristic_highest_total_by_group():
    df = pd.DataFrame({"country": ["FR", "DE"], "revenue": [1.0, 2.0]})
    plan = extract_plan_heuristic(
        "Which country has the highest total revenue?", df)
    assert plan["operation"] == "sum"
    assert plan["column"] == "revenue"
    assert plan["group_by"] == "country"


def test_heuristic_french_missing():
    df = pd.DataFrame({"revenue": [1.0, None]})
    plan = extract_plan_heuristic(
        "Combien de lignes ont des revenus manquants ?", df)
    assert plan is not None
    assert plan["operation"] == "filter_count"
    assert plan["column"] == "revenue"


def test_heuristic_no_match_returns_none(sample_df):
    plan = extract_plan_heuristic(
        "Tell me a joke about data engineering", sample_df)
    assert plan is None
