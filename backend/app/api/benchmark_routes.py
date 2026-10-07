"""Benchmark API route."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.dataset import Dataset

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


@router.post("/{dataset_id}")
def run_benchmark(dataset_id: str, db: Session = Depends(get_db)):
    """Run benchmark comparing modes A, B, C on a dataset."""
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    try:
        from app.services.profiler import load_dataframe
        from app.agents.benchmark import run_benchmark as _run

        df = load_dataframe(ds.file_path, ds.file_type)
        results = _run(df)
        return results

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
