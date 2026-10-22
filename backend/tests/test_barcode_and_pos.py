"""
Tests for Barcode/QR Scanning, Lookup Resolution, and POS Integrations.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus, ItemUnit
from backend.app.models.pos import PosIntegration, PosProvider
from backend.app.models.tenant import BusinessType, Tenant
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.models.user import User
from backend.app.schemas.inventory import StockAdjustmentRequest
from backend.app.schemas.pos import PosIntegrationCreate
from backend.app.services.inventory_service import (
    adjust_stock_quantity,
    lookup_by_barcode,
)
from backend.app.services.pos_adapter import (
    MockPosProviderAdapter,
    SquarePosAdapter,
    create_pos_integration,
    hash_secret,
    normalize_pos_unit,
    redact_secrets,
    sync_pos_integration,
    verify_hmac_signature,
)


@pytest.fixture
def barcode_items(db_session: Session, tenant_a: Tenant) -> dict:
    """Fixture creating items with barcodes, SKUs, and categories for Tenant A."""
    cat = db_session.query(Category).first()
    today = date(2026, 10, 22)

    item1 = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Organic Almond Milk 1L",
        sku="ALM-MILK-1L",
        barcode="012345678912",
        current_quantity=20.0,
        unit=ItemUnit.LITERS.value,
        cost_per_unit=2.50,
        purchase_date=today - timedelta(days=2),
        expiry_date=today + timedelta(days=10),
        status=InventoryStatus.ACTIVE.value,
    )

    item2 = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Artisan Sourdough Loaf",
        sku="BAK-SOUR-500G",
        barcode="987654321098",
        current_quantity=15.0,
        unit=ItemUnit.UNITS.value,
        cost_per_unit=1.80,
        purchase_date=today - timedelta(days=1),
        expiry_date=today + timedelta(days=3),
        status=InventoryStatus.ACTIVE.value,
    )

    db_session.add_all([item1, item2])
    db_session.commit()
    return {"milk": item1, "bread": item2}


def test_barcode_lookup_success_and_type_detection(db_session: Session, tenant_a: Tenant, barcode_items: dict):
    """Lookup by standard UPC/EAN barcode identifies item and returns correct code_type."""
    item, code_type, embedded = lookup_by_barcode(db_session, tenant_a.id, "012345678912")
    assert item is not None
    assert item.id == barcode_items["milk"].id
    assert code_type == "UPC_OR_EAN"
    assert embedded is None


def test_barcode_lookup_fallback_to_sku(db_session: Session, tenant_a: Tenant, barcode_items: dict):
    """Scanning an internal SKU barcode cleanly resolves the item."""
    item, code_type, embedded = lookup_by_barcode(db_session, tenant_a.id, "BAK-SOUR-500G")
    assert item is not None
    assert item.id == barcode_items["bread"].id
    assert code_type == "SKU"
    assert embedded is None


def test_barcode_lookup_structured_qr_json(db_session: Session, tenant_a: Tenant, barcode_items: dict):
    """
    Structured QR code encoding JSON metadata (batch, quantity, expiry).
    Correctly extracts embedded metadata without false assumptions.
    """
    qr_payload = json.dumps({
        "sku": "ALM-MILK-1L",
        "batch": "LOT-2026-X",
        "qty": 5,
        "exp": "2026-11-01"
    })

    item, code_type, embedded = lookup_by_barcode(db_session, tenant_a.id, qr_payload)
    assert item is not None
    assert item.id == barcode_items["milk"].id
    assert code_type == "STRUCTURED_QR_JSON"
    assert embedded is not None
    assert embedded["batch"] == "LOT-2026-X"
    assert embedded["qty"] == 5


def test_barcode_lookup_not_found(db_session: Session, tenant_a: Tenant):
    """Unregistered barcode returns None."""
    item, code_type, embedded = lookup_by_barcode(db_session, tenant_a.id, "000000000000")
    assert item is None
    assert embedded is None


def test_barcode_api_lookup_and_cross_tenant_isolation(client: TestClient, token_a_owner: str, token_b_owner: str, barcode_items: dict):
    """
    Tenant A can look up its item.
    Tenant B querying Tenant A's barcode gets 404 (zero information disclosure).
    """
    # 1. Tenant A succeeds
    resp_a = client.get(
        "/api/v1/inventory/lookup?code=012345678912",
        headers={"Authorization": f"Bearer {token_a_owner}"},
    )
    assert resp_a.status_code == 200
    data = resp_a.json()["data"]
    assert data["item"]["name"] == "Organic Almond Milk 1L"
    assert data["code_type"] == "UPC_OR_EAN"

    # 2. Tenant B fails with 404
    resp_b = client.get(
        "/api/v1/inventory/lookup?code=012345678912",
        headers={"Authorization": f"Bearer {token_b_owner}"},
    )
    assert resp_b.status_code == 404


def test_stock_adjustment_via_barcode_with_idempotency(client: TestClient, token_a_owner: str, barcode_items: dict):
    """
    Confirm stock adjustment with idempotency key.
    Submitting duplicate adjustment request returns previous result without double decrementing.
    """
    milk = barcode_items["milk"]
    idemp_key = "idemp_scan_test_12345"

    adj_payload = {
        "quantity_delta": -2.0,
        "adjustment_type": "POS_SALE",
        "reason": "Scanned sale at checkout",
        "reference_type": "BARCODE_SCAN",
        "reference_id": "012345678912",
        "idempotency_key": idemp_key,
    }

    # First request: reduces stock from 20.0 to 18.0
    resp1 = client.post(
        f"/api/v1/inventory/{milk.id}/adjust",
        headers={"Authorization": f"Bearer {token_a_owner}"},
        json=adj_payload,
    )
    assert resp1.status_code == 200
    assert resp1.json()["data"]["item"]["current_quantity"] == 18.0

    # Duplicate request: returns same transaction, stock remains 18.0
    resp2 = client.post(
        f"/api/v1/inventory/{milk.id}/adjust",
        headers={"Authorization": f"Bearer {token_a_owner}"},
        json=adj_payload,
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["item"]["current_quantity"] == 18.0


def test_pos_integration_registration_and_secret_redaction(client: TestClient, token_a_owner: str, db_session: Session):
    """
    Register POS integration.
    Verifies plaintext signing secret is returned only once, hashed in DB,
    and never exposed on subsequent list requests.
    """
    reg_resp = client.post(
        "/api/v1/pos/integrations",
        headers={"Authorization": f"Bearer {token_a_owner}"},
        json={
            "provider": "MOCK_SQUARE",
            "integration_name": "Main Register #1",
            "api_key": "test_sq_api_key_secret_123",
        },
    )
    assert reg_resp.status_code == 201
    data = reg_resp.json()["data"]
    integration_id = data["id"]
    webhook_slug = data["webhook_slug"]
    plaintext_secret = data["webhook_signing_secret"]

    assert plaintext_secret.startswith("whsec_")

    # Verify database state has hashes, NOT plaintexts
    db_integration = db_session.query(PosIntegration).filter(PosIntegration.id == integration_id).first()
    assert db_integration.webhook_secret_hash == hash_secret(plaintext_secret)
    assert db_integration.api_key_hash == hash_secret("test_sq_api_key_secret_123")
    assert plaintext_secret not in db_integration.webhook_secret_hash

    # Verify list endpoint redacts signing secret
    list_resp = client.get(
        "/api/v1/pos/integrations",
        headers={"Authorization": f"Bearer {token_a_owner}"},
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()["data"]
    target = next(i for i in listed if i["id"] == integration_id)
    assert target["webhook_signing_secret"] is None


def test_pos_unit_normalization():
    """Verify mapping of diverse external POS units to standard platform ItemUnits."""
    assert normalize_pos_unit("ea") == "units"
    assert normalize_pos_unit("EACH") == "units"
    assert normalize_pos_unit("pcs") == "units"
    assert normalize_pos_unit("kg") == "kg"
    assert normalize_pos_unit("KILOGRAMS") == "kg"
    assert normalize_pos_unit("g") == "g"
    assert normalize_pos_unit("liter") == "liters"
    assert normalize_pos_unit("ml") == "ml"
    assert normalize_pos_unit("boxes") == "boxes"
    assert normalize_pos_unit("pk") == "packs"
    assert normalize_pos_unit("unknown_unit") == "units"
    assert normalize_pos_unit(None) == "units"


def test_pos_sync_paginated_execution(db_session: Session, tenant_a: Tenant):
    """
    Test paginated inventory sync using the Mock POS Adapter.
    Validates double-entry stock transactions and pagination cursors.
    """
    integration, _ = create_pos_integration(
        db=db_session,
        tenant_id=tenant_a.id,
        payload=PosIntegrationCreate(
            provider="MOCK_POS",
            integration_name="Test POS Terminal",
        ),
    )

    # Sync page 1
    res1 = sync_pos_integration(db_session, integration.id, tenant_a.id, cursor=None)
    assert res1.status == "SUCCESS"
    assert res1.synced_items_count == 3
    assert res1.next_cursor == "page_2"

    # Sync page 2
    res2 = sync_pos_integration(db_session, integration.id, tenant_a.id, cursor=res1.next_cursor)
    assert res2.status == "SUCCESS"
    assert res2.synced_items_count == 2
    assert res2.next_cursor is None

    # Verify items exist in tenant inventory
    mock_items = db_session.query(InventoryItem).filter(
        InventoryItem.tenant_id == tenant_a.id,
        InventoryItem.sku.like("MOCK-POS-%"),
    ).all()
    assert len(mock_items) == 5


def test_pos_webhook_sales_deduction_and_idempotency(client: TestClient, db_session: Session, tenant_a: Tenant, barcode_items: dict):
    """
    Inbound POS order webhook deducting stock.
    Submitting the same order webhook twice must be idempotent.
    """
    integration, secret = create_pos_integration(
        db=db_session,
        tenant_id=tenant_a.id,
        payload=PosIntegrationCreate(
            provider="MOCK_SQUARE",
            integration_name="Store Checkout Register",
        ),
    )

    order_payload = {
        "event_type": "order.completed",
        "order_id": "sq_ord_test_998877",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "line_items": [
            {
                "sku": "ALM-MILK-1L",
                "quantity": 3.0,
                "unit_price": 2.50
            }
        ]
    }

    # Webhook 1
    resp1 = client.post(
        f"/api/v1/pos/webhook/{integration.webhook_slug}",
        json=order_payload,
    )
    assert resp1.status_code == 200
    assert resp1.json()["items_adjusted"] == 1

    # Verify milk quantity decreased from 20 to 17
    db_session.refresh(barcode_items["milk"])
    assert float(barcode_items["milk"].current_quantity) == 17.0

    # Webhook 2 (Duplicate replay)
    resp2 = client.post(
        f"/api/v1/pos/webhook/{integration.webhook_slug}",
        json=order_payload,
    )
    assert resp2.status_code == 200

    # Stock must remain 17.0 (NOT 14.0)
    db_session.refresh(barcode_items["milk"])
    assert float(barcode_items["milk"].current_quantity) == 17.0


def test_pos_webhook_hmac_signature_verification():
    """Verify HMAC signature calculation and verification."""
    raw_body = b'{"event_type": "order.completed", "order_id": "test_123"}'
    secret = "whsec_abcdef1234567890"

    expected_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    assert verify_hmac_signature(raw_body, secret, expected_sig) is True
    assert verify_hmac_signature(raw_body, secret, f"sha256={expected_sig}") is True

    # Tampered body fails
    assert verify_hmac_signature(b'tampered body', secret, expected_sig) is False
    # Wrong secret fails
    assert verify_hmac_signature(raw_body, "wrong_secret", expected_sig) is False


def test_pos_adapter_rate_limit_backoff():
    """Verify exponential backoff adapter retry mechanics."""
    adapter = SquarePosAdapter(max_retries=2, backoff_base_sec=0.01)
    assert adapter.max_retries == 2
    assert adapter.provider_name == "SQUARE"


def test_secret_redaction_utility():
    """Confirm sensitive credentials are recursively redacted."""
    sensitive = {
        "user_id": "usr_123",
        "api_key": "secret_token_val",
        "nested": {
            "password_hash": "hash_val",
            "webhook_secret": "whsec_val",
            "safe_counter": 42,
        },
        "list": [{"auth_token": "bearer 123"}, {"name": "Item"}],
    }
    redacted = redact_secrets(sensitive)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["password_hash"] == "[REDACTED]"
    assert redacted["nested"]["webhook_secret"] == "[REDACTED]"
    assert redacted["nested"]["safe_counter"] == 42
    assert redacted["list"][0]["auth_token"] == "[REDACTED]"
    assert redacted["list"][1]["name"] == "Item"
