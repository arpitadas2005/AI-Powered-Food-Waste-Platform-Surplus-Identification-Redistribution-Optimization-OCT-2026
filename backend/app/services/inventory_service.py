"""Core Inventory Business Logic & Stock Ledger Service."""

import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus
from backend.app.models.transaction import ReferenceType, StockTransaction, TransactionType
from backend.app.schemas.inventory import (
    InventoryItemCreate,
    InventoryItemUpdate,
    StockAdjustmentRequest,
)


class InventoryServiceError(Exception):
    """Base exception for inventory service operations."""
    pass


class ItemNotFoundError(InventoryServiceError):
    """Raised when an item is not found or belongs to another tenant."""
    pass


class CategoryNotFoundError(InventoryServiceError):
    """Raised when category does not exist."""
    pass


class DuplicateSkuError(InventoryServiceError):
    """Raised when a SKU already exists for the tenant."""
    pass


class InsufficientStockError(InventoryServiceError):
    """Raised when an adjustment would cause negative inventory."""
    pass


def calculate_days_to_expiry(expiry_date: date) -> float:
    """Calculate remaining days to expiration relative to current UTC date."""
    today = datetime.now(timezone.utc).date()
    delta = (expiry_date - today).days
    return float(delta)


def derive_status(expiry_date: date, current_quantity: float, warning_days: int = 3) -> str:
    """Derive dynamic operational status for an item based on stock and expiry."""
    if current_quantity <= 0:
        return InventoryStatus.DEPLETED.value
    today = datetime.now(timezone.utc).date()
    days_left = (expiry_date - today).days
    if days_left < 0:
        return InventoryStatus.EXPIRED.value
    elif days_left <= warning_days:
        return InventoryStatus.EXPIRING_SOON.value
    return InventoryStatus.ACTIVE.value


