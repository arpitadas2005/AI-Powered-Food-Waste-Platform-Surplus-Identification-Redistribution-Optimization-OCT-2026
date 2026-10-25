"""
Forecasting REST API Endpoints.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_tenant_context
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.inventory import InventoryItem
from backend.app.ml.inference_service import get_inference_service
from backend.app.schemas.forecast import (
    DailyForecastItem,
    ForecastSummaryItem,
    ForecastSummaryResponse,
    ModelHealthResponse,
    SKUForecastResponse,
)

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("/health", response_model=ModelHealthResponse)
def get_forecast_model_health():
    """Returns inference engine readiness, loaded models, and fallback state."""
    inference_service = get_inference_service()
    return inference_service.get_health_status()


@router.get("/sku/{sku}", response_model=SKUForecastResponse)
def get_sku_forecast(
    sku: str,
    horizon_days: int = Query(default=7, ge=1, le=28),
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Returns multi-horizon demand forecast for a specific product SKU
    belonging to the authenticated tenant.
    """
    # Verify tenant ownership of SKU in inventory
    item = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.tenant_id == ctx.tenant_id,
            InventoryItem.sku == sku,
            InventoryItem.is_active == True,
        )
        .first()
    )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU '{sku}' not found in active inventory for tenant.",
        )

    inference_service = get_inference_service()
    result = inference_service.predict_daily_trajectory(
        sku=sku,
        horizon_days=horizon_days,
        tenant_id=ctx.tenant_id,
        product_name=item.name,
        unit=item.unit,
    )

    return SKUForecastResponse(
        sku=result.sku,
        tenant_id=result.tenant_id,
        product_name=result.product_name,
        unit=result.unit,
        horizon_days=result.horizon_days,
        daily_forecasts=[
            DailyForecastItem(
                date=p.date,
                predicted_sales=p.predicted_sales,
                lower_bound_80=p.lower_bound_80,
                upper_bound_80=p.upper_bound_80,
            )
            for p in result.daily_forecasts
        ],
        predicted_7d_demand=result.predicted_7d_demand,
        model_name=result.model_name,
        model_version=result.model_version,
        generated_at=result.generated_at,
    )


@router.get("/summary", response_model=ForecastSummaryResponse)
def get_tenant_forecast_summary(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Returns tenant-wide aggregated 7-day forecast summary across all active SKUs.
    """
    items = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.tenant_id == ctx.tenant_id,
            InventoryItem.is_active == True,
        )
        .all()
    )

    inference_service = get_inference_service()
    summary_items = []
    total_vol = 0.0

    for it in items:
        sku_val = it.sku or it.name
        traj = inference_service.predict_daily_trajectory(
            sku=sku_val,
            horizon_days=7,
            tenant_id=ctx.tenant_id,
            product_name=it.name,
            unit=it.unit,
        )
        p7d = traj.predicted_7d_demand
        total_vol += p7d
        summary_items.append(ForecastSummaryItem(
            sku=sku_val,
            product_name=it.name,
            unit=it.unit,
            current_stock=float(it.current_quantity),
            predicted_7d_demand=p7d,
            daily_average=round(p7d / 7.0, 2),
        ))

    return ForecastSummaryResponse(
        tenant_id=ctx.tenant_id,
        total_skus_tracked=len(summary_items),
        total_predicted_7d_volume=round(total_vol, 2),
        forecasts=summary_items,
        generated_at=str(datetime.now().isoformat()),
    )
