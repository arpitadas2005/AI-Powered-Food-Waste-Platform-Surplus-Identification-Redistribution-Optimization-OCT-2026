"""CSV Import Pydantic Schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CsvImportRowErrorSchema(BaseModel):
    row_number: int
    field_name: Optional[str] = None
    invalid_value: Optional[str] = None
    error_code: str
    error_message: str

    model_config = {"from_attributes": True}


class CsvImportSummary(BaseModel):
    total_rows: int = Field(ge=0)
    accepted_rows: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    skipped_rows: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)


class CsvImportResponse(BaseModel):
    job_id: str
    filename: str
    file_size_bytes: int
    dry_run: bool
    allow_partial: bool
    status: str
    summary: CsvImportSummary
    errors: List[CsvImportRowErrorSchema]
    sample_imported_items: Optional[List[Dict[str, Any]]] = None

    model_config = {"from_attributes": True}
