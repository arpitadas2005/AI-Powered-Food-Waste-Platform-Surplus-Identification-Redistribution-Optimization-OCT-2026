"""Tests for Tenant Isolation, RBAC Security, and Cross-Tenant Prevention."""

from datetime import date, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.tenant import (
    TenantContext,
    CrossTenantAccessError,
    TenantNotFoundError,
    enforce_tenant_ownership,
    resolve_tenant_context,
    scope_query,
    verify_tenant_ownership,
)
from backend.app.models.tenant import Tenant
from backend.app.models.user import User, UserRole
from backend.app.models.inventory import InventoryItem
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.models.alert import ExpiryAlertHistory, AlertLevel


def test_resolve_tenant_context_success(
    db_session: Session, user_a_owner: User, tenant_a: Tenant
):
    """Verify clean resolution of trusted tenant context from user identity."""
    context = resolve_tenant_context(
        session=db_session,
        user_id=user_a_owner.id,
        claim_tenant_id=tenant_a.id,
    )
    assert context.tenant_id == tenant_a.id
    assert context.user_id == user_a_owner.id
    assert context.role == UserRole.BUSINESS_OWNER.value
    assert context.business_name == tenant_a.name
    assert context.timezone == tenant_a.timezone


def test_resolve_tenant_context_inactive_user(
    db_session: Session, user_a_owner: User, tenant_a: Tenant
):
    """Verify rejection when user account is deactivated."""
    user_a_owner.is_active = False
    db_session.flush()

    with pytest.raises(TenantNotFoundError):
        resolve_tenant_context(
            session=db_session,
            user_id=user_a_owner.id,
            claim_tenant_id=tenant_a.id,
        )


def test_resolve_tenant_context_inactive_tenant(
    db_session: Session, user_a_owner: User, tenant_a: Tenant
):
    """Verify rejection when tenant organization is deactivated."""
    tenant_a.is_active = False
    db_session.flush()

    with pytest.raises(TenantNotFoundError):
        resolve_tenant_context(
            session=db_session,
            user_id=user_a_owner.id,
            claim_tenant_id=tenant_a.id,
        )


def test_resolve_tenant_context_claim_spoofing(
    db_session: Session, user_a_owner: User, tenant_b: Tenant
):
    """Verify rejection when JWT claim tenant_id does not match user DB record."""
    with pytest.raises(CrossTenantAccessError):
        resolve_tenant_context(
            session=db_session,
            user_id=user_a_owner.id,
            claim_tenant_id=tenant_b.id,  # Spoofed! User A belongs to Tenant A, not B
        )


def test_scope_query_isolation(
    db_session: Session, tenant_a: Tenant, tenant_b: Tenant
):
    """Verify that scoped queries strictly isolate records between tenants."""
    # Create 3 items in Tenant A
    for i in range(3):
        db_session.add(
            InventoryItem(
                tenant_id=tenant_a.id,
                category_id="cat_dairy_eggs",
                name=f"Tenant A Item {i}",
                current_quantity=10.0,
                unit="units",
                cost_per_unit=1.0,
                purchase_date=date.today(),
                expiry_date=date.today() + timedelta(days=5),
                storage_requirement="REFRIGERATED",
            )
        )

    # Create 2 items in Tenant B
    for j in range(2):
        db_session.add(
            InventoryItem(
                tenant_id=tenant_b.id,
                category_id="cat_bakery",
                name=f"Tenant B Item {j}",
                current_quantity=15.0,
                unit="units",
                cost_per_unit=2.0,
                purchase_date=date.today(),
                expiry_date=date.today() + timedelta(days=3),
                storage_requirement="AMBIENT",
            )
        )
    db_session.flush()

    # Query items scoped to Tenant A
    stmt_a = scope_query(select(InventoryItem), InventoryItem, tenant_a.id)
    results_a = db_session.execute(stmt_a).scalars().all()
    assert len(results_a) == 3
    for item in results_a:
        assert item.tenant_id == tenant_a.id

    # Query items scoped to Tenant B
    stmt_b = scope_query(select(InventoryItem), InventoryItem, tenant_b.id)
    results_b = db_session.execute(stmt_b).scalars().all()
    assert len(results_b) == 2
    for item in results_b:
        assert item.tenant_id == tenant_b.id


