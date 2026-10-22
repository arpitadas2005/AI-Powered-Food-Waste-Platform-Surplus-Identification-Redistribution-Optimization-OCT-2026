"""
Alerts & Expiry Evaluation API Router.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    get_current_tenant_context,
    require_roles,
)
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.alert import ExpiryAlertHistory, TenantAlertConfig
from backend.app.models.inventory import InventoryItem, InventoryStatus
from backend.app.models.user import UserRole
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.expiry import (
    AcknowledgeAlertRequest,
    ExpiryAlertHistoryResponse,
    ExpiryEvaluationResponse,
    TenantAlertConfigSchema,
    TenantAlertConfigUpdate,
)
from backend.app.services.expiry_service import (
    acknowledge_alert,
    evaluate_tenant_inventory,
    get_or_create_alert_config,
)

router = APIRouter(tags=["alerts-and-expiry"])


@router.post(
    "/inventory/expiry/evaluate",
    response_model=SuccessEnvelope[ExpiryEvaluationResponse],
)
def trigger_expiry_evaluation(
    dry_run: bool = Query(False, description="If true, preview results without committing changes"),
    context: TenantContext = Depends(require_roles([UserRole.BUSINESS_OWNER.value, UserRole.INVENTORY_STAFF.value])),
    db: Session = Depends(get_db),
):
    """
    On-demand execution of the tenant expiry classification engine.
    Calculates time remaining, flags items, updates inventory status, and generates alerts.
    """
    try:
        response = evaluate_tenant_inventory(
            db=db,
            tenant_id=context.tenant_id,
            dry_run=dry_run,
        )
        return SuccessEnvelope(data=response)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/inventory/expiring",
    response_model=SuccessEnvelope[ExpiryEvaluationResponse],
)
def get_expiring_inventory(
    status: Optional[str] = Query(None, description="Filter by status: CRITICAL, EXPIRING_SOON, EXPIRED, ALL_AT_RISK"),
    days_threshold: Optional[float] = Query(None, description="Optional custom threshold cutoff in days"),
    category_id: Optional[str] = Query(None, description="Filter by food category ID"),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Query items approaching expiry segmented by severity thresholds with summary totals.
    Executes a dry-run evaluation to return up-to-the-minute status calculations.
    """
    response = evaluate_tenant_inventory(
        db=db,
        tenant_id=context.tenant_id,
        dry_run=True,
    )

    filtered_items = response.items

    if category_id:
        # Resolve category ID from items
        item_objs = {i.id: i.category_id for i in db.query(InventoryItem).filter(InventoryItem.tenant_id == context.tenant_id).all()}
        filtered_items = [i for i in filtered_items if item_objs.get(i.item_id) == category_id]

    if days_threshold is not None:
        filtered_items = [i for i in filtered_items if i.days_remaining <= days_threshold]

    if status:
        stat_upper = status.upper()
        if stat_upper == "ALL_AT_RISK":
            filtered_items = [i for i in filtered_items if i.alert_level in {"NOTICE", "WARNING", "CRITICAL", "EXPIRED"}]
        elif stat_upper in {"CRITICAL", "WARNING", "NOTICE", "EXPIRED", "FRESH"}:
            filtered_items = [i for i in filtered_items if i.alert_level == stat_upper]
        elif stat_upper == "EXPIRING_SOON":
            filtered_items = [i for i in filtered_items if i.alert_level in {"NOTICE", "WARNING", "CRITICAL"}]

    response.items = filtered_items
    return SuccessEnvelope(data=response)


@router.get(
    "/alerts/config",
    response_model=SuccessEnvelope[TenantAlertConfigSchema],
)
def get_alert_configuration(
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieve tenant expiry alert threshold configuration."""
    config = get_or_create_alert_config(db, context.tenant_id)
    return SuccessEnvelope(data=TenantAlertConfigSchema.model_validate(config))


@router.put(
    "/alerts/config",
    response_model=SuccessEnvelope[TenantAlertConfigSchema],
)
def update_alert_configuration(
    payload: TenantAlertConfigUpdate,
    context: TenantContext = Depends(require_roles([UserRole.BUSINESS_OWNER.value])),
    db: Session = Depends(get_db),
):
    """Update tenant expiry alert threshold configuration."""
    config = get_or_create_alert_config(db, context.tenant_id)

    # Validate relative threshold order if updating thresholds
    crit_hours = payload.critical_threshold_hours or config.critical_threshold_hours
    warn_days = payload.warning_threshold_days or config.warning_threshold_days
    notice_days = payload.notice_threshold_days or config.notice_threshold_days

    if (crit_hours / 24.0) >= warn_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="critical_threshold_hours must represent fewer days than warning_threshold_days",
        )
    if warn_days >= notice_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="warning_threshold_days must be strictly less than notice_threshold_days",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)
    return SuccessEnvelope(data=TenantAlertConfigSchema.model_validate(config))


@router.get(
    "/alerts/history",
    response_model=SuccessEnvelope[List[ExpiryAlertHistoryResponse]],
)
def list_alert_history(
    alert_level: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """List historical alert notifications for this tenant."""
    query = (
        select(ExpiryAlertHistory, InventoryItem.name.label("item_name"))
        .join(InventoryItem, ExpiryAlertHistory.item_id == InventoryItem.id)
        .where(ExpiryAlertHistory.tenant_id == context.tenant_id)
    )

    if alert_level:
        query = query.where(ExpiryAlertHistory.alert_level == alert_level.upper())
    if acknowledged is not None:
        query = query.where(ExpiryAlertHistory.acknowledged == acknowledged)

    query = query.order_by(desc(ExpiryAlertHistory.created_at)).limit(limit)
    rows = db.execute(query).all()

    results = []
    for alert, item_name in rows:
        results.append(
            ExpiryAlertHistoryResponse(
                id=alert.id,
                tenant_id=alert.tenant_id,
                item_id=alert.item_id,
                item_name=item_name,
                alert_level=alert.alert_level,
                days_remaining=float(alert.days_remaining),
                acknowledged=alert.acknowledged,
                acknowledged_by_user_id=alert.acknowledged_by_user_id,
                acknowledged_at=alert.acknowledged_at,
                action_taken=alert.action_taken,
                created_at=alert.created_at,
            )
        )

    return SuccessEnvelope(data=results)


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=SuccessEnvelope[ExpiryAlertHistoryResponse],
)
def acknowledge_expiry_alert(
    alert_id: str,
    payload: AcknowledgeAlertRequest,
    context: TenantContext = Depends(require_roles([UserRole.BUSINESS_OWNER.value, UserRole.INVENTORY_STAFF.value])),
    db: Session = Depends(get_db),
):
    """Mark an alert as acknowledged with an optional operational action taken."""
    try:
        alert = acknowledge_alert(
            db=db,
            tenant_id=context.tenant_id,
            alert_id=alert_id,
            user_id=context.user_id,
            action_taken=payload.action_taken,
        )
        item = db.query(InventoryItem).filter(InventoryItem.id == alert.item_id).first()
        return SuccessEnvelope(
            data=ExpiryAlertHistoryResponse(
                id=alert.id,
                tenant_id=alert.tenant_id,
                item_id=alert.item_id,
                item_name=item.name if item else None,
                alert_level=alert.alert_level,
                days_remaining=float(alert.days_remaining),
                acknowledged=alert.acknowledged,
                acknowledged_by_user_id=alert.acknowledged_by_user_id,
                acknowledged_at=alert.acknowledged_at,
                action_taken=alert.action_taken,
                created_at=alert.created_at,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
