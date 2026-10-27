"""
Analytics, Dashboard Summaries & Sustainability API Endpoints (Milestone 3 Phase 3).
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_tenant_context, require_roles
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.user import UserRole
from backend.app.schemas.analytics import (
    BusinessDashboardSummary,
    NgoDashboardSummary,
    SustainabilityMetrics,
    TimeSeriesResponse,
)
from backend.app.schemas.common import SuccessEnvelope
from backend.app.services.analytics_service import (
    generate_redistribution_csv,
    get_business_dashboard_summary,
    get_ngo_dashboard_summary,
    get_redistribution_time_series,
    get_sustainability_metrics,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/business/summary",
    response_model=SuccessEnvelope[BusinessDashboardSummary],
    summary="Get Business Dashboard operational and waste risk summary",
)
def get_business_summary(
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Returns high-level commercial KPIs, at-risk inventory value, active surplus listings,
    pending claim requests, scheduled pickups, and completed redistribution totals.
    """
    if context.role == UserRole.RECIPIENT_NGO.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="NGO organizations should access /api/v1/analytics/ngo/summary instead.",
        )

    summary = get_business_dashboard_summary(db=db, tenant_id=context.tenant_id)
    return SuccessEnvelope(data=summary)


@router.get(
    "/ngo/summary",
    response_model=SuccessEnvelope[NgoDashboardSummary],
    summary="Get NGO Dashboard operational summary",
)
def get_ngo_summary(
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Returns operational overview for recipient NGOs: eligible surplus listings,
    pending claims status, upcoming pickup logistics, completed food collections,
    and meal equivalents distributed.
    """
    summary = get_ngo_dashboard_summary(db=db, ngo_tenant_id=context.tenant_id)
    return SuccessEnvelope(data=summary)


@router.get(
    "/sustainability",
    response_model=SuccessEnvelope[SustainabilityMetrics],
    summary="Get cumulative and category-wise sustainability impact metrics",
)
def get_sustainability(
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    tenant_id: Optional[str] = Query(None, description="Optional tenant filter (Admin only)"),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Computes verified environmental, social, and financial impact metrics:
    - Rescued mass (kg) and discrete units
    - Avoided GHG emissions (EPA WARM v15: 2.5 kg CO2e / kg food)
    - Meal equivalents (USDA / Feeding America: 0.42 kg / meal)
    - Financial value rescued ($)
    - Breakdown by food category and tangible environmental equivalencies.
    """
    # Enforce strict multi-tenant boundary unless system administrator
    target_tenant_id = context.tenant_id
    if context.role == UserRole.SYSTEM_ADMIN.value:
        target_tenant_id = tenant_id or context.tenant_id

    is_ngo = (context.role == UserRole.RECIPIENT_NGO.value)

    metrics = get_sustainability_metrics(
        db=db,
        tenant_id=target_tenant_id,
        is_ngo=is_ngo,
        date_from=date_from,
        date_to=date_to,
    )
    return SuccessEnvelope(data=metrics)


@router.get(
    "/time-series",
    response_model=SuccessEnvelope[TimeSeriesResponse],
    summary="Get chronological redistribution impact timeline",
)
def get_time_series(
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    interval: str = Query("daily", pattern="^(daily|monthly)$", description="Aggregation frequency"),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Returns time-series data points of rescued food mass, meals, avoided emissions,
    and financial value for interactive line and bar charts.
    """
    is_ngo = (context.role == UserRole.RECIPIENT_NGO.value)
    series = get_redistribution_time_series(
        db=db,
        tenant_id=context.tenant_id,
        is_ngo=is_ngo,
        date_from=date_from,
        date_to=date_to,
        interval=interval,
    )
    return SuccessEnvelope(data=series)


@router.get(
    "/export/csv",
    summary="Export sanitized redistribution sustainability report as CSV",
    response_class=StreamingResponse,
)
def export_sustainability_csv(
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Generates a secure, formula-injection-sanitized CSV export of completed redistribution
    transactions and verified environmental impact metrics.
    """
    is_ngo = (context.role == UserRole.RECIPIENT_NGO.value)
    csv_buffer = generate_redistribution_csv(
        db=db,
        tenant_id=context.tenant_id,
        is_ngo=is_ngo,
        date_from=date_from,
        date_to=date_to,
    )

    filename = f"redistribution_sustainability_report_{date.today().isoformat()}.csv"

    return StreamingResponse(
        iter([csv_buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
