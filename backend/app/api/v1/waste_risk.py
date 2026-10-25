"""
Waste-Risk Assessment & Smart Reorders REST API Endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_tenant_context, require_roles
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.inventory import InventoryItem
from backend.app.models.user import UserRole
from backend.app.ml.waste_risk_service import WasteRiskService
from backend.app.ml.smart_reorder_service import SmartReorderService
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.forecast import (
    SmartReorderItemResponse,
    WasteRiskAlertResponse,
    WasteRiskEvaluateRequest,
)

router = APIRouter(prefix="/waste-risk", tags=["waste-risk"])


@router.post("/evaluate")
def evaluate_waste_risk(
    payload: WasteRiskEvaluateRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Evaluates real-time waste risk for an inventory item by ID, SKU, or custom payload.
    """
    service = WasteRiskService()

    if payload.item_id:
        item = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.tenant_id == ctx.tenant_id,
                InventoryItem.id == payload.item_id,
                InventoryItem.is_active == True,
            )
            .first()
        )
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item '{payload.item_id}' not found for tenant.",
            )
        assessment = service.evaluate_item_risk(item, db, persist=True)
        return {
            "item_id": item.id,
            "sku": item.sku,
            "product_name": item.name,
            "unit": item.unit,
            "current_stock": assessment.current_stock,
            "days_to_expiry": assessment.days_to_expiry,
            "predicted_demand_to_expiry": assessment.predicted_demand_to_expiry,
            "expected_surplus": assessment.expected_surplus_units,
            "surplus_ratio": assessment.surplus_ratio,
            "value_at_risk": assessment.value_at_risk,
            "risk_tier": assessment.risk_tier,
            "recommended_action": assessment.recommended_action,
            "model_name": assessment.model_name,
            "assessed_at": str(assessment.assessed_at),
        }

    # Manual evaluation without DB item record
    days_to_exp = payload.days_to_expiry
    avail_stock = payload.current_stock
    sku_val = payload.sku or payload.product_name or "GENERIC-ITEM"
    pred_demand = service.inference_service.predict_demand_over_window(sku=sku_val, days_ahead=days_to_exp)

    expected_surplus = max(0.0, avail_stock - pred_demand)
    surplus_ratio = round(expected_surplus / avail_stock, 3) if avail_stock > 0 else 0.0
    var = round(expected_surplus * payload.unit_cost, 2)

    from backend.app.ml.risk_rules import classify_waste_risk
    tier, action = classify_waste_risk(days_to_exp, avail_stock, expected_surplus, surplus_ratio)

    return {
        "item_id": "manual-adhoc",
        "sku": payload.sku,
        "product_name": payload.product_name,
        "unit": payload.unit,
        "current_stock": round(avail_stock, 2),
        "days_to_expiry": round(days_to_exp, 1),
        "predicted_demand_to_expiry": round(pred_demand, 2),
        "expected_surplus": round(expected_surplus, 2),
        "surplus_ratio": surplus_ratio,
        "value_at_risk": var,
        "risk_tier": tier,
        "recommended_action": action,
        "model_name": "InferenceEngine",
    }


@router.get("/alerts", response_model=List[WasteRiskAlertResponse])
def get_waste_risk_alerts(
    min_tier: str = Query(default="HIGH", pattern="^(MEDIUM|HIGH|CRITICAL)$"),
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Returns active perishable inventory items for the authenticated tenant
    that exceed the specified risk severity threshold.
    """
    service = WasteRiskService()
    alerts = service.list_active_risk_alerts(tenant_id=ctx.tenant_id, db=db, min_tier=min_tier)
    return [WasteRiskAlertResponse(**a) for a in alerts]


@router.get("/reorders", response_model=List[SmartReorderItemResponse])
def get_smart_reorder_recommendations(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Returns dynamic reorder recommendations based on lead-time demand,
    safety stock, storage constraints, and surplus risk guards.
    """
    service = SmartReorderService()
    reorders = service.list_active_reorder_recommendations(tenant_id=ctx.tenant_id, db=db)
    return [SmartReorderItemResponse(**r) for r in reorders]


@router.post("/batch-evaluate")
def run_batch_evaluation(
    ctx: TenantContext = Depends(require_roles([UserRole.STORE_MANAGER, UserRole.BUSINESS_OWNER, UserRole.SYSTEM_ADMIN])),
    db: Session = Depends(get_db),
):
    """
    Triggers batch waste risk assessment and reorder recommendation generation
    across all active inventory for the authenticated tenant.
    """
    from backend.app.ml.batch_job import BatchPredictionJob
    job = BatchPredictionJob()
    summary = job.execute_tenant_batch(tenant_id=ctx.tenant_id, db=db)
    return SuccessEnvelope(
        message=f"Batch evaluation completed successfully for tenant {ctx.tenant_id}.",
        data=summary,
    )
