"""Pydantic schemas for Point-of-Sale (POS) Integration."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PosIntegrationCreate(BaseModel):
    provider: str = Field(..., description="POS Provider: MOCK_SQUARE, SQUARE, CLOVER, GENERIC_REST")
    integration_name: str = Field(..., min_length=2, max_length=100)
    api_key: Optional[str] = Field(None, description="Optional provider API key; hashed on server, never stored in plain text")


class PosIntegrationResponse(BaseModel):
    id: str
    tenant_id: str
    provider: str
    integration_name: str
    webhook_slug: str
    webhook_url: str
    webhook_signing_secret: Optional[str] = Field(
        None, description="Returned only once upon initial creation. Must be saved securely by client."
    )
    is_active: bool
    last_sync_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PosSyncRequest(BaseModel):
    since: Optional[datetime] = Field(None, description="Incremental sync filter timestamp")
    cursor: Optional[str] = Field(None, description="Pagination cursor for batched sync")


class PosSyncResponse(BaseModel):
    integration_id: str
    provider: str
    status: str
    synced_items_count: int = 0
    adjusted_transactions_count: int = 0
    errors: List[str] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    audit_summary: str


class PosWebhookLineItem(BaseModel):
    sku: Optional[str] = None
    barcode: Optional[str] = None
    name: Optional[str] = None
    quantity: Decimal = Field(..., gt=0, description="Quantity sold/deducted")
    unit_price: Optional[Decimal] = None
    unit: Optional[str] = None


class PosWebhookPayload(BaseModel):
    event_type: str = Field(..., description="Event type, e.g. order.completed, inventory.adjustment")
    order_id: str = Field(..., min_length=1, description="External unique order/transaction identifier")
    timestamp: Optional[datetime] = None
    line_items: List[PosWebhookLineItem] = Field(default_factory=list)


class PosWebhookResponse(BaseModel):
    success: bool
    event_type: str
    order_id: str
    items_adjusted: int
    message: str
