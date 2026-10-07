"""
Dataset API routes — upload, list, retrieve, delete, preview.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging_config import get_logger
from app.models.dataset import Dataset, ExecutionLog
from app.schemas.dataset import DatasetList, DatasetRead, DashboardStats

router = APIRouter(prefix="/api/datasets", tags=["datasets"])
logger = get_logger(__name__)

ALLOWED_TYPES = {"csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
MAX_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
CHUNK_SIZE = 1024 * 1024  # 1 MB — upload is streamed in chunks


def _log(db: Session, dataset_id: str, message: str, level: str = "INFO"):
    entry = ExecutionLog(dataset_id=dataset_id, message=message, level=level)
    db.add(entry)
    db.commit()


def _remove_quietly(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@router.post("/upload", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a CSV or XLSX dataset and trigger profiling."""
    # Validate extension
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '.{ext}'. Use CSV or XLSX.")

    # Stream to disk in chunks, enforcing the size limit while reading
    # (never buffers the whole file in memory)
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = str(uuid.uuid4())
    safe_name = f"{dataset_id}_{filename}"
    file_path = upload_dir / safe_name

    size = 0
    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
                    )
                f.write(chunk)
    except HTTPException:
        _remove_quietly(file_path)
        raise

    if size == 0:
        _remove_quietly(file_path)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Persist metadata
    dataset = Dataset(
        id=dataset_id,
        name=filename.rsplit(".", 1)[0],
        original_filename=filename,
        file_path=str(file_path),
        file_size_bytes=size,
        file_type=ext,
        status="uploaded",
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    _log(db, dataset_id, f"Dataset '{filename}' uploaded ({size:,} bytes).")

    return dataset


@router.get("", response_model=DatasetList)
def list_datasets(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """List all datasets."""
    items = db.query(Dataset).order_by(Dataset.created_at.desc()).offset(skip).limit(limit).all()
    total = db.query(Dataset).count()
    return DatasetList(items=items, total=total)


@router.get("/dashboard", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    """Aggregate dashboard statistics."""
    from app.models.dataset import QualityReport, Pipeline
    from sqlalchemy import func

    total_datasets = db.query(Dataset).count()

    latest = db.query(Dataset).order_by(Dataset.created_at.desc()).first()
    latest_analysis = str(latest.created_at) if latest else None

    avg_score_row = db.query(func.avg(QualityReport.quality_score)).scalar()
    avg_score = round(float(avg_score_row), 1) if avg_score_row else None

    total_issues = 0
    for qr in db.query(QualityReport).all():
        total_issues += len(qr.issues_json or [])

    recent_pipelines = db.query(Pipeline).count()

    return DashboardStats(
        total_datasets=total_datasets,
        latest_analysis=latest_analysis,
        average_quality_score=avg_score,
        total_issues_detected=total_issues,
        recent_pipelines=recent_pipelines,
    )


@router.get("/{dataset_id}", response_model=DatasetRead)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return ds


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    # Remove file
    try:
        os.remove(ds.file_path)
    except FileNotFoundError:
        pass
    db.delete(ds)
    db.commit()
