"""
Milestone 2 — Phase 3: Forecast Output Contract & Downstream Schema Definitions.

Defines the exact interface contract connecting the ML Forecasting Engine (Phase 3)
to the downstream Waste-Risk Scoring and Surplus Redistribution Engine (Phase 4).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DailyForecastPoint(BaseModel):
    """Single daily point forecast with prediction intervals."""
    date: str = Field(..., description="Forecast date (YYYY-MM-DD)")
    predicted_sales: float = Field(..., ge=0.0, description="Point forecast in physical canonical units")
    lower_bound_80: float = Field(0.0, ge=0.0, description="80% prediction interval lower bound")
    upper_bound_80: float = Field(0.0, ge=0.0, description="80% prediction interval upper bound")


class SKUForecastResult(BaseModel):
    """Complete multi-horizon forecast output for a specific product SKU."""
    sku: str = Field(..., description="Unique product stock-keeping unit identifier")
    tenant_id: str = Field(..., description="Store tenant identifier")
    product_name: str = Field(..., description="Product display name")
    unit: str = Field(..., description="Platform canonical measurement unit")
    horizon_days: int = Field(..., description="Forecast horizon span (e.g. 7 days)")
    daily_forecasts: List[DailyForecastPoint] = Field(..., description="Sequence of daily point forecasts")
    predicted_7d_demand: float = Field(..., ge=0.0, description="Cumulative 7-day expected sales volume")
    model_name: str = Field(..., description="Identifier of the serving forecasting model")
    model_version: str = Field(..., description="Model release version (e.g. 2.0.0-phase3)")
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="ISO timestamp of generation")


class WasteRiskInputContract(BaseModel):
    """
    Contract required by the downstream Waste Risk and Surplus Redistribution Engine.
    Combines live physical inventory state with ML demand forecasts.
    """
    sku: str = Field(..., description="Product SKU")
    tenant_id: str = Field(..., description="Store tenant identifier")
    current_stock: float = Field(..., ge=0.0, description="Current physical shelf stock balance (I_t)")
    shelf_life_days: float = Field(..., ge=1.0, description="Expected total biological shelf life in days")
    days_to_expiry: float = Field(..., ge=0.0, description="Remaining days until batch expiration")
    unit_cost: float = Field(..., ge=0.0, description="Procurement unit cost ($)")
    selling_price: float = Field(..., ge=0.0, description="Current shelf selling price ($)")
    predicted_demand_to_expiry: float = Field(..., ge=0.0, description="Cumulative forecast demand across remaining expiry days")
    predicted_7d_demand: float = Field(..., ge=0.0, description="Cumulative 7-day forecast demand")
    lead_time_days: int = Field(default=2, ge=1, description="Supplier delivery lead time in days")


class WasteRiskOutputContract(BaseModel):
    """
    Proposed output contract produced by downstream risk engine in Phase 4.
    """
    sku: str = Field(...)
    tenant_id: str = Field(...)
    risk_level: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")
    expected_surplus_quantity: float = Field(..., ge=0.0, description="max(0, current_stock - predicted_demand)")
    surplus_ratio: float = Field(..., ge=0.0, le=1.0, description="surplus / current_stock")
    value_at_risk: float = Field(..., ge=0.0, description="expected_surplus * unit_cost")
    reorder_point: float = Field(..., ge=0.0, description="Statistical safety stock + lead-time demand")
    recommended_action: str = Field(..., description="NONE, DISCOUNT_MARKDOWN, DONATE_SURPLUS, REORDER_NOW")
