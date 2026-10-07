"""
ORM models for datasets, analyses, pipelines, and related entities.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime,
    ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    """Return current UTC time as a timezone-aware datetime (Python 3.11+ compatible)."""
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    file_type = Column(String, nullable=False)   # csv | xlsx
    status = Column(String, default="uploaded")  # uploaded|profiling|profiled|error
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    profile = relationship("DataProfile", back_populates="dataset", uselist=False,
                           cascade="all, delete-orphan")
    quality_report = relationship("QualityReport", back_populates="dataset", uselist=False,
                                  cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="dataset",
                                   cascade="all, delete-orphan")
    pipelines = relationship("Pipeline", back_populates="dataset",
                             cascade="all, delete-orphan")
    validation_results = relationship("ValidationResult", back_populates="dataset",
                                      cascade="all, delete-orphan")
    execution_logs = relationship("ExecutionLog", back_populates="dataset",
                                  cascade="all, delete-orphan")

    @property
    def workflow_progress(self) -> int:
        """
        Index (0-6) of the active workflow step:
        0 Upload, 1 Profile, 2 Quality, 3 AI Recs, 4 Pipeline,
        5 Validate, 6 Analytics.

        Derived from persisted artefacts so the UI can advance past
        the "Quality" step (previously only ds.status was mapped).
        """
        if self.status == "profiling":
            return 1
        progress = 0
        if self.profile is not None:
            progress = 2       # Quality is next
        if self.quality_report is not None:
            progress = 3       # AI Recs next
        if self.recommendations:
            progress = 4       # Pipeline next
        if self.pipelines:
            progress = 5       # Validate next
        if self.validation_results:
            progress = 6       # Analytics next
        return progress


class DataProfile(Base):
    __tablename__ = "data_profiles"

    id = Column(String, primary_key=True, default=_uuid)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    profile_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    dataset = relationship("Dataset", back_populates="profile")


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id = Column(String, primary_key=True, default=_uuid)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    quality_score = Column(Float, nullable=False)
    issues_json = Column(JSON, nullable=False)
    score_breakdown_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    dataset = relationship("Dataset", back_populates="quality_report")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(String, primary_key=True, default=_uuid)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    issue = Column(String, nullable=False)
    column_name = Column(String, nullable=True)
    severity = Column(String, nullable=False)   # low | medium | high | critical
    action = Column(String, nullable=False)
    strategy = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    expected_impact = Column(Text, nullable=True)
    status = Column(String, default="pending")   # pending | applied | rejected
    critic_review_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    dataset = relationship("Dataset", back_populates="recommendations")


class Pipeline(Base):
    __tablename__ = "pipelines"

    id = Column(String, primary_key=True, default=_uuid)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    name = Column(String, nullable=False)
    steps_json = Column(JSON, nullable=False)
    status = Column(String, default="created")  # created|running|completed|failed
    generated_code = Column(Text, nullable=True)
    execution_time_s = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    executed_at = Column(DateTime(timezone=True), nullable=True)

    dataset = relationship("Dataset", back_populates="pipelines")


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id = Column(String, primary_key=True, default=_uuid)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    pipeline_id = Column(String, ForeignKey("pipelines.id"), nullable=True)
    before_json = Column(JSON, nullable=False)
    after_json = Column(JSON, nullable=False)
    checks_json = Column(JSON, nullable=False)
    overall_status = Column(String, nullable=False)   # PASS | WARNING | FAILED
    created_at = Column(DateTime(timezone=True), default=_now)

    dataset = relationship("Dataset", back_populates="validation_results")


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(String, primary_key=True, default=_uuid)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    level = Column(String, default="INFO")        # INFO | WARNING | ERROR
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    dataset = relationship("Dataset", back_populates="execution_logs")
