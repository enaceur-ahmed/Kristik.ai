"""
Analysis API — profiling, quality, recommendations, pipeline, validation, analytics, report.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging_config import get_logger
from app.core.config import settings
from app.models.dataset import (
    DataProfile, Dataset, ExecutionLog, Pipeline,
    QualityReport, Recommendation, ValidationResult,
)
from app.schemas.dataset import (
    DataProfileRead, ExecutionLogRead, PipelineRead,
    QualityReportRead, RecommendationAction, RecommendationGeneration,
    RecommendationRead, ValidationResultRead,
)

router = APIRouter(prefix="/api/datasets", tags=["analysis"])
logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _get_dataset_or_404(dataset_id: str, db: Session) -> Dataset:
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return ds


def _log(db: Session, dataset_id: str, message: str, level: str = "INFO"):
    entry = ExecutionLog(dataset_id=dataset_id, message=message, level=level)
    db.add(entry)
    db.commit()


def _load_df(ds: Dataset):
    from app.services.profiler import load_dataframe
    return load_dataframe(ds.file_path, ds.file_type)


# --------------------------------------------------------------------------- #
#  Profile                                                                     #
# --------------------------------------------------------------------------- #

@router.post("/{dataset_id}/profile", response_model=DataProfileRead)
def run_profile(dataset_id: str, db: Session = Depends(get_db)):
    """Run (or re-run) data profiling on a dataset."""
    ds = _get_dataset_or_404(dataset_id, db)

    _log(db, dataset_id, "Profiling started.")
    ds.status = "profiling"
    db.commit()

    try:
        from app.services.profiler import profile_dataframe
        df = _load_df(ds)
        profile = profile_dataframe(df)

        # Update dataset metadata
        ds.row_count = profile["rows"]
        ds.column_count = profile["columns"]
        ds.status = "profiled"
        db.commit()

        # Upsert profile record
        existing = db.query(DataProfile).filter(DataProfile.dataset_id == dataset_id).first()
        if existing:
            existing.profile_json = profile
            db.commit()
            db.refresh(existing)
            _log(db, dataset_id, f"Re-profiled: {profile['rows']} rows, {profile['columns']} columns.")
            return existing
        else:
            dp = DataProfile(dataset_id=dataset_id, profile_json=profile)
            db.add(dp)
            db.commit()
            db.refresh(dp)
            _log(db, dataset_id, f"Profiling complete: {profile['rows']} rows, {profile['columns']} columns.")
            return dp

    except Exception as exc:
        ds.status = "error"
        db.commit()
        _log(db, dataset_id, f"Profiling failed: {exc}", "ERROR")
        raise HTTPException(status_code=500, detail=f"Profiling failed: {exc}")


@router.get("/{dataset_id}/profile", response_model=DataProfileRead)
def get_profile(dataset_id: str, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    dp = db.query(DataProfile).filter(DataProfile.dataset_id == dataset_id).first()
    if not dp:
        raise HTTPException(status_code=404, detail="Profile not found. Run POST /profile first.")
    return dp


# --------------------------------------------------------------------------- #
#  Quality                                                                     #
# --------------------------------------------------------------------------- #

@router.post("/{dataset_id}/quality", response_model=QualityReportRead)
def run_quality(dataset_id: str, db: Session = Depends(get_db)):
    """Compute quality score from existing profile."""
    _get_dataset_or_404(dataset_id, db)
    dp = db.query(DataProfile).filter(DataProfile.dataset_id == dataset_id).first()
    if not dp:
        raise HTTPException(status_code=400, detail="Run /profile first.")

    _log(db, dataset_id, "Quality analysis started.")
    try:
        from app.services.quality_score import calculate_quality_score
        result = calculate_quality_score(dp.profile_json)

        existing = db.query(QualityReport).filter(QualityReport.dataset_id == dataset_id).first()
        if existing:
            existing.quality_score = result["score"]
            existing.issues_json = result["issues"]
            existing.score_breakdown_json = result["breakdown"]
            db.commit()
            db.refresh(existing)
        else:
            qr = QualityReport(
                dataset_id=dataset_id,
                quality_score=result["score"],
                issues_json=result["issues"],
                score_breakdown_json=result["breakdown"],
            )
            db.add(qr)
            db.commit()
            db.refresh(qr)
            existing = qr

        _log(db, dataset_id, f"Quality score: {result['score']}/100. Issues: {len(result['issues'])}.")
        return existing

    except Exception as exc:
        _log(db, dataset_id, f"Quality analysis failed: {exc}", "ERROR")
        raise HTTPException(status_code=500, detail=f"Quality analysis failed: {exc}")


@router.get("/{dataset_id}/quality", response_model=QualityReportRead)
def get_quality(dataset_id: str, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    qr = db.query(QualityReport).filter(QualityReport.dataset_id == dataset_id).first()
    if not qr:
        raise HTTPException(status_code=404, detail="Quality report not found. Run POST /quality first.")
    return qr


# --------------------------------------------------------------------------- #
#  Recommendations                                                             #
# --------------------------------------------------------------------------- #

@router.post("/{dataset_id}/recommendations", response_model=RecommendationGeneration)
def generate_recommendations(dataset_id: str, db: Session = Depends(get_db)):
    """Generate AI recommendations (uses demo mode if no API key)."""
    _get_dataset_or_404(dataset_id, db)
    dp = db.query(DataProfile).filter(DataProfile.dataset_id == dataset_id).first()
    qr = db.query(QualityReport).filter(QualityReport.dataset_id == dataset_id).first()

    if not dp:
        raise HTTPException(status_code=400, detail="Run /profile first.")
    if not qr:
        raise HTTPException(status_code=400, detail="Run /quality first.")

    _log(db, dataset_id, "Generating AI recommendations.")
    try:
        from app.agents.data_engineer_agent import generate_recommendations as gen_recs
        from app.agents.critic_agent import review_all_recommendations
        from app.agents.llm_provider import get_llm_provider

        provider = get_llm_provider()
        recs_raw, gen_meta = gen_recs(dp.profile_json, qr.issues_json, provider)
        recs_reviewed = review_all_recommendations(recs_raw, dp.profile_json, provider)

        # Aggregate fallback flags from both the engineer and the critic
        critic_fallbacks = [
            r["critic_review"] for r in recs_reviewed
            if isinstance(r.get("critic_review"), dict)
            and r["critic_review"].get("llm_fallback")
        ]
        llm_fallback = bool(gen_meta.get("llm_fallback") or critic_fallbacks)
        llm_error = gen_meta.get("llm_error")
        if not llm_error and critic_fallbacks:
            llm_error = critic_fallbacks[0].get("llm_error")

        # Clear old recommendations
        db.query(Recommendation).filter(Recommendation.dataset_id == dataset_id).delete()
        db.commit()

        saved = []
        for r in recs_reviewed:
            rec = Recommendation(
                dataset_id=dataset_id,
                issue=r.get("issue", ""),
                column_name=r.get("column"),
                severity=r.get("severity", "medium"),
                action=r.get("action", ""),
                strategy=r.get("strategy"),
                reason=r.get("reason"),
                expected_impact=r.get("expected_impact"),
                status="pending",
                critic_review_json=r.get("critic_review"),
            )
            db.add(rec)
            saved.append(rec)

        db.commit()
        if provider.is_demo():
            mode_label = "Demo Mode"
        elif llm_fallback:
            mode_label = f"{settings.LLM_MODEL} (fallback→demo)"
        else:
            mode_label = settings.LLM_MODEL
        _log(db, dataset_id, f"{len(saved)} recommendations generated ({mode_label}).")
        return RecommendationGeneration(
            recommendations=saved,
            llm_fallback=llm_fallback,
            llm_error=llm_error,
            provider=settings.LLM_PROVIDER,
            model=None if provider.is_demo() else settings.LLM_MODEL,
            demo_mode=provider.is_demo(),
        )

    except Exception as exc:
        _log(db, dataset_id, f"Recommendation generation failed: {exc}", "ERROR")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{dataset_id}/recommendations", response_model=list[RecommendationRead])
def get_recommendations(dataset_id: str, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    return db.query(Recommendation).filter(Recommendation.dataset_id == dataset_id).all()


@router.patch("/{dataset_id}/recommendations/{rec_id}", response_model=RecommendationRead)
def update_recommendation(
    dataset_id: str, rec_id: str,
    body: RecommendationAction,
    db: Session = Depends(get_db),
):
    """Apply or reject a recommendation."""
    rec = db.query(Recommendation).filter(
        Recommendation.id == rec_id,
        Recommendation.dataset_id == dataset_id,
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found.")

    action = body.action.lower()
    if action not in ("apply", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'apply' or 'reject'.")

    rec.status = "applied" if action == "apply" else "rejected"
    db.commit()
    db.refresh(rec)
    _log(db, dataset_id, f"Recommendation '{rec.action}' on '{rec.column_name}' → {rec.status}.")
    return rec


# --------------------------------------------------------------------------- #
#  Pipeline                                                                    #
# --------------------------------------------------------------------------- #

@router.post("/{dataset_id}/pipeline/generate", response_model=PipelineRead)
def generate_pipeline(dataset_id: str, db: Session = Depends(get_db)):
    """Generate pipeline from applied recommendations."""
    ds = _get_dataset_or_404(dataset_id, db)
    recs = db.query(Recommendation).filter(Recommendation.dataset_id == dataset_id).all()

    _log(db, dataset_id, "Pipeline generation started.")
    try:
        from app.agents.pipeline_generator import generate_pipeline as gen_pipe

        recs_dicts = [
            {
                "action": r.action,
                "column": r.column_name,
                "strategy": r.strategy,
                "status": r.status,
            }
            for r in recs
        ]

        result = gen_pipe(recs_dicts, ds.name)

        pipeline = Pipeline(
            dataset_id=dataset_id,
            name=result["name"],
            steps_json=result["steps"],
            generated_code=result["code"],
            status="created",
        )
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)

        _log(db, dataset_id, f"Pipeline '{pipeline.name}' created with {len(result['steps'])} steps.")
        return pipeline

    except Exception as exc:
        _log(db, dataset_id, f"Pipeline generation failed: {exc}", "ERROR")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{dataset_id}/pipeline/{pipeline_id}/execute", response_model=PipelineRead)
def execute_pipeline(dataset_id: str, pipeline_id: str, db: Session = Depends(get_db)):
    """Execute a pipeline and produce validation results."""
    ds = _get_dataset_or_404(dataset_id, db)
    pipeline = db.query(Pipeline).filter(
        Pipeline.id == pipeline_id, Pipeline.dataset_id == dataset_id
    ).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found.")

    _log(db, dataset_id, f"Pipeline '{pipeline.name}' execution started.")
    t0 = time.perf_counter()

    try:
        from app.services.transformer import apply_pipeline
        from app.services.validator import validate_transformation

        df = _load_df(ds)
        df_out, step_results = apply_pipeline(df, pipeline.steps_json)

        elapsed = round(time.perf_counter() - t0, 3)
        pipeline.execution_time_s = elapsed
        pipeline.executed_at = datetime.now(timezone.utc)
        pipeline.status = "completed"
        pipeline.steps_json = [
            {**s, "result": step_results[i] if i < len(step_results) else {}}
            for i, s in enumerate(pipeline.steps_json)
        ]
        # sanitize before commit
        from app.services.profiler import _sanitize_for_json
        pipeline.steps_json = _sanitize_for_json(pipeline.steps_json)
        db.commit()

        # Validation
        validation = validate_transformation(df, df_out, pipeline.steps_json)
        vr = ValidationResult(
            dataset_id=dataset_id,
            pipeline_id=pipeline_id,
            before_json=validation["before"],
            after_json=validation["after"],
            checks_json=validation["checks"],
            overall_status=validation["overall_status"],
        )
        db.add(vr)
        db.commit()

        _log(db, dataset_id,
             f"Pipeline executed in {elapsed}s. Validation: {validation['overall_status']}.")
        db.refresh(pipeline)
        return pipeline

    except Exception as exc:
        pipeline.status = "failed"
        db.commit()
        _log(db, dataset_id, f"Pipeline execution failed: {exc}", "ERROR")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{dataset_id}/pipeline", response_model=list[PipelineRead])
def get_pipelines(dataset_id: str, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    return db.query(Pipeline).filter(Pipeline.dataset_id == dataset_id)\
        .order_by(Pipeline.created_at.desc()).all()


# --------------------------------------------------------------------------- #
#  Validation                                                                  #
# --------------------------------------------------------------------------- #

@router.get("/{dataset_id}/validation", response_model=list[ValidationResultRead])
def get_validation(dataset_id: str, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    return db.query(ValidationResult).filter(ValidationResult.dataset_id == dataset_id)\
        .order_by(ValidationResult.created_at.desc()).all()


# --------------------------------------------------------------------------- #
#  Dataset Preview                                                             #
# --------------------------------------------------------------------------- #

@router.get("/{dataset_id}/preview")
def get_preview(
    dataset_id: str,
    limit: int = Query(default=50, ge=1, le=500, description="Max rows to return"),
    db: Session = Depends(get_db),
):
    """
    Return a bounded row preview of the dataset.

    Never loads the full file into memory when only a preview is needed —
    uses pandas nrows parameter for CSV and head() for XLSX.
    """
    ds = _get_dataset_or_404(dataset_id, db)

    try:
        import pandas as pd

        file_path = ds.file_path
        file_type = ds.file_type

        if file_type == "csv":
            # Read only as many rows as needed — efficient for large files
            df = pd.read_csv(file_path, nrows=limit, low_memory=False)
        elif file_type == "xlsx":
            df = pd.read_excel(file_path, nrows=limit)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")

        # Replace NaN/Inf with None for JSON safety
        import math
        def _safe_val(v):
            if v is None:
                return None
            try:
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return None
            except TypeError:
                pass
            return v

        columns = list(df.columns)
        rows = [
            {col: _safe_val(row[col]) for col in columns}
            for row in df.to_dict(orient="records")
        ]

        return {
            "dataset_id": dataset_id,
            "dataset_name": ds.name,
            "file_type": file_type,
            "columns": columns,
            "rows": rows,
            "row_count": ds.row_count,          # total rows in full dataset (may be None if not profiled)
            "preview_rows": len(rows),
            "limit": limit,
        }

    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset file not found on disk.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview failed: {exc}")


# --------------------------------------------------------------------------- #
#  Analytics                                                                   #
# --------------------------------------------------------------------------- #

@router.get("/{dataset_id}/analytics")
def get_analytics(dataset_id: str, db: Session = Depends(get_db)):
    ds = _get_dataset_or_404(dataset_id, db)
    try:
        from app.services.analytics import generate_analytics
        df = _load_df(ds)
        return generate_analytics(df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# --------------------------------------------------------------------------- #
#  Execution Logs                                                              #
# --------------------------------------------------------------------------- #

@router.get("/{dataset_id}/logs", response_model=list[ExecutionLogRead])
def get_logs(dataset_id: str, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    return db.query(ExecutionLog).filter(ExecutionLog.dataset_id == dataset_id)\
        .order_by(ExecutionLog.created_at.asc()).all()


# --------------------------------------------------------------------------- #
#  Report                                                                      #
# --------------------------------------------------------------------------- #

@router.get("/{dataset_id}/report")
def get_report(dataset_id: str, db: Session = Depends(get_db)):
    """Generate the final comprehensive report."""
    ds = _get_dataset_or_404(dataset_id, db)
    dp = db.query(DataProfile).filter(DataProfile.dataset_id == dataset_id).first()
    qr = db.query(QualityReport).filter(QualityReport.dataset_id == dataset_id).first()
    recs = db.query(Recommendation).filter(Recommendation.dataset_id == dataset_id).all()
    pipelines = db.query(Pipeline).filter(Pipeline.dataset_id == dataset_id)\
        .order_by(Pipeline.created_at.desc()).all()
    validations = db.query(ValidationResult).filter(ValidationResult.dataset_id == dataset_id)\
        .order_by(ValidationResult.created_at.desc()).all()

    report: dict = {
        "dataset": {
            "id": ds.id,
            "name": ds.name,
            "filename": ds.original_filename,
            "rows": ds.row_count,
            "columns": ds.column_count,
            "file_size_bytes": ds.file_size_bytes,
            "created_at": str(ds.created_at),
        },
        "quality_score": qr.quality_score if qr else None,
        "score_breakdown": qr.score_breakdown_json if qr else None,
        "issues_detected": qr.issues_json if qr else [],
        "recommendations": [
            {
                "issue": r.issue,
                "column": r.column_name,
                "severity": r.severity,
                "action": r.action,
                "status": r.status,
                "reason": r.reason,
                "expected_impact": r.expected_impact,
                "critic_review": r.critic_review_json,
            }
            for r in recs
        ],
        "pipelines": [
            {
                "name": p.name,
                "steps": p.steps_json,
                "status": p.status,
                "execution_time_s": p.execution_time_s,
            }
            for p in pipelines
        ],
        "validation_results": [
            {
                "overall_status": v.overall_status,
                "checks": v.checks_json,
                "before": v.before_json,
                "after": v.after_json,
            }
            for v in validations
        ],
        "profile_summary": {
            "numerical_columns": dp.profile_json.get("numerical_columns") if dp else [],
            "categorical_columns": dp.profile_json.get("categorical_columns") if dp else [],
            "date_columns": dp.profile_json.get("date_columns") if dp else [],
        } if dp else {},
    }
    return report
