"""Standard Response Envelopes and Common Schemas."""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    issue: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Optional[List[ErrorDetail]] = None
    request_id: Optional[str] = None


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: ErrorBody


class SuccessEnvelope(BaseModel, Generic[DataT]):
    success: bool = True
    data: DataT


class PaginationMeta(BaseModel):
    page: int = Field(ge=1)
    size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: List[DataT]
    pagination: PaginationMeta
