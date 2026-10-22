"""CSV Bulk Ingestion and Template Download Endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_tenant_context, require_roles
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.csv_import import CsvImportJob
from backend.app.models.user import UserRole
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.csv_import import (
    CsvImportResponse,
    CsvImportRowErrorSchema,
    CsvImportSummary,
)
from backend.app.services.csv_service import (
    CsvIngestionError,
    FileSizeLimitExceededError,
    MalformedEncodingError,
    MissingHeadersError,
    RowLimitExceededError,
    generate_template_csv,
    process_csv_import,
)

router = APIRouter(prefix="/inventory/bulk-import", tags=["import-export"])


@router.get("/template")
def download_csv_template():
    """
    Downloads standard CSV inventory import template with column headers and sample data.
    """
    csv_content = generate_template_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="inventory_import_template.csv"',
        },
    )


@router.post(
    "/csv",
    response_model=SuccessEnvelope[CsvImportResponse],
    dependencies=[
        Depends(
            require_roles(
                [UserRole.BUSINESS_OWNER.value, UserRole.STORE_MANAGER.value]
            )
        )
    ],
)
async def upload_csv_inventory(
    file: UploadFile = File(..., description="CSV file to import"),
    dry_run: bool = Query(True, description="Preview validation without writing to database"),
    allow_partial: bool = Query(False, description="Commit valid rows even if some fail"),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Upload and process a bulk CSV inventory import file.
    Supports dry-run preview and configurable all-or-nothing or partial commit policies.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a .csv file",
        )

    file_bytes = await file.read()

    try:
        result = process_csv_import(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            filename=file.filename,
            file_bytes=file_bytes,
            dry_run=dry_run,
            allow_partial=allow_partial,
        )
        return SuccessEnvelope(data=result)
    except FileSizeLimitExceededError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except (MalformedEncodingError, MissingHeadersError, RowLimitExceededError, CsvIngestionError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.get(
    "/jobs/{job_id}",
    response_model=SuccessEnvelope[CsvImportResponse],
    dependencies=[
        Depends(
            require_roles(
                [UserRole.BUSINESS_OWNER.value, UserRole.STORE_MANAGER.value]
            )
        )
    ],
)
def get_import_job(
    job_id: str,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Retrieve past import job execution status and granular row errors.
    """
    job = db.execute(
        select(CsvImportJob).where(
            CsvImportJob.id == job_id,
            CsvImportJob.tenant_id == context.tenant_id,
        )
    ).scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found",
        )

    errors = [
        CsvImportRowErrorSchema(
            row_number=err.row_number,
            field_name=err.field_name,
            invalid_value=err.invalid_value,
            error_code=err.error_code,
            error_message=err.error_message,
        )
        for err in job.errors
    ]

    return SuccessEnvelope(
        data=CsvImportResponse(
            job_id=job.id,
            filename=job.filename,
            file_size_bytes=job.file_size_bytes,
            dry_run=job.dry_run,
            allow_partial=job.allow_partial,
            status=job.status,
            summary=CsvImportSummary(
                total_rows=job.total_rows,
                accepted_rows=job.successful_rows,
                rejected_rows=job.failed_rows,
                skipped_rows=0,
                duplicate_rows=0,
            ),
            errors=errors,
        )
    )
