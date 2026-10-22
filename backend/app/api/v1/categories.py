"""Categories API Router."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_tenant_context
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.category import Category
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.inventory import CategorySummary

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=SuccessEnvelope[List[CategorySummary]])
def list_categories(
    perishability_tier: Optional[str] = Query(None),
    recommended_storage: Optional[str] = Query(None),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    List global and tenant-specific food categories.
    """
    query = select(Category).where(
        or_(Category.tenant_id == context.tenant_id, Category.tenant_id == None)
    )

    if perishability_tier:
        query = query.where(Category.perishability_tier == perishability_tier.upper())
    if recommended_storage:
        query = query.where(Category.recommended_storage == recommended_storage.upper())

    query = query.order_by(Category.name.asc())
    categories = db.execute(query).scalars().all()

    return SuccessEnvelope(
        data=[CategorySummary.model_validate(c) for c in categories]
    )
