"""Inventory REST API Endpoints."""

import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_tenant_context, require_roles
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.user import UserRole
from backend.app.schemas.common import PaginatedResponse, PaginationMeta, SuccessEnvelope
from backend.app.schemas.inventory import (
    BarcodeLookupResult,
    CategorySummary,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    StockAdjustmentRequest,
    StockTransactionResponse,
)
from backend.app.services.inventory_service import (
    CategoryNotFoundError,
    DuplicateSkuError,
    InsufficientStockError,
    InventoryServiceError,
    ItemNotFoundError,
    adjust_stock_quantity,
    calculate_days_to_expiry,
    create_inventory_item,
    delete_inventory_item,
    get_inventory_item,
    get_item_transactions,
    list_inventory_items,
    lookup_by_barcode,
    update_inventory_item,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def serialize_item(item) -> InventoryItemResponse:
    """Helper to convert ORM model to response schema with computed days_to_expiry."""
    cat_summary = None
    if item.category:
        cat_summary = CategorySummary(
            id=item.category.id,
            name=item.category.name,
            slug=item.category.slug,
            perishability_tier=item.category.perishability_tier,
            recommended_storage=item.category.recommended_storage,
        )

    return InventoryItemResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        category_id=item.category_id,
        category=cat_summary,
        name=item.name,
        sku=item.sku,
        barcode=item.barcode,
        current_quantity=float(item.current_quantity),
        unit=item.unit,
        cost_per_unit=float(item.cost_per_unit),
        selling_price=float(item.selling_price) if item.selling_price is not None else None,
        purchase_date=item.purchase_date,
        expiry_date=item.expiry_date,
        days_to_expiry=calculate_days_to_expiry(item.expiry_date),
        batch_number=item.batch_number,
        storage_requirement=item.storage_requirement,
        storage_location=item.storage_location,
        status=item.status,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=PaginatedResponse[InventoryItemResponse])
def list_inventory(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search term for name, SKU, or barcode"),
    category_id: Optional[str] = Query(None, description="Filter by category UUID"),
    storage_requirement: Optional[str] = Query(None, description="Filter by storage requirement"),
    status: Optional[str] = Query(None, description="Filter by inventory status"),
    sort_by: str = Query("expiry_date", description="Sort column"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Search, filter, sort, and paginate inventory items strictly within tenant boundary.
    """
    items, total = list_inventory_items(
        db=db,
        tenant_id=context.tenant_id,
        page=page,
        size=size,
        search=search,
        category_id=category_id,
        storage_requirement=storage_requirement,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    total_pages = math.ceil(total / size) if size > 0 else 0
    serialized = [serialize_item(item) for item in items]

    return PaginatedResponse(
        data=serialized,
        pagination=PaginationMeta(
            page=page,
            size=size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.post(
    "",
    response_model=SuccessEnvelope[InventoryItemResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_roles(
                [
                    UserRole.BUSINESS_OWNER.value,
                    UserRole.STORE_MANAGER.value,
                    UserRole.INVENTORY_STAFF.value,
                ]
            )
        )
    ],
)
def create_item(
    item_in: InventoryItemCreate,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Create a new inventory item and log initial stock transaction.
    """
    try:
        item = create_inventory_item(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            item_in=item_in,
        )
        return SuccessEnvelope(data=serialize_item(item))
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateSkuError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InventoryServiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.get("/lookup", response_model=SuccessEnvelope[BarcodeLookupResult])
def lookup_item_by_barcode(
    code: str = Query(..., min_length=1, description="Scanned barcode or QR code"),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Lookup inventory item by barcode, SKU, or structured QR code strictly within tenant inventory.
    """
    item, code_type, embedded_data = lookup_by_barcode(db=db, tenant_id=context.tenant_id, barcode=code)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No item matching code '{code}' found in your inventory",
        )
    serialized_item = serialize_item(item)
    return SuccessEnvelope(
        data=BarcodeLookupResult(
            id=item.id,
            item=serialized_item,
            scanned_code=code,
            code_type=code_type,
            embedded_data=embedded_data,
        )
    )


@router.get("/{id}", response_model=SuccessEnvelope[InventoryItemResponse])
def get_item(
    id: str,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Retrieve single item by ID within tenant boundary.
    Returns 404 for non-existent items and cross-tenant items.
    """
    item = get_inventory_item(db=db, tenant_id=context.tenant_id, item_id=id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    return SuccessEnvelope(data=serialize_item(item))


@router.patch(
    "/{id}",
    response_model=SuccessEnvelope[InventoryItemResponse],
    dependencies=[
        Depends(
            require_roles(
                [UserRole.BUSINESS_OWNER.value, UserRole.STORE_MANAGER.value]
            )
        )
    ],
)
def update_item(
    id: str,
    update_in: InventoryItemUpdate,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Update inventory item details.
    """
    try:
        updated = update_inventory_item(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            item_id=id,
            update_in=update_in,
        )
        return SuccessEnvelope(data=serialize_item(updated))
    except ItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateSkuError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InventoryServiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.delete(
    "/{id}",
    response_model=SuccessEnvelope[dict],
    dependencies=[
        Depends(
            require_roles(
                [UserRole.BUSINESS_OWNER.value, UserRole.STORE_MANAGER.value]
            )
        )
    ],
)
def delete_item(
    id: str,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Soft-delete / decommission an inventory item.
    """
    try:
        delete_inventory_item(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            item_id=id,
        )
        return SuccessEnvelope(data={"id": id, "deleted": True})
    except ItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")


@router.post(
    "/{id}/adjust",
    response_model=SuccessEnvelope[dict],
    dependencies=[
        Depends(
            require_roles(
                [
                    UserRole.BUSINESS_OWNER.value,
                    UserRole.STORE_MANAGER.value,
                    UserRole.INVENTORY_STAFF.value,
                ]
            )
        )
    ],
)
def adjust_stock(
    id: str,
    adj_in: StockAdjustmentRequest,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Adjust physical stock quantity with mandatory operational justification.
    Records immutable transaction ledger entry.
    """
    try:
        item, tx = adjust_stock_quantity(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            item_id=id,
            adj=adj_in,
        )
        return SuccessEnvelope(
            data={
                "item": serialize_item(item),
                "transaction": StockTransactionResponse.model_validate(tx),
            }
        )
    except ItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InventoryServiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.get(
    "/{id}/transactions",
    response_model=SuccessEnvelope[List[StockTransactionResponse]],
    dependencies=[
        Depends(
            require_roles(
                [UserRole.BUSINESS_OWNER.value, UserRole.STORE_MANAGER.value]
            )
        )
    ],
)
def list_transactions(
    id: str,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Retrieve stock transaction ledger entries for a single inventory item.
    """
    try:
        txs = get_item_transactions(db=db, tenant_id=context.tenant_id, item_id=id)
        return SuccessEnvelope(data=[StockTransactionResponse.model_validate(t) for t in txs])
    except ItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
