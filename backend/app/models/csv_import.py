"""CSV Bulk Ingestion Tracker & Row Error Models."""

from datetime import datetime
from enum import Enum
from typing import List, TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TenantScopedMixin, generate_uuid, utc_now

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant
    from backend.app.models.user import User


class CsvImportStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    COMMITTING = "COMMITTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DRY_RUN_PASSED = "DRY_RUN_PASSED"
    DRY_RUN_FAILED = "DRY_RUN_FAILED"


class CsvImportJob(Base, TenantScopedMixin):
    """
    Tracks inventory batch import jobs and records processing summaries.
    """
    __tablename__ = "csv_import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_partial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    user: Mapped["User"] = relationship("User")
    errors: Mapped[List["CsvImportRowError"]] = relationship(
        "CsvImportRowError", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_csv_jobs_tenant_started", "tenant_id", "started_at"),
    )


class CsvImportRowError(Base, TenantScopedMixin):
    """
    Detailed row-level validation errors encountered during CSV import.
    """
    __tablename__ = "csv_import_row_errors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("csv_import_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_row_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invalid_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    # Relationships
    job: Mapped["CsvImportJob"] = relationship("CsvImportJob", back_populates="errors")

    __table_args__ = (
        Index("idx_csv_errors_job_row", "job_id", "row_number"),
    )
