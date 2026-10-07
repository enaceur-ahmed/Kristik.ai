"""
RAG over a selected dataset — pure Python, no LLM inside.

Builds text chunks from a dataset's stored artefacts (schema, per-column
stats, quality report, recommendations, validation results and row groups),
retrieves the most relevant chunks for a question with a pure-Python BM25
index, and can execute a safe whitelisted "query plan" (count / sum / mean
/ min / max / groupby_count / groupby_mean / value_counts / filter_count)
against the DataFrame with pandas so the LLM never guesses numbers.

Design rule: the LLM never invents statistics — every number in the context
comes from pandas/NumPy or the stored DB artefacts.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.models import (
    Dataset, DataProfile, QualityReport, Recommendation, ValidationResult,
)
from app.services.profiler import load_dataframe
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
#  Configuration                                                              #
# --------------------------------------------------------------------------- #
ROWS_PER_CHUNK = 20          # rows rendered per text chunk
MAX_ROW_CHUNKS = 2000        # cap total row chunks (40k rows covered max)
RETRIEVAL_K = 6              # chunks retrieved per question
MAX_CHUNK_CHARS = 2000       # per-chunk text cap injected into the prompt
MAX_CACHE_SIZE = 8           # cached datasets (DataFrame + index)


# --------------------------------------------------------------------------- #
#  Chunking                                                                   #
# --------------------------------------------------------------------------- #
def _fmt(v: Any) -> str:
    """Compact string formatting for chunk text."""
    if v is None:
        return "null"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def build_chunks(dataset: Dataset, db: Session) -> list[dict[str, Any]]:
    """
    Build the chunk list for a dataset. Each chunk is a dict with
    keys: id, type, label, text. Reads only stored DB artefacts plus
    the dataset file itself (lazily, via the loader).
    """
    chunks: list[dict[str, Any]] = []
    ds_id = dataset.id

    def add(chunk_type: str, label: str, text: str) -> None:
        chunks.append({
            "id": f"{ds_id}:{chunk_type}:{label}",
            "type": chunk_type,
            "label": label,
            "text": text,
        })

    # --- 1. schema chunk (always included in retrieval) ---
    df = get_dataframe(dataset)
    schema_lines = [
        f"dataset: {dataset.original_filename}",
        f"shape: {df.shape[0]} rows x {df.shape[1]} columns",
        "columns:",
    ]
    for col in df.columns:
        dtype = str(df[col].dtype)
        nulls = int(df[col].isna().sum())
        schema_lines.append(f"  - {col} (dtype={dtype}, nulls={nulls})")
    add("schema", "schema", "\n".join(schema_lines))

    # --- 2. per-column stats chunks ---
    for col in df.columns:
        s = df[col]
        lines = [f"column: {col} (dtype={s.dtype})"]
        lines.append(f"  missing: {int(s.isna().sum())} "
                     f"({s.isna().mean() * 100:.2f}%)")
        lines.append(f"  unique: {int(s.nunique(dropna=False))}")
        if pd.api.types.is_numeric_dtype(s):
            lines.append(f"  min: {_fmt(s.min())}  max: {_fmt(s.max())}")
            lines.append(f"  mean: {_fmt(s.mean())}  median: {_fmt(s.median())}")
        else:
            top = s.value_counts(dropna=False).head(5)
            lines.append("  top values: " +
                         ", ".join(f"{_fmt(k)}={int(v)}" for k, v in top.items()))
        add("column_stats", f"column {col} stats", "\n".join(lines))

    # --- 3. stored profile ---
    dp = db.query(DataProfile).filter(DataProfile.dataset_id == ds_id).first()
    if dp is not None:
        pj = dp.profile_json or {}
        lines = ["stored data profile:"]
        for key in ("rows", "columns", "duplicate_rows",
                    "duplicate_percentage", "memory_usage_bytes"):
            if key in pj:
                lines.append(f"  {key}: {_fmt(pj[key])}")
        mv = pj.get("missing_values") or {}
        if isinstance(mv, dict) and mv:
            lines.append("  missing_values: " + ", ".join(
                f"{k}: {_fmt(v.get('count'))} ({_fmt(v.get('percentage'))}%)"
                for k, v in list(mv.items())[:20]
                if isinstance(v, dict)))
        add("profile", "stored profile", "\n".join(lines))

    # --- 4. quality report ---
    qr = db.query(QualityReport).filter(QualityReport.dataset_id == ds_id).first()
    if qr is not None:
        lines = [
            "data quality report:",
            f"  quality score: {_fmt(qr.quality_score)} / 100",
        ]
        bd = qr.score_breakdown_json or {}
        if isinstance(bd, dict):
            lines.append("  score breakdown: " + ", ".join(
                f"{k}: {_fmt(v)}" for k, v in bd.items()))
        issues = qr.issues_json or []
        if isinstance(issues, list) and issues:
            lines.append(f"  issues ({len(issues)}):")
            for iss in issues[:20]:
                if isinstance(iss, dict):
                    lines.append("    - {type} in {col}: {desc}".format(
                        type=iss.get("type", "?"),
                        col=iss.get("column") or "(dataset)",
                        desc=str(iss.get("description") or
                                 iss.get("value") or "")[:160]))
        add("quality", "quality report", "\n".join(lines))

    # --- 5. recommendations ---
    recs = (db.query(Recommendation)
            .filter(Recommendation.dataset_id == ds_id)
            .order_by(Recommendation.created_at).all())
    if recs:
        lines = [f"cleaning recommendations ({len(recs)}):"]
        for r in recs[:20]:
            lines.append(f"  - [{r.severity}] {r.issue} in "
                         f"{r.column_name or '(dataset)'}: {r.action}"
                         + (f" ({r.strategy})" if r.strategy else ""))
        add("recommendations", "recommendations", "\n".join(lines))

    # --- 6. validation results ---
    vals = (db.query(ValidationResult)
            .filter(ValidationResult.dataset_id == ds_id)
            .order_by(ValidationResult.created_at.desc()).limit(3).all())
    if vals:
        lines = ["validation results:"]
        for v in vals:
            lines.append(f"  overall: {v.overall_status}")
            for chk in (v.checks_json or [])[:8]:
                if isinstance(chk, dict):
                    lines.append(f"    - {chk.get('check', '?')}: "
                                 f"{chk.get('status', '?')} "
                                 f"{str(chk.get('detail', ''))[:120]}")
        add("validation", "validation results", "\n".join(lines))

    # --- 7. row chunks (groups of ~20 rows, capped) ---
    total_row_chunks = min(
        math.ceil(len(df) / ROWS_PER_CHUNK) if len(df) else 0,
        MAX_ROW_CHUNKS,
    )
    for i in range(total_row_chunks):
        start = i * ROWS_PER_CHUNK
        end = min(start + ROWS_PER_CHUNK, len(df))
        part = df.iloc[start:end]
        lines = [f"rows {start + 1}-{end} of {len(df)}:"]
        for ridx, (_, row) in enumerate(part.iterrows(), start=start + 1):
            cells = ", ".join(f"{c}={_fmt(row[c])}" for c in df.columns[:12])
            lines.append(f"  row {ridx}: {cells}")
        add("rows", f"rows {start + 1}-{end}", "\n".join(lines))

    if len(df) > MAX_ROW_CHUNKS * ROWS_PER_CHUNK:
        logger.info(
            "RAG: dataset %s has %d rows; row chunks capped at %d "
            "(covers %d rows)", ds_id, len(df), MAX_ROW_CHUNKS,
            MAX_ROW_CHUNKS * ROWS_PER_CHUNK)

    return chunks


# --------------------------------------------------------------------------- #
#  BM25 retrieval (pure Python)                                               #
# --------------------------------------------------------------------------- #
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]


class BM25Index:
    """Okapi BM25 over a list of document strings. Pure Python, no deps."""

    def __init__(self, documents: list[str], k1: float = 1.5,
                 b: float = 0.75) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.tokenized = [_tokenize(d) for d in documents]
        self.n_docs = len(documents)
        self.avgdl = (sum(len(t) for t in self.tokenized) / self.n_docs
                      if self.n_docs else 0.0)
        # document frequency per term
        df: dict[str, int] = {}
        for tokens in self.tokenized:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        self.idf = {
            term: math.log(1 + (self.n_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def _score(self, query_tokens: list[str], doc_idx: int) -> float:
        tokens = self.tokenized[doc_idx]
        if not tokens:
            return 0.0
        dl = len(tokens)
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for term in query_tokens:
            if term not in self.idf:
                continue
            f = tf.get(term, 0)
            if f:
                score += self.idf[term] * (f * (self.k1 + 1)) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return score

    def search(self, query: str, k: int) -> list[int]:
        """Return indices of the top-k documents for the query."""
        if not self.n_docs:
            return []
        qt = _tokenize(query)
        if not qt:
            return list(range(min(k, self.n_docs)))
        scored = [(self._score(qt, i), i) for i in range(self.n_docs)]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [i for _, i in scored[:k]]


# --------------------------------------------------------------------------- #
#  Dataset cache (DataFrame + chunks + index, keyed by dataset id)            #
# --------------------------------------------------------------------------- #
_CACHE: dict[str, dict[str, Any]] = {}


def _evict_cache() -> None:
    while len(_CACHE) > MAX_CACHE_SIZE:
        oldest = next(iter(_CACHE))
        _CACHE.pop(oldest, None)


def get_dataframe(dataset: Dataset) -> pd.DataFrame:
    """
    Lazily load (and cache) the dataset's DataFrame. Never loads the same
    file twice while cached; entries are invalidated when the dataset row
    is updated (e.g. re-profiled).
    """
    entry = _CACHE.get(dataset.id)
    if entry is not None and entry.get("updated_at") == str(dataset.updated_at):
        return entry["df"]
    df = load_dataframe(dataset.file_path, dataset.file_type)
    _CACHE[dataset.id] = {"df": df, "updated_at": str(dataset.updated_at)}
    _evict_cache()
    return df


def get_index(dataset: Dataset, db: Session) -> dict[str, Any]:
    """Return (and cache) the chunk list + BM25 index for a dataset."""
    entry = _CACHE.get(dataset.id)
    if entry is not None and entry.get("updated_at") == str(dataset.updated_at) \
            and "chunks" in entry:
        return entry
    df = get_dataframe(dataset)
    chunks = build_chunks(dataset, db)
    index = BM25Index([c["text"] for c in chunks])
    _CACHE[dataset.id] = {
        "df": df,
        "updated_at": str(dataset.updated_at),
        "chunks": chunks,
        "index": index,
    }
    _evict_cache()
    return _CACHE[dataset.id]


def invalidate(dataset_id: str) -> None:
    """Drop the cached entry for a dataset (e.g. after re-profiling)."""
    _CACHE.pop(dataset_id, None)


def retrieve(dataset: Dataset, db: Session, question: str,
             k: int = RETRIEVAL_K) -> list[dict[str, Any]]:
    """
    Retrieve the top-k chunks for a question. The schema chunk is always
    included so column names/dtypes are never missing from the context.
    """
    entry = get_index(dataset, db)
    chunks: list[dict[str, Any]] = entry["chunks"]
    bm25: BM25Index = entry["index"]
    idxs = bm25.search(question, k)
    # always include the schema chunk (first chunk of type "schema")
    schema_idx = next((i for i, c in enumerate(chunks)
                       if c["type"] == "schema"), 0)
    if schema_idx not in idxs:
        idxs = [schema_idx] + idxs[:k - 1]
    return [chunks[i] for i in idxs]


# --------------------------------------------------------------------------- #
#  Safe query plans                                                           #
# --------------------------------------------------------------------------- #
ALLOWED_OPERATIONS = {
    "count", "sum", "mean", "min", "max",
    "groupby_count", "groupby_mean", "value_counts", "filter_count",
}
ALLOWED_FILTER_OPS = {"isna", "notna", "equals", "not_equals",
                      "gt", "lt", "gte", "lte"}


def validate_plan(plan: Any, df: pd.DataFrame) -> tuple[bool, Optional[str]]:
    """
    Validate a query plan against the whitelist and the real DataFrame.
    Returns (ok, error_message).
    """
    if not isinstance(plan, dict):
        return False, "plan is not a JSON object"
    op = plan.get("operation")
    if op not in ALLOWED_OPERATIONS:
        return False, f"operation '{op}' not in whitelist {sorted(ALLOWED_OPERATIONS)}"

    col = plan.get("column")
    if op in ("sum", "mean", "min", "max", "value_counts",
              "groupby_mean", "filter_count"):
        if not isinstance(col, str) or col not in df.columns:
            return False, f"column '{col}' does not exist in the dataset"

    gb = plan.get("group_by")
    if op in ("groupby_count", "groupby_mean"):
        if not isinstance(gb, str) or gb not in df.columns:
            return False, f"group_by column '{gb}' does not exist in the dataset"
    if op == "sum" and gb is not None:
        if not isinstance(gb, str) or gb not in df.columns:
            return False, f"group_by column '{gb}' does not exist in the dataset"

    flt = plan.get("filter")
    if flt is not None:
        if not isinstance(flt, dict):
            return False, "filter must be an object"
        fcol = flt.get("column")
        fop = flt.get("operator")
        if not isinstance(fcol, str) or fcol not in df.columns:
            return False, f"filter column '{fcol}' does not exist in the dataset"
        if fop not in ALLOWED_FILTER_OPS:
            return False, f"filter operator '{fop}' not in whitelist"
        if fop in ("equals", "not_equals", "gt", "lt", "gte", "lte") \
                and "value" not in flt:
            return False, f"filter operator '{fop}' requires a value"

    return True, None


def _apply_filter(df: pd.DataFrame, flt: dict[str, Any]) -> pd.DataFrame:
    col, fop = flt["column"], flt["operator"]
    s = df[col]
    if fop == "isna":
        return df[s.isna()]
    if fop == "notna":
        return df[s.notna()]
    val = flt.get("value")
    if fop == "equals":
        return df[s == val]
    if fop == "not_equals":
        return df[s != val]
    if fop == "gt":
        return df[s > val]
    if fop == "lt":
        return df[s < val]
    if fop == "gte":
        return df[s >= val]
    if fop == "lte":
        return df[s <= val]
    return df


def execute_plan(plan: dict[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    """
    Execute a validated plan with pandas. Returns a JSON-serializable
    result dict. No eval()/exec() — operations are a fixed whitelist.
    """
    op = plan["operation"]
    col = plan.get("column")
    gb = plan.get("group_by")
    flt = plan.get("filter")

    work = _apply_filter(df, flt) if flt else df
    result: Any
    if op == "count":
        result = {"row_count": int(len(work))}
    elif op == "sum":
        result = {"sum": _fmt(work[col].sum())} if gb is None else {
            "group_sums": {_fmt(k): _fmt(v) for k, v in
                           work.groupby(gb)[col].sum().items()}}
    elif op == "mean":
        result = {"mean": _fmt(work[col].mean())}
    elif op == "min":
        result = {"min": _fmt(work[col].min())}
    elif op == "max":
        result = {"max": _fmt(work[col].max())}
    elif op == "groupby_count":
        result = {"group_counts": {_fmt(k): int(v) for k, v in
                                   work.groupby(gb).size().items()}}
    elif op == "groupby_mean":
        result = {"group_means": {_fmt(k): _fmt(v) for k, v in
                                  work.groupby(gb)[col].mean().items()}}
    elif op == "value_counts":
        result = {"value_counts": {_fmt(k): int(v) for k, v in
                                   work[col].value_counts().head(20).items()}}
    elif op == "filter_count":
        result = {"matching_rows": int(len(work)),
                  "total_rows": int(len(df)),
                  "percentage": round(len(work) / len(df) * 100, 2)
                  if len(df) else 0.0}
    else:  # pragma: no cover — validate_plan already rejects unknown ops
        raise ValueError(f"unknown operation: {op}")

    return {
        "operation": op,
        "column": col,
        "group_by": gb,
        "filter": flt,
        "result": result,
    }


# --------------------------------------------------------------------------- #
#  Heuristic plan extraction (demo mode / first attempt, no LLM)              #
# --------------------------------------------------------------------------- #
_MISSING_RE = re.compile(
    r"(missing|manquant|null|vide|empty)", re.IGNORECASE)
_ROWS_RE = re.compile(
    r"(how many rows|combien de lignes|nombre de lignes|number of rows|"
    r"row count|total rows)", re.IGNORECASE)
_HIGHEST_RE = re.compile(
    r"(highest|largest|most|biggest|top|plus (grand|élevé|fort)|le plus|"
    r"maximum|max)", re.IGNORECASE)
_LOWEST_RE = re.compile(
    r"(lowest|smallest|least|fewest|plus petit|le moins|minimum|min)",
    re.IGNORECASE)
_SUM_RE = re.compile(
    r"(total|sum|somme|combined)", re.IGNORECASE)
_AVG_RE = re.compile(
    r"(average|mean|moyenne|avg)", re.IGNORECASE)
_COUNT_VALUES_RE = re.compile(
    r"(how many (distinct |unique )?|combien de|count of|number of "
    r"(distinct |unique )?values|distribution)", re.IGNORECASE)


def _find_column(question: str, columns: list[str]) -> Optional[str]:
    """Find the known column name mentioned in the question (longest first).

    Matches the exact column name (word boundaries) or, as a light
    fallback for French/English inflections (e.g. revenue/revenus),
    any word starting with the column's 5-char stem.
    """
    q = question.lower()
    words = set(re.findall(r"\w+", q))
    for col in sorted(columns, key=len, reverse=True):
        cl = col.lower()
        if len(cl) <= 2:
            continue
        if re.search(rf"\b{re.escape(cl)}\b", q):
            return col
        if len(cl) >= 5 and any(w.startswith(cl[:5]) for w in words):
            return col
    return None


def _matching_columns(question: str, columns: list[str],
                        df: pd.DataFrame) -> list[str]:
    """All column names mentioned in the question (longest first)."""
    q = question.lower()
    words = set(re.findall(r"\w+", q))
    matched = []
    for col in sorted(columns, key=len, reverse=True):
        cl = col.lower()
        if len(cl) <= 2:
            continue
        exact = re.search(rf"\b{re.escape(cl)}\b", q)
        stem = len(cl) >= 5 and any(w.startswith(cl[:5]) for w in words)
        if exact or stem:
            matched.append(col)
    return matched


def extract_plan_heuristic(question: str,
                           df: pd.DataFrame) -> Optional[dict[str, Any]]:
    """
    Map obvious question patterns to a query plan deterministically.
    Returns None when the question does not match a known pattern.
    Used in demo mode and as a free first attempt before asking the LLM.
    """
    cols = list(df.columns)
    col = _find_column(question, cols)
    q = question

    # "How many rows have missing <col>?" / "missing values in <col>"
    if col and _MISSING_RE.search(q):
        return {"operation": "filter_count", "column": col,
                "filter": {"column": col, "operator": "isna"}}

    # "Which <group> has the highest/lowest total <col>?"
    if _HIGHEST_RE.search(q) or _LOWEST_RE.search(q):
        matched = _matching_columns(question, cols, df)
        if len(matched) >= 2:
            # the numeric column is the measure, the other the group
            numeric = [c for c in matched
                       if pd.api.types.is_numeric_dtype(df[c])]
            categorical = [c for c in matched
                           if not pd.api.types.is_numeric_dtype(df[c])]
            if numeric and categorical:
                return {"operation": "sum",
                        "column": numeric[0],
                        "group_by": categorical[0]}
            return {"operation": "sum", "column": matched[0],
                    "group_by": matched[1]}
        if matched and _SUM_RE.search(q):
            return {"operation": "max", "column": matched[0]}

    # "How many rows ...?" (no missing keyword)
    if _ROWS_RE.search(q):
        return {"operation": "count"}

    # "total/sum of <col>"
    if col and _SUM_RE.search(q):
        return {"operation": "sum", "column": col}

    # "average/mean of <col>"
    if col and _AVG_RE.search(q):
        return {"operation": "mean", "column": col}

    # "min/max of <col>"
    if col and (_LOWEST_RE.search(q) or _HIGHEST_RE.search(q)) and \
            not _SUM_RE.search(q):
        return {"operation": "min" if _LOWEST_RE.search(q) else "max",
                "column": col}
    # "how many distinct values / distribution of <col>"
    if col and _COUNT_VALUES_RE.search(q):
        return {"operation": "value_counts", "column": col}

    return None
