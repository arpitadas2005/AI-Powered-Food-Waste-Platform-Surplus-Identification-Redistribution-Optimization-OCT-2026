"""
Expiry Evaluation, Classification, and Alert Engine.

Implements:
1. Precise timezone-aware time-to-expiry calculation with local end-of-day anchor.
2. Multi-tier classification (FRESH, NOTICE, WARNING, CRITICAL, EXPIRED).
3. Critical food safety rule: Expired items are strictly ineligible for donation.
4. Intelligent deduplication to prevent alert fatigue on repeated runs.
5. Audit history tracking and scheduler telemetry diagnostics.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import os
from typing import Any, Dict, List, Optional, Tuple
import zoneinfo

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from backend.app.db.base import utc_now
from backend.app.models.alert import (
    AlertAction,
    AlertLevel,
    ExpiryAlertHistory,
    TenantAlertConfig,
)
from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus
from backend.app.models.tenant import Tenant
from backend.app.schemas.expiry import (
    ExpiryAlertHistoryResponse,
    ExpiryAlertItemSummary,
    ExpiryEvaluationResponse,
    ExpiryEvaluationSummary,
    ExpirySchedulerDiagnostics,
)


def get_tenant_zone(tenant_timezone: Optional[str]) -> zoneinfo.ZoneInfo:
    """Safely resolve ZoneInfo, falling back to UTC if invalid or missing."""
    if not tenant_timezone:
        return zoneinfo.ZoneInfo("UTC")
    try:
        return zoneinfo.ZoneInfo(tenant_timezone)
    except Exception:
        return zoneinfo.ZoneInfo("UTC")


def calculate_time_remaining(
    expiry_date: date,
    tenant_timezone: str,
    as_of: Optional[datetime] = None,
) -> Tuple[float, datetime]:
    """
    Calculate the fractional days remaining until expiry.
    
    Anchored at 23:59:59.999999 of the expiry date in the tenant's local timezone.
    Returns:
        (days_remaining: float, expiry_moment_local: datetime)
    """
    tz = get_tenant_zone(tenant_timezone)
    
    # End of calendar day in tenant's timezone
    expiry_moment = datetime.combine(
        expiry_date, time(23, 59, 59, 999999), tzinfo=tz
    )
    
    # Current evaluation moment normalized to tenant timezone
    if as_of:
        if as_of.tzinfo is None:
            current_moment = as_of.replace(tzinfo=tz)
        else:
            current_moment = as_of.astimezone(tz)
    else:
        current_moment = datetime.now(tz)

    delta = expiry_moment - current_moment
    days_remaining = delta.total_seconds() / 86400.0
    return days_remaining, expiry_moment


def classify_expiry_state(
    days_remaining: float,
    config: TenantAlertConfig,
) -> Tuple[str, str, bool]:
    """
    Classify an inventory item based on days remaining and tenant thresholds.
    
    Returns:
        (alert_level, recommended_action, donation_eligible)
        
    FOOD SAFETY CONTRACT:
    If days_remaining <= 0 (EXPIRED), donation_eligible is ALWAYS False.
    """
    crit_days = config.critical_threshold_hours / 24.0

    if days_remaining <= 0.0:
        return (
            AlertLevel.EXPIRED.value,
            "DISCARD_OR_COMPOST",
            False,  # STRICT: Expired food cannot be donated under any circumstance
        )
    elif days_remaining <= crit_days:
        action = (
            "EXPEDITE_DISPATCH_OR_DONATE"
            if config.auto_flag_for_donation
            else "DISCOUNT_50_PERCENT"
        )
        return (AlertLevel.CRITICAL.value, action, True)
    elif days_remaining <= float(config.warning_threshold_days):
        action = (
            "MARK_DOWN_OR_PREPARE_DONATION"
            if config.auto_flag_for_donation
            else "DISCOUNT_25_PERCENT"
        )
        return (AlertLevel.WARNING.value, action, True)
    elif days_remaining <= float(config.notice_threshold_days):
        return (AlertLevel.NOTICE.value, "MONITOR_AND_ROTATE_FIFO", True)
    else:
        return ("FRESH", "STANDARD_STORAGE", False)


def get_or_create_alert_config(db: Session, tenant_id: str) -> TenantAlertConfig:
    """Retrieve tenant alert thresholds or create baseline defaults."""
    config = (
        db.query(TenantAlertConfig)
        .filter(TenantAlertConfig.tenant_id == tenant_id)
        .first()
    )
    if not config:
        config = TenantAlertConfig(
            tenant_id=tenant_id,
            critical_threshold_hours=24,
            warning_threshold_days=3,
            notice_threshold_days=7,
            auto_flag_for_donation=True,
            email_notifications_enabled=False,
            webhook_notification_url=None,
        )
        db.add(config)
        db.flush()
    return config


def check_alert_deduplication(
    db: Session,
    tenant_id: str,
    item_id: str,
    new_level: str,
    as_of: datetime,
) -> bool:
    """
    Determine if generating an alert would be a duplicate.
    
    Returns True if duplicate (SKIP alert creation).
    Returns False if alert should be created.
    """
    recent_alert = (
        db.query(ExpiryAlertHistory)
        .filter(
            ExpiryAlertHistory.tenant_id == tenant_id,
            ExpiryAlertHistory.item_id == item_id,
        )
        .order_by(desc(ExpiryAlertHistory.created_at))
        .first()
    )

    if not recent_alert:
        return False  # No prior alert, create it

    # If the alert has transitioned to a different level (e.g. WARNING -> CRITICAL or -> EXPIRED)
    if recent_alert.alert_level != new_level:
        return False

    # If same alert level is already acknowledged, do not alert again
    if recent_alert.acknowledged:
        return True

    # If unacknowledged but logged within the last 24 hours, suppress duplicate spam
    alert_time = recent_alert.created_at
    if alert_time.tzinfo is None:
        alert_time = alert_time.replace(tzinfo=timezone.utc)
    
    eval_time = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    time_since_last_alert = eval_time - alert_time

    if time_since_last_alert < timedelta(hours=24):
        return True  # Suppress duplicate alert within 24 hours

    return False


def get_scheduler_diagnostics() -> ExpirySchedulerDiagnostics:
    """
    Inspect deployment environment and report actual scheduler & notification health.
    Never claims alerts/workers are running if backing services are missing.
    """
    missing = []
    
    redis_url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL")
    if not redis_url:
        missing.append("Async Task Broker (REDIS_URL / CELERY_BROKER_URL not configured)")

    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        missing.append("Email Delivery Provider (SMTP_HOST / SENDGRID_API_KEY not configured)")

    webhook_url = os.getenv("GLOBAL_ALERT_WEBHOOK_URL")
    if not webhook_url:
        missing.append("Global Alert Webhook (GLOBAL_ALERT_WEBHOOK_URL not configured)")

    background_active = bool(redis_url and os.getenv("CELERY_WORKER_ACTIVE") == "true")

    rec = (
        "Operating in on-demand / cron CLI mode. For automated 24/7 background evaluation, "
        "configure an external task scheduler (e.g., Celery worker or Cloud Scheduler hitting "
        "POST /api/v1/inventory/expiry/evaluate)."
        if missing
        else "All background notification and scheduler services are fully configured."
    )

    return ExpirySchedulerDiagnostics(
        scheduler_mode="ON_DEMAND_AND_CRON",
        background_worker_active=background_active,
        missing_configurations=missing,
        recommendation=rec,
    )


def evaluate_tenant_inventory(
    db: Session,
    tenant_id: str,
    as_of: Optional[datetime] = None,
    dry_run: bool = False,
) -> ExpiryEvaluationResponse:
    """
    Execute full expiry evaluation for a single tenant's inventory items.
    
    1. Loads tenant and alert configuration.
    2. Queries all active items with stock > 0.
    3. Calculates days remaining with timezone precision.
    4. Categorizes into FRESH, NOTICE, WARNING, CRITICAL, EXPIRED.
    5. Deduplicates alerts against historical logs.
    6. Updates item status (EXPIRING_SOON / EXPIRED / ACTIVE).
    7. Respects dry-run flag.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise ValueError(f"Active tenant '{tenant_id}' not found")

    config = get_or_create_alert_config(db, tenant_id)
    tz = get_tenant_zone(tenant.timezone)
    eval_datetime = as_of or datetime.now(timezone.utc)

    # Active items in stock
    items = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.tenant_id == tenant_id,
            InventoryItem.is_active == True,
            InventoryItem.current_quantity > 0,
            InventoryItem.status.notin_([
                InventoryStatus.DEPLETED.value,
                InventoryStatus.DONATED.value,
                InventoryStatus.DISCARDED.value,
            ]),
        )
        .all()
    )

    # Pre-fetch categories for display names
    categories_map = {c.id: c.name for c in db.query(Category).all()}

    summary = ExpiryEvaluationSummary()
    item_results: List[ExpiryAlertItemSummary] = []

    for item in items:
        summary.total_evaluated += 1
        days_rem, expiry_moment = calculate_time_remaining(
            item.expiry_date, tenant.timezone, eval_datetime
        )
        level, action, donation_eligible = classify_expiry_state(days_rem, config)

        # Counter increments
        if level == AlertLevel.EXPIRED.value:
            summary.expired_count += 1
            summary.total_at_risk_value += Decimal(str(item.current_quantity)) * Decimal(str(item.cost_per_unit))
            if not dry_run:
                item.status = InventoryStatus.EXPIRED.value
        elif level == AlertLevel.CRITICAL.value:
            summary.critical_count += 1
            summary.total_at_risk_value += Decimal(str(item.current_quantity)) * Decimal(str(item.cost_per_unit))
            if not dry_run:
                item.status = InventoryStatus.EXPIRING_SOON.value
            if config.auto_flag_for_donation and donation_eligible:
                summary.items_flagged_for_donation += 1
        elif level == AlertLevel.WARNING.value:
            summary.warning_count += 1
            summary.total_at_risk_value += Decimal(str(item.current_quantity)) * Decimal(str(item.cost_per_unit))
            if not dry_run:
                item.status = InventoryStatus.EXPIRING_SOON.value
            if config.auto_flag_for_donation and donation_eligible:
                summary.items_flagged_for_donation += 1
        elif level == AlertLevel.NOTICE.value:
            summary.notice_count += 1
            if not dry_run:
                item.status = InventoryStatus.EXPIRING_SOON.value
        else:  # FRESH
            summary.fresh_count += 1
            if not dry_run and item.status == InventoryStatus.EXPIRING_SOON.value:
                item.status = InventoryStatus.ACTIVE.value

        # Alert logging and deduplication (only for non-fresh states)
        if level in {AlertLevel.NOTICE.value, AlertLevel.WARNING.value, AlertLevel.CRITICAL.value, AlertLevel.EXPIRED.value}:
            is_dup = check_alert_deduplication(db, tenant_id, item.id, level, eval_datetime)
            if is_dup:
                summary.alerts_skipped_dedup += 1
            else:
                summary.alerts_created += 1
                if not dry_run:
                    alert = ExpiryAlertHistory(
                        tenant_id=tenant_id,
                        item_id=item.id,
                        alert_level=level,
                        days_remaining=round(days_rem, 2),
                        acknowledged=False,
                        action_taken=action if level != AlertLevel.EXPIRED.value else AlertAction.DISCARDED.value,
                        created_at=eval_datetime,
                    )
                    db.add(alert)

        item_results.append(
            ExpiryAlertItemSummary(
                item_id=item.id,
                name=item.name,
                sku=item.sku,
                category_name=categories_map.get(item.category_id, "Unknown"),
                current_quantity=Decimal(str(item.current_quantity)),
                unit=item.unit,
                expiry_date=item.expiry_date,
                days_remaining=round(days_rem, 2),
                alert_level=level,
                recommended_action=action,
                donation_eligible=donation_eligible,
                status=item.status,
            )
        )

    if not dry_run:
        db.commit()

    return ExpiryEvaluationResponse(
        evaluated_at=eval_datetime,
        tenant_id=tenant_id,
        tenant_timezone=tenant.timezone,
        dry_run=dry_run,
        summary=summary,
        items=item_results,
        scheduler_diagnostics=get_scheduler_diagnostics(),
    )


def acknowledge_alert(
    db: Session,
    tenant_id: str,
    alert_id: str,
    user_id: str,
    action_taken: Optional[str] = None,
) -> ExpiryAlertHistory:
    """Mark an alert acknowledged by an authorized user."""
    alert = (
        db.query(ExpiryAlertHistory)
        .filter(
            ExpiryAlertHistory.id == alert_id,
            ExpiryAlertHistory.tenant_id == tenant_id,
        )
        .first()
    )
    if not alert:
        raise ValueError("Alert record not found")

    alert.acknowledged = True
    alert.acknowledged_by_user_id = user_id
    alert.acknowledged_at = utc_now()
    if action_taken:
        alert.action_taken = action_taken

    db.commit()
    db.refresh(alert)
    return alert
