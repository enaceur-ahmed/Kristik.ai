"""
Pydantic v2 request/response schemas.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


# --------------------------------------------------------------------------- #
#  Dataset                                                                     #
# --------------------------------------------------------------------------- #
class DatasetBase(BaseModel):
    name: str
    original_filename: str
    file_type: str


class DatasetRead(DatasetBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_size_bytes: int
    status: str
    row_count: Optional[int]
    column_count: Optional[int]
    created_at: datetime
    updated_at: datetime
    workflow_progress: int = 0   # 0-6: index of the active workflow step


class DatasetList(BaseModel):
    items: list[DatasetRead]
    total: int


# --------------------------------------------------------------------------- #
#  Profile                                                                     #
# --------------------------------------------------------------------------- #
class DataProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    profile_json: dict[str, Any]
    created_at: datetime


# --------------------------------------------------------------------------- #
#  Quality                                                                     #
# --------------------------------------------------------------------------- #
class QualityReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    quality_score: float
    issues_json: list[dict[str, Any]]
    score_breakdown_json: Optional[dict[str, Any]]
    created_at: datetime


# --------------------------------------------------------------------------- #
#  Recommendation                                                              #
# --------------------------------------------------------------------------- #
class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    issue: str
    column_name: Optional[str]
    severity: str
    action: str
    strategy: Optional[str]
    reason: Optional[str]
    expected_impact: Optional[str]
    status: str
    critic_review_json: Optional[dict[str, Any]]
    created_at: datetime


class RecommendationAction(BaseModel):
    action: str   # "apply" | "reject"


class RecommendationGeneration(BaseModel):
    """Response of POST /api/datasets/{id}/recommendations."""
    recommendations: list[RecommendationRead]
    llm_fallback: bool
    llm_error: Optional[str] = None
    provider: str
    model: Optional[str] = None
    demo_mode: bool


# --------------------------------------------------------------------------- #
#  Pipeline                                                                    #
# --------------------------------------------------------------------------- #
class PipelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    name: str
    steps_json: list[dict[str, Any]]
    status: str
    generated_code: Optional[str]
    execution_time_s: Optional[float]
    created_at: datetime
    executed_at: Optional[datetime]


# --------------------------------------------------------------------------- #
#  Validation                                                                  #
# --------------------------------------------------------------------------- #
class ValidationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    pipeline_id: Optional[str]
    before_json: dict[str, Any]
    after_json: dict[str, Any]
    checks_json: list[dict[str, Any]]
    overall_status: str
    created_at: datetime


# --------------------------------------------------------------------------- #
#  Execution Log                                                               #
# --------------------------------------------------------------------------- #
class ExecutionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    level: str
    message: str
    created_at: datetime


# --------------------------------------------------------------------------- #
#  Dashboard                                                                   #
# --------------------------------------------------------------------------- #
class DashboardStats(BaseModel):
    total_datasets: int
    latest_analysis: Optional[str]
    average_quality_score: Optional[float]
    total_issues_detected: int
    recent_pipelines: int
