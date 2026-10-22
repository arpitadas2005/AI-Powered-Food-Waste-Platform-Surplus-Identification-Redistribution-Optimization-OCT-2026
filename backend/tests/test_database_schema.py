"""Tests for Database Schema, Foreign Keys, Check Constraints, and Uniqueness Rules."""

from datetime import date, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.tenant import Tenant, BusinessType
from backend.app.models.user import User, UserRole
from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus, ItemUnit
from backend.app.models.transaction import StockTransaction, TransactionType


def test_table_presence_and_category_seeding(db_session: Session):
    """Verify that all standard taxonomy categories are present and readable."""
    categories = db_session.execute(select(Category)).scalars().all()
    assert len(categories) == 9
    slugs = {c.slug for c in categories}
    assert "dairy-and-eggs" in slugs
    assert "fresh-meat-and-poultry" in slugs
    assert "leafy-greens-and-soft-produce" in slugs


def test_foreign_key_tenant_constraint(db_session: Session):
    """Verify foreign key enforcement when tenant does not exist."""
    invalid_item = InventoryItem(
        tenant_id="00000000-0000-0000-0000-000000000000",  # Non-existent
        category_id="cat_dairy_eggs",
        name="Orphan Milk",
        current_quantity=10.0,
        unit="liters",
        cost_per_unit=1.5,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(invalid_item)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_foreign_key_category_constraint(db_session: Session, tenant_a: Tenant):
    """Verify foreign key enforcement when category does not exist."""
    invalid_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="non_existent_category_id",
        name="Mystery Food",
        current_quantity=5.0,
        unit="units",
        cost_per_unit=2.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=3),
        storage_requirement="AMBIENT",
    )
    db_session.add(invalid_item)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_unique_tenant_slug(db_session: Session, tenant_a: Tenant):
    """Verify tenant slug uniqueness constraint."""
    duplicate_tenant = Tenant(
        name="Different Name Same Slug",
        slug=tenant_a.slug,  # Collision
        business_type=BusinessType.RESTAURANT.value,
        contact_email="other@example.com",
    )
    db_session.add(duplicate_tenant)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_unique_sku_within_same_tenant(db_session: Session, tenant_a: Tenant):
    """Verify SKU uniqueness within a single tenant boundary."""
    item1 = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Whole Milk 1L",
        sku="SKU-DAIRY-001",
        current_quantity=10.0,
        unit="liters",
        cost_per_unit=1.2,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(item1)
    db_session.flush()

    item2 = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Skim Milk 1L",
        sku="SKU-DAIRY-001",  # Duplicate SKU in same tenant
        current_quantity=5.0,
        unit="liters",
        cost_per_unit=1.1,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(item2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_same_sku_allowed_across_different_tenants(
    db_session: Session, tenant_a: Tenant, tenant_b: Tenant
):
    """Verify that different tenants can reuse identical SKUs without conflict."""
    item_a = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Milk A",
        sku="SHARED-SKU-100",
        current_quantity=10.0,
        unit="liters",
        cost_per_unit=1.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(item_a)
    db_session.flush()

    item_b = InventoryItem(
        tenant_id=tenant_b.id,
        category_id="cat_bakery",
        name="Bread B",
        sku="SHARED-SKU-100",  # Identical SKU but different tenant
        current_quantity=20.0,
        unit="units",
        cost_per_unit=2.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=3),
        storage_requirement="AMBIENT",
    )
    db_session.add(item_b)
    db_session.flush()

    assert item_a.id != item_b.id
    assert item_a.tenant_id != item_b.tenant_id


def test_check_constraint_negative_quantity(db_session: Session, tenant_a: Tenant):
    """Verify database check constraint preventing negative physical inventory."""
    negative_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Negative Milk",
        current_quantity=-5.0,  # Negative!
        unit="liters",
        cost_per_unit=1.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(negative_item)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_check_constraint_negative_cost(db_session: Session, tenant_a: Tenant):
    """Verify database check constraint preventing negative cost."""
    negative_cost_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Negative Cost Milk",
        current_quantity=10.0,
        unit="liters",
        cost_per_unit=-2.50,  # Negative!
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(negative_cost_item)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_check_constraint_expiry_before_purchase(db_session: Session, tenant_a: Tenant):
    """Verify check constraint ensuring expiry_date >= purchase_date."""
    invalid_dates_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Time Traveling Milk",
        current_quantity=10.0,
        unit="liters",
        cost_per_unit=1.0,
        purchase_date=date(2026, 10, 25),
        expiry_date=date(2026, 10, 20),  # Expired before purchase!
        storage_requirement="REFRIGERATED",
    )
    db_session.add(invalid_dates_item)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_stock_transaction_math_and_boundaries(
    db_session: Session, tenant_a: Tenant, user_a_owner: User
):
    """Verify mathematical consistency check in stock transaction ledger."""
    item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Fresh Cream 250ml",
        current_quantity=20.0,
        unit="packs",
        cost_per_unit=1.5,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=10),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(item)
    db_session.flush()

    # Valid transaction: 0 + 20 = 20
    tx_valid = StockTransaction(
        tenant_id=tenant_a.id,
        item_id=item.id,
        transaction_type=TransactionType.INITIAL_COUNT.value,
        quantity_change=20.0,
        quantity_before=0.0,
        quantity_after=20.0,
        reason="Initial inventory count",
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(tx_valid)
    db_session.flush()

    # Invalid transaction math: 20 + 10 != 50 (should trigger chk_tx_quantity_math)
    tx_bad_math = StockTransaction(
        tenant_id=tenant_a.id,
        item_id=item.id,
        transaction_type=TransactionType.RESTOCK.value,
        quantity_change=10.0,
        quantity_before=20.0,
        quantity_after=50.0,  # Math error! 20 + 10 is 30, not 50
        reason="Corrupt restock entry",
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(tx_bad_math)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_tenant_cascade_delete(db_session: Session):
    """Verify that deleting a tenant cascades and cleans up all child records."""
    temp_tenant = Tenant(
        name="Transient Tenant",
        slug="transient-tenant",
        business_type=BusinessType.RESTAURANT.value,
        contact_email="transient@example.com",
    )
    db_session.add(temp_tenant)
    db_session.flush()

    temp_item = InventoryItem(
        tenant_id=temp_tenant.id,
        category_id="cat_dairy_eggs",
        name="Transient Item",
        current_quantity=10.0,
        unit="units",
        cost_per_unit=1.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(temp_item)
    db_session.flush()

    item_id = temp_item.id
    tenant_id = temp_tenant.id

    # Delete tenant
    db_session.delete(temp_tenant)
    db_session.flush()

    # Verify item is also gone
    deleted_item = db_session.execute(
        select(InventoryItem).where(InventoryItem.id == item_id)
    ).scalar_one_or_none()
    assert deleted_item is None
