"""Pydantic schemas for Expiry Tracking, Classification, and Alerts."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TenantAlertConfigBase(BaseModel):
    critical_threshold_hours: int = Field(24, ge=1, le=168, description="Hours before expiry considered critical")
    warning_threshold_days: int = Field(3, ge=1, le=30, description="Days before expiry considered warning")
    notice_threshold_days: int = Field(7, ge=2, le=90, description="Days before expiry considered notice")
    auto_flag_for_donation: bool = Field(True, description="Automatically mark eligible expiring items for donation")
    email_notifications_enabled: bool = Field(False, description="Send email notifications on critical alerts")
    webhook_notification_url: Optional[str] = Field(None, max_length=500, description="Optional webhook for alerts")

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "TenantAlertConfigBase":
        crit_days = self.critical_threshold_hours / 24.0
        if crit_days >= self.warning_threshold_days:
            raise ValueError("critical_threshold_hours must represent fewer days than warning_threshold_days")
        if self.warning_threshold_days >= self.notice_threshold_days:
            raise ValueError("warning_threshold_days must be strictly less than notice_threshold_days")
        return self


class TenantAlertConfigUpdate(BaseModel):
    critical_threshold_hours: Optional[int] = Field(None, ge=1, le=168)
    warning_threshold_days: Optional[int] = Field(None, ge=1, le=30)
    notice_threshold_days: Optional[int] = Field(None, ge=2, le=90)
    auto_flag_for_donation: Optional[bool] = None
    email_notifications_enabled: Optional[bool] = None
    webhook_notification_url: Optional[str] = Field(None, max_length=500)


class TenantAlertConfigSchema(TenantAlertConfigBase):
    id: str
    tenant_id: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpiryAlertItemSummary(BaseModel):
    item_id: str
    name: str
    sku: Optional[str] = None
    category_name: str
    current_quantity: Decimal
    unit: str
    expiry_date: date
    days_remaining: float
    alert_level: str  # FRESH, NOTICE, WARNING, CRITICAL, EXPIRED
    recommended_action: str
    donation_eligible: bool
    status: str

    model_config = ConfigDict(from_attributes=True)


class ExpiryEvaluationSummary(BaseModel):
    total_evaluated: int = 0
    fresh_count: int = 0
    notice_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    expired_count: int = 0
    alerts_created: int = 0
    alerts_skipped_dedup: int = 0
    items_flagged_for_donation: int = 0
    total_at_risk_value: Decimal = Decimal("0.00")


class ExpirySchedulerDiagnostics(BaseModel):
    scheduler_mode: str = "ON_DEMAND_AND_CRON"
    background_worker_active: bool = False
    missing_configurations: List[str] = Field(default_factory=list)
    recommendation: str = ""


class ExpiryEvaluationResponse(BaseModel):
    evaluated_at: datetime
    tenant_id: str
    tenant_timezone: str
    dry_run: bool
    summary: ExpiryEvaluationSummary
    items: List[ExpiryAlertItemSummary]
    scheduler_diagnostics: ExpirySchedulerDiagnostics


class ExpiryAlertHistoryResponse(BaseModel):
    id: str
    tenant_id: str
    item_id: str
    item_name: Optional[str] = None
    alert_level: str
    days_remaining: float
    acknowledged: bool
    acknowledged_by_user_id: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    action_taken: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AcknowledgeAlertRequest(BaseModel):
    action_taken: Optional[str] = Field(None, max_length=50)