def create_inventory_item(
    db: Session,
    tenant_id: str,
    user_id: Optional[str],
    item_in: InventoryItemCreate,
) -> InventoryItem:
    """
    Creates an inventory item and records its initial stock transaction atomically.
    """
    # 1. Validate Category
    category = db.execute(
        select(Category).where(
            Category.id == item_in.category_id,
            or_(Category.tenant_id == tenant_id, Category.tenant_id == None),
        )
    ).scalar_one_or_none()
    if not category:
        raise CategoryNotFoundError(f"Category '{item_in.category_id}' does not exist")

    # 2. Check SKU Uniqueness within Tenant
    if item_in.sku:
        existing_sku = db.execute(
            select(InventoryItem).where(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.sku == item_in.sku,
                InventoryItem.is_active == True,
            )
        ).scalar_one_or_none()
        if existing_sku:
            raise DuplicateSkuError(f"Item with SKU '{item_in.sku}' already exists in your inventory")

    initial_qty = float(item_in.initial_quantity)
    status = derive_status(item_in.expiry_date, initial_qty)

    # 3. Create Inventory Record
    item = InventoryItem(
        tenant_id=tenant_id,
        category_id=category.id,
        name=item_in.name.strip(),
        sku=item_in.sku.strip() if item_in.sku else None,
        barcode=item_in.barcode.strip() if item_in.barcode else None,
        current_quantity=initial_qty,
        unit=item_in.unit,
        cost_per_unit=float(item_in.cost_per_unit),
        selling_price=float(item_in.selling_price) if item_in.selling_price is not None else None,
        purchase_date=item_in.purchase_date,
        expiry_date=item_in.expiry_date,
        batch_number=item_in.batch_number,
        storage_requirement=item_in.storage_requirement,
        storage_location=item_in.storage_location,
        status=status,
        is_active=True,
    )
    db.add(item)
    db.flush()

    # 4. Record Initial Stock Transaction
    tx = StockTransaction(
        tenant_id=tenant_id,
        item_id=item.id,
        transaction_type=TransactionType.INITIAL_COUNT.value,
        quantity_change=initial_qty,
        quantity_before=0.0,
        quantity_after=initial_qty,
        reason="Initial inventory registration",
        reference_type=ReferenceType.MANUAL_ENTRY.value,
        created_by_user_id=user_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(item)
    return item


def get_inventory_item(
    db: Session,
    tenant_id: str,
    item_id: str,
) -> Optional[InventoryItem]:
    """Retrieve single item by ID within tenant boundary."""
    return db.execute(
        select(InventoryItem)
        .options(joinedload(InventoryItem.category))
        .where(
            InventoryItem.id == item_id,
            InventoryItem.tenant_id == tenant_id,
            InventoryItem.is_active == True,
        )
    ).scalar_one_or_none()


def update_inventory_item(
    db: Session,
    tenant_id: str,
    user_id: Optional[str],
    item_id: str,
    update_in: InventoryItemUpdate,
) -> InventoryItem:
    """Partially updates inventory item fields."""
    item = get_inventory_item(db, tenant_id, item_id)
    if not item:
        raise ItemNotFoundError(f"Inventory item '{item_id}' not found")

    # If updating category, check existence
    if update_in.category_id and update_in.category_id != item.category_id:
        category = db.execute(
            select(Category).where(
                Category.id == update_in.category_id,
                or_(Category.tenant_id == tenant_id, Category.tenant_id == None),
            )
        ).scalar_one_or_none()
        if not category:
            raise CategoryNotFoundError(f"Category '{update_in.category_id}' does not exist")
        item.category_id = category.id

    # If updating SKU, check uniqueness
    if update_in.sku and update_in.sku != item.sku:
        existing_sku = db.execute(
            select(InventoryItem).where(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.sku == update_in.sku,
                InventoryItem.id != item.id,
                InventoryItem.is_active == True,
            )
        ).scalar_one_or_none()
        if existing_sku:
            raise DuplicateSkuError(f"SKU '{update_in.sku}' is already in use")
        item.sku = update_in.sku

    if update_in.name is not None:
        item.name = update_in.name.strip()
    if update_in.barcode is not None:
        item.barcode = update_in.barcode.strip() if update_in.barcode else None
    if update_in.cost_per_unit is not None:
        item.cost_per_unit = float(update_in.cost_per_unit)
    if update_in.selling_price is not None:
        item.selling_price = float(update_in.selling_price)
    if update_in.expiry_date is not None:
        if update_in.expiry_date < item.purchase_date:
            raise InventoryServiceError("expiry_date cannot be earlier than purchase_date")
        item.expiry_date = update_in.expiry_date
    if update_in.batch_number is not None:
        item.batch_number = update_in.batch_number
    if update_in.storage_requirement is not None:
        item.storage_requirement = update_in.storage_requirement
    if update_in.storage_location is not None:
        item.storage_location = update_in.storage_location
    if update_in.status is not None:
        item.status = update_in.status

    # Recalculate status
    item.status = derive_status(item.expiry_date, float(item.current_quantity))

    db.commit()
    db.refresh(item)
    return item


def delete_inventory_item(
    db: Session,
    tenant_id: str,
    user_id: Optional[str],
    item_id: str,
) -> bool:
    """Soft deletes / archives an item."""
    item = get_inventory_item(db, tenant_id, item_id)
    if not item:
        raise ItemNotFoundError(f"Inventory item '{item_id}' not found")

    item.is_active = False
    item.status = InventoryStatus.DISCARDED.value
    db.commit()
    return True


def list_inventory_items(
    db: Session,
    tenant_id: str,
    page: int = 1,
    size: int = 50,
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    storage_requirement: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = "expiry_date",
    sort_order: str = "asc",
) -> Tuple[List[InventoryItem], int]:
    """
    Search, filter, sort, and paginate inventory items strictly within tenant boundary.
    """
    query = (
        select(InventoryItem)
        .options(joinedload(InventoryItem.category))
        .where(
            InventoryItem.tenant_id == tenant_id,
            InventoryItem.is_active == True,
        )
    )

    # 1. Search across name, sku, barcode
    if search:
        search_term = f"%{search.strip()}%"
        query = query.where(
            or_(
                InventoryItem.name.ilike(search_term),
                InventoryItem.sku.ilike(search_term),
                InventoryItem.barcode.ilike(search_term),
            )
        )

    # 2. Filters
    if category_id:
        query = query.where(InventoryItem.category_id == category_id)
    if storage_requirement:
        query = query.where(InventoryItem.storage_requirement == storage_requirement.upper())
    if status:
        query = query.where(InventoryItem.status == status.upper())

    # 3. Total Count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar_one()

    # 4. Sorting
    sort_col = getattr(InventoryItem, sort_by, InventoryItem.expiry_date)
    if sort_order.lower() == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    # 5. Pagination
    offset = (page - 1) * size
    items = db.execute(query.offset(offset).limit(size)).scalars().all()

    return list(items), total


def adjust_stock_quantity(
    db: Session,
    tenant_id: str,
    user_id: Optional[str],
    item_id: str,
    adj: StockAdjustmentRequest,
) -> Tuple[InventoryItem, StockTransaction]:
    """
    Safely adjusts stock quantity with concurrency safety, idempotency,
    negative stock prevention, and immutable transaction ledger logging.
    """
    # 1. Idempotency Check
    if adj.idempotency_key:
        existing_tx = db.execute(
            select(StockTransaction).where(
                StockTransaction.tenant_id == tenant_id,
                StockTransaction.item_id == item_id,
                StockTransaction.reference_id == adj.idempotency_key,
            )
        ).scalar_one_or_none()
        if existing_tx:
            item = get_inventory_item(db, tenant_id, item_id)
            return item, existing_tx

    # 2. Fetch and Lock Item
    # For SQLite, standard query; for PostgreSQL, with_for_update()
    item_query = select(InventoryItem).where(
        InventoryItem.id == item_id,
        InventoryItem.tenant_id == tenant_id,
        InventoryItem.is_active == True,
    )
    bind = db.get_bind()
    if bind and bind.dialect.name == "postgresql":
        item_query = item_query.with_for_update()

    item = db.execute(item_query).scalar_one_or_none()
    if not item:
        raise ItemNotFoundError(f"Inventory item '{item_id}' not found")

    qty_before = float(item.current_quantity)
    delta = float(adj.quantity_delta)
    qty_after = qty_before + delta

    # 3. Prevent Negative Stock
    if qty_after < 0:
        raise InsufficientStockError(
            f"Cannot deduct {abs(delta):.2f} {item.unit}. Only {qty_before:.2f} {item.unit} available in stock."
        )

    # 4. Update Stock & Derive Status
    item.current_quantity = qty_after
    item.status = derive_status(item.expiry_date, qty_after)

    # 5. Insert Immutable Transaction Ledger Record
    tx = StockTransaction(
        tenant_id=tenant_id,
        item_id=item.id,
        transaction_type=adj.adjustment_type,
        quantity_change=delta,
        quantity_before=qty_before,
        quantity_after=qty_after,
        reason=adj.reason,
        reference_type=adj.reference_type or ReferenceType.MANUAL_ENTRY.value,
        reference_id=adj.idempotency_key or adj.reference_id,
        created_by_user_id=user_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(item)
    db.refresh(tx)
    return item, tx


def lookup_by_barcode(
    db: Session,
    tenant_id: str,
    barcode: str,
) -> Tuple[Optional[InventoryItem], str, Optional[Dict[str, Any]]]:
    """
    Fast lookup by barcode or SKU strictly within tenant boundary.
    Supports standard UPC/EAN, internal SKU barcodes, and structured JSON QR codes.
    Returns:
        (matched_item, code_type, optional_embedded_data)
    """
    raw_code = barcode.strip()
    embedded_data: Optional[Dict[str, Any]] = None
    code_type = "RAW_CODE"
    lookup_keys = [raw_code]

    # Check for structured JSON QR code
    if (raw_code.startswith("{") and raw_code.endswith("}")) or (raw_code.startswith("[") and raw_code.endswith("]")):
        try:
            parsed = json.loads(raw_code)
            if isinstance(parsed, dict):
                embedded_data = parsed
                code_type = "STRUCTURED_QR_JSON"
                if "barcode" in parsed:
                    lookup_keys.insert(0, str(parsed["barcode"]).strip())
                if "sku" in parsed:
                    lookup_keys.append(str(parsed["sku"]).strip())
        except Exception:
            pass

    # 1. Match by barcode
    for key in lookup_keys:
        item = db.execute(
            select(InventoryItem)
            .options(joinedload(InventoryItem.category))
            .where(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.barcode == key,
                InventoryItem.is_active == True,
            )
        ).scalar_one_or_none()
        if item:
            if code_type == "RAW_CODE":
                code_type = "UPC_OR_EAN" if key.isdigit() and len(key) in {8, 12, 13, 14} else "BARCODE"
            return item, code_type, embedded_data

    # 2. Fallback match by SKU
    for key in lookup_keys:
        item = db.execute(
            select(InventoryItem)
            .options(joinedload(InventoryItem.category))
            .where(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.sku == key,
                InventoryItem.is_active == True,
            )
        ).scalar_one_or_none()
        if item:
            if code_type == "RAW_CODE":
                code_type = "SKU"
            return item, code_type, embedded_data

    return None, code_type, embedded_data


def get_item_transactions(
    db: Session,
    tenant_id: str,
    item_id: str,
) -> List[StockTransaction]:
    """Retrieve audit transaction history for a specific item."""
    item = get_inventory_item(db, tenant_id, item_id)
    if not item:
        raise ItemNotFoundError(f"Inventory item '{item_id}' not found")

    return list(
        db.execute(
            select(StockTransaction)
            .where(
                StockTransaction.tenant_id == tenant_id,
                StockTransaction.item_id == item_id,
            )
            .order_by(StockTransaction.created_at.desc())
        )
        .scalars()
        .all()
    )
