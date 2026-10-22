"""Schemas package exports."""

from backend.app.schemas.common import (
    ErrorBody,
    ErrorDetail,
    ErrorEnvelope,
    PaginatedResponse,
    PaginationMeta,
    SuccessEnvelope,
)
from backend.app.schemas.inventory import (
    CategorySummary,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    StockAdjustmentRequest,
    StockTransactionResponse,
)

__all__ = [
    "ErrorBody",
    "ErrorDetail",
    "ErrorEnvelope",
    "PaginatedResponse",
    "PaginationMeta",
    "SuccessEnvelope",
    "CategorySummary",
    "InventoryItemCreate",
    "InventoryItemResponse",
    "InventoryItemUpdate",
    "StockAdjustmentRequest",
    "StockTransactionResponse",
]