def test_verify_tenant_ownership_cross_access(
    db_session: Session, tenant_a: Tenant, tenant_b: Tenant
):
    """Verify that attempting to mutate another tenant's record triggers CrossTenantAccessError."""
    item_a = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Tenant A Secret Lot",
        current_quantity=50.0,
        unit="units",
        cost_per_unit=1.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(item_a)
    db_session.flush()

    # Tenant B tries to verify/access Tenant A's item
    with pytest.raises(CrossTenantAccessError):
        verify_tenant_ownership(record=item_a, tenant_id=tenant_b.id)

    # Tenant A verifying their own item succeeds without exception
    verify_tenant_ownership(record=item_a, tenant_id=tenant_a.id)


def test_enforce_tenant_ownership_overrides_client_input(
    tenant_a: Tenant, tenant_b: Tenant
):
    """Verify that trusted tenant ID overrides any client-supplied spoofed tenant ID."""
    untrusted_item = InventoryItem(
        tenant_id=tenant_b.id,  # Client claimed Tenant B
        category_id="cat_dairy_eggs",
        name="Spoof Attempt Item",
        current_quantity=10.0,
        unit="units",
        cost_per_unit=1.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )

    # Server enforces authenticated tenant A
    enforce_tenant_ownership(untrusted_item, tenant_a.id)
    assert untrusted_item.tenant_id == tenant_a.id


def test_transaction_history_cross_tenant_isolation(
    db_session: Session, tenant_a: Tenant, tenant_b: Tenant, user_a_owner: User
):
    """Verify that stock transactions are never accessible across tenants."""
    item_a = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Item with Transactions",
        current_quantity=10.0,
        unit="units",
        cost_per_unit=1.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(item_a)
    db_session.flush()

    tx_a = StockTransaction(
        tenant_id=tenant_a.id,
        item_id=item_a.id,
        transaction_type=TransactionType.INITIAL_COUNT.value,
        quantity_change=10.0,
        quantity_before=0.0,
        quantity_after=10.0,
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(tx_a)
    db_session.flush()

    # Query transactions scoped to Tenant B
    stmt_tx_b = scope_query(select(StockTransaction), StockTransaction, tenant_b.id)
    results_tx_b = db_session.execute(stmt_tx_b).scalars().all()
    assert len(results_tx_b) == 0

    # Query transactions scoped to Tenant A
    stmt_tx_a = scope_query(select(StockTransaction), StockTransaction, tenant_a.id)
    results_tx_a = db_session.execute(stmt_tx_a).scalars().all()
    assert len(results_tx_a) == 1
    assert results_tx_a[0].id == tx_a.id


def test_alert_history_cross_tenant_isolation(
    db_session: Session, tenant_a: Tenant, tenant_b: Tenant
):
    """Verify alert history is isolated to the owning tenant."""
    item_a = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Expiring Yogurt",
        current_quantity=5.0,
        unit="units",
        cost_per_unit=1.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=1),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(item_a)
    db_session.flush()

    alert_a = ExpiryAlertHistory(
        tenant_id=tenant_a.id,
        item_id=item_a.id,
        alert_level=AlertLevel.CRITICAL.value,
        days_remaining=1.0,
    )
    db_session.add(alert_a)
    db_session.flush()

    # Scoped query for Tenant B must return 0
    stmt_b = scope_query(select(ExpiryAlertHistory), ExpiryAlertHistory, tenant_b.id)
    assert len(db_session.execute(stmt_b).scalars().all()) == 0

    # Scoped query for Tenant A must return 1
    stmt_a = scope_query(select(ExpiryAlertHistory), ExpiryAlertHistory, tenant_a.id)
    assert len(db_session.execute(stmt_a).scalars().all()) == 1
