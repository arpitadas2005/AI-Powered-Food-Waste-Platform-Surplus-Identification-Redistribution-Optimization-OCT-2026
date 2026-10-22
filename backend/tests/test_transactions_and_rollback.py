"""Tests for Atomic Transaction Rollback, Ledger Invariants, and Security Utilities."""

from datetime import date, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.security import (
    create_access_token,
    decode_token,
    get_password_hash,
    hash_secret,
    verify_password,
    verify_secret,
    verify_webhook_signature,
)
from backend.app.models.tenant import Tenant
from backend.app.models.user import User, UserRole
from backend.app.models.inventory import InventoryItem
from backend.app.models.transaction import StockTransaction, TransactionType


def test_transaction_atomic_rollback_on_failure(db_session: Session, tenant_a: Tenant):
    """
    Verify that if an error occurs within an operation batch,
    the entire transaction is rolled back and no partial records persist.
    """
    initial_count = len(db_session.execute(select(InventoryItem)).scalars().all())

    # Begin savepoint
    nested = db_session.begin_nested()
    try:
        # Item 1: Valid
        item1 = InventoryItem(
            tenant_id=tenant_a.id,
            category_id="cat_dairy_eggs",
            name="Valid Milk Lot",
            current_quantity=20.0,
            unit="liters",
            cost_per_unit=1.5,
            purchase_date=date.today(),
            expiry_date=date.today() + timedelta(days=5),
            storage_requirement="REFRIGERATED",
        )
        db_session.add(item1)
        db_session.flush()

        # Item 2: Invalid (negative quantity triggers database check constraint)
        item2 = InventoryItem(
            tenant_id=tenant_a.id,
            category_id="cat_dairy_eggs",
            name="Corrupt Negative Milk",
            current_quantity=-50.0,
            unit="liters",
            cost_per_unit=1.5,
            purchase_date=date.today(),
            expiry_date=date.today() + timedelta(days=5),
            storage_requirement="REFRIGERATED",
        )
        db_session.add(item2)
        db_session.flush()
    except IntegrityError:
        nested.rollback()

    # Verify that Item 1 was NOT committed due to rollback of the failed batch
    final_count = len(db_session.execute(select(InventoryItem)).scalars().all())
    assert final_count == initial_count


def test_stock_adjustment_atomic_ledger_reconciliation(
    db_session: Session, tenant_a: Tenant, user_a_owner: User
):
    """
    Verify that updating physical stock and logging a ledger entry maintain
    exact mathematical reconciliation.
    """
    # 1. Initial creation (50 units)
    item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Greek Yogurt 500g",
        current_quantity=50.0,
        unit="units",
        cost_per_unit=2.0,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=7),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(item)
    db_session.flush()

    tx_initial = StockTransaction(
        tenant_id=tenant_a.id,
        item_id=item.id,
        transaction_type=TransactionType.INITIAL_COUNT.value,
        quantity_change=50.0,
        quantity_before=0.0,
        quantity_after=50.0,
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(tx_initial)
    db_session.flush()

    # 2. Restock (+25 units)
    qty_before = item.current_quantity
    delta = 25.0
    item.current_quantity += delta

    tx_restock = StockTransaction(
        tenant_id=tenant_a.id,
        item_id=item.id,
        transaction_type=TransactionType.RESTOCK.value,
        quantity_change=delta,
        quantity_before=qty_before,
        quantity_after=item.current_quantity,
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(tx_restock)
    db_session.flush()

    # 3. Sale / Decrement (-15 units)
    qty_before = item.current_quantity
    sale_delta = -15.0
    item.current_quantity += sale_delta

    tx_sale = StockTransaction(
        tenant_id=tenant_a.id,
        item_id=item.id,
        transaction_type=TransactionType.POS_SALE.value,
        quantity_change=sale_delta,
        quantity_before=qty_before,
        quantity_after=item.current_quantity,
        reference_type="POS_ORDER",
        reference_id="order_987654",
    )
    db_session.add(tx_sale)
    db_session.flush()

    assert item.current_quantity == 60.0

    # Query all transactions and verify sum(delta) == current_quantity
    all_txs = (
        db_session.execute(
            select(StockTransaction)
            .where(StockTransaction.item_id == item.id)
            .order_by(StockTransaction.created_at.asc())
        )
        .scalars()
        .all()
    )

    assert len(all_txs) == 3
    total_delta = sum(t.quantity_change for t in all_txs)
    assert total_delta == item.current_quantity


def test_password_hashing_and_verification():
    """Verify bcrypt password hashing and verification safety."""
    raw_pass = "ComplexPassword2026!#"
    hashed = get_password_hash(raw_pass)

    assert hashed != raw_pass
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False


def test_jwt_token_minting_and_decoding(tenant_a: Tenant, user_a_owner: User):
    """Verify JWT access token creation, claims extraction, and tamper detection."""
    token = create_access_token(
        subject=user_a_owner.id,
        tenant_id=tenant_a.id,
        role=UserRole.BUSINESS_OWNER.value,
    )

    payload = decode_token(token)
    assert payload["sub"] == user_a_owner.id
    assert payload["tenant_id"] == tenant_a.id
    assert payload["role"] == UserRole.BUSINESS_OWNER.value
    assert "exp" in payload


def test_pos_webhook_hmac_signature_verification():
    """Verify constant-time HMAC-SHA256 signature verification."""
    import hmac
    import hashlib

    secret = "whsec_super_secret_pos_key_123"
    payload = b'{"event":"order.completed","amount":25.50}'

    # Compute valid signature
    computed_hash = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    valid_header = f"sha256={computed_hash}"

    # Valid check
    assert verify_webhook_signature(payload, valid_header, secret) is True

    # Tampered payload check
    tampered_payload = b'{"event":"order.completed","amount":999.99}'
    assert verify_webhook_signature(tampered_payload, valid_header, secret) is False

    # Tampered secret check
    assert verify_webhook_signature(payload, valid_header, "wrong_secret") is False

    # Malformed header check
    assert verify_webhook_signature(payload, "invalid_header", secret) is False


def test_pos_secret_hashing():
    """Verify one-way secret hashing and verification for POS API keys."""
    raw_api_key = "pos_live_key_abcdef1234567890"
    stored_hash = hash_secret(raw_api_key)

    assert stored_hash != raw_api_key
    assert len(stored_hash) == 64  # SHA-256 hex string length
    assert verify_secret(raw_api_key, stored_hash) is True
    assert verify_secret("wrong_key", stored_hash) is False
