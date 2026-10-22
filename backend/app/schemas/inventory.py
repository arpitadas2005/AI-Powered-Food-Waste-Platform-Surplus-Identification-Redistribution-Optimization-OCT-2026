"""Inventory and Stock Ledger Pydantic Schemas."""

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.models.inventory import InventoryStatus, ItemUnit
from backend.app.models.category import StorageRequirement
from backend.app.models.transaction import TransactionType, ReferenceType


class CategorySummary(BaseModel):
    id: str
    name: str
    slug: str
    perishability_tier: str
    recommended_storage: str

    model_config = {"from_attributes": True}


class InventoryItemBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Item name")
    category_id: str = Field(..., description="Food taxonomy category UUID")
    sku: Optional[str] = Field(None, max_length=100)
    barcode: Optional[str] = Field(None, max_length=100)
    unit: str = Field(default=ItemUnit.UNITS.value)
    cost_per_unit: float = Field(default=0.0, ge=0.0)
    selling_price: Optional[float] = Field(default=None, ge=0.0)
    purchase_date: date
    expiry_date: date
    batch_number: Optional[str] = Field(None, max_length=100)
    storage_requirement: str = Field(default=StorageRequirement.AMBIENT.value)
    storage_location: Optional[str] = Field(None, max_length=100)

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: str) -> str:
        valid_units = {u.value for u in ItemUnit}
        if v.lower() not in valid_units:
            raise ValueError(
                f"Invalid unit '{v}'. Must be one of: {', '.join(sorted(valid_units))}"
            )
        return v.lower()

    @field_validator("storage_requirement")
    @classmethod
    def validate_storage(cls, v: str) -> str:
        valid_storage = {s.value for s in StorageRequirement}
        if v.upper() not in valid_storage:
            raise ValueError(
                f"Invalid storage requirement '{v}'. Must be one of: {', '.join(sorted(valid_storage))}"
            )
        return v.upper()

    @model_validator(mode="after")
    def validate_date_chronology(self) -> "InventoryItemBase":
        if self.expiry_date < self.purchase_date:
            raise ValueError("expiry_date must be greater than or equal to purchase_date")
        return self


class InventoryItemCreate(InventoryItemBase):
    initial_quantity: float = Field(
        default=0.0, ge=0.0, description="Starting physical stock count"
    )


class InventoryItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    category_id: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=100)
    barcode: Optional[str] = Field(None, max_length=100)
    cost_per_unit: Optional[float] = Field(None, ge=0.0)
    selling_price: Optional[float] = Field(None, ge=0.0)
    expiry_date: Optional[date] = None
    batch_number: Optional[str] = None
    storage_requirement: Optional[str] = None
    storage_location: Optional[str] = None
    status: Optional[str] = None

    @field_validator("storage_requirement")
    @classmethod
    def validate_storage_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid_storage = {s.value for s in StorageRequirement}
            if v.upper() not in valid_storage:
                raise ValueError(f"Invalid storage requirement '{v}'")
            return v.upper()
        return v


class InventoryItemResponse(BaseModel):
    id: str
    tenant_id: str
    category_id: str
    category: Optional[CategorySummary] = None
    name: str
    sku: Optional[str] = None
    barcode: Optional[str] = None
    current_quantity: float
    unit: str
    cost_per_unit: float
    selling_price: Optional[float] = None
    purchase_date: date
    expiry_date: date
    days_to_expiry: float
    batch_number: Optional[str] = None
    storage_requirement: str
    storage_location: Optional[str] = None
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StockAdjustmentRequest(BaseModel):
    quantity_delta: float = Field(..., description="Signed adjustment: positive to add, negative to deduct")
    adjustment_type: str = Field(
        default=TransactionType.MANUAL_ADJUSTMENT.value,
        description="Transaction type category",
    )
    reason: str = Field(..., min_length=3, max_length=255, description="Operational justification")
    reference_type: Optional[str] = Field(None, max_length=50)
    reference_id: Optional[str] = Field(None, max_length=100)
    idempotency_key: Optional[str] = Field(
        None, max_length=100, description="Client idempotency key to prevent duplicate decrements"
    )

    @field_validator("quantity_delta")
    @classmethod
    def validate_non_zero(cls, v: float) -> float:
        if v == 0.0:
            raise ValueError("quantity_delta must be a non-zero number")
        return v

    @field_validator("adjustment_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = {t.value for t in TransactionType}
        if v.upper() not in valid_types:
            raise ValueError(f"Invalid adjustment_type '{v}'. Allowed: {', '.join(sorted(valid_types))}")
        return v.upper()


class StockTransactionResponse(BaseModel):
    id: str
    tenant_id: str
    item_id: str
    transaction_type: str
    quantity_change: float
    quantity_before: float
    quantity_after: float
    reason: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
