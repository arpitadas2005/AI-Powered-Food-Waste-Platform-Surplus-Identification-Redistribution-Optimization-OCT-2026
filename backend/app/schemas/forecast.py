"""
Pydantic Schemas for Forecasting, Waste-Risk Alerts, and Smart Reorders API.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DailyForecastItem(BaseModel):
    date: str
    predicted_sales: float
    lower_bound_80: float
    upper_bound_80: float


class SKUForecastResponse(BaseModel):
    sku: str
    tenant_id: str
    product_name: str
    unit: str
    horizon_days: int
    daily_forecasts: List[DailyForecastItem]
    predicted_7d_demand: float
    model_name: str
    model_version: str
    generated_at: str


class ForecastSummaryItem(BaseModel):
    sku: str
    product_name: str
    unit: str
    current_stock: float
    predicted_7d_demand: float
    daily_average: float


class ForecastSummaryResponse(BaseModel):
    tenant_id: str
    total_skus_tracked: int
    total_predicted_7d_volume: float
    forecasts: List[ForecastSummaryItem]
    generated_at: str


class WasteRiskEvaluateRequest(BaseModel):
    item_id: Optional[str] = None
    sku: Optional[str] = None
    product_name: Optional[str] = "Manual Item"
    current_stock: float = Field(..., ge=0.0)
    days_to_expiry: float = Field(..., ge=0.0)
    unit_cost: float = Field(..., ge=0.0)
    unit: str = "units"


class WasteRiskAlertResponse(BaseModel):
    item_id: str
    sku: Optional[str] = None
    product_name: str
    unit: str
    current_stock: float
    days_to_expiry: float
    predicted_demand_to_expiry: float
    expected_surplus: float
    surplus_ratio: float
    value_at_risk: float
    risk_tier: str
    recommended_action: str
    expiry_date: str


class SmartReorderItemResponse(BaseModel):
    item_id: str
    sku: Optional[str] = None
    product_name: str
    unit: str
    current_stock: float
    predicted_daily_demand: float
    reorder_point: float
    recommended_quantity: float
    lead_time_days: int
    safety_stock: float
    is_blocked_by_expiry_risk: bool
    status: str
    reason: str


class ModelHealthResponse(BaseModel):
    status: str
    is_using_fallback: bool
    models: Dict[str, Any]
    reference_skus_cached: int
    checked_at: str
