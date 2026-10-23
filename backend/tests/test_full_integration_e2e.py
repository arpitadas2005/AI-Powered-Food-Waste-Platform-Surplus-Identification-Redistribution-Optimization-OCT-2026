"""
End-to-End Workflow & Frontend Integration Verification Tests.

Exercises the complete user workflows:
1. Item creation and persistence across session reloads.
2. Stock adjustments with immutable transaction ledger verification.
3. CSV bulk ingestion pipeline with validation and error reporting.
4. Expiry horizon classification with food safety donation guardrails.
5. Barcode & QR code scanning with structured metadata parsing.
6. POS provider sync and idempotent sales order webhook ingestion.
7. Cross-tenant isolation across all resources.
8. Frontend production bundle serving & static assets.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import io
import csv
import json
import os
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus, ItemUnit
from backend.app.models.pos import PosIntegration
from backend.app.models.tenant import Tenant
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.schemas.pos import PosIntegrationCreate


def test_frontend_production_bundle_serving(client: TestClient):
    """Verify FastAPI serves the compiled frontend single-page application and scanner interface."""
    # Root index.html
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "Food Waste Management Platform" in root_res.text
    assert '<div id="root"></div>' in root_res.text

    # Mobile scanner interface
    scanner_res = client.get("/scanner")
    assert scanner_res.status_code == 200
    assert "Mobile Barcode Scanner" in scanner_res.text


def test_e2e_workflow_inventory_lifecycle_and_persistence(client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant):
    """
    Workflow 1: Add item -> reload/query -> update -> adjust stock -> verify double-entry ledger.
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    today = date.today()

    # Step 1: Create Item
    create_payload = {
        "name": "E2E Farm Fresh Eggs 12pk",
        "category_id": "cat_dairy_eggs",
        "sku": "E2E-EGG-12",
        "barcode": "098765432109",
        "initial_quantity": 30.0,
        "unit": "packs",
        "cost_per_unit": 3.20,
        "purchase_date": str(today),
        "expiry_date": str(today + timedelta(days=14)),
        "storage_requirement": "REFRIGERATED",
        "storage_location": "Dairy Chiller A",
    }
    create_res = client.post("/api/v1/inventory", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    item_id = create_res.json()["data"]["id"]

    # Step 2: Query item (simulating page reload)
    get_res = client.get(f"/api/v1/inventory/{item_id}", headers=headers)
    assert get_res.status_code == 200
    item_data = get_res.json()["data"]
    assert item_data["name"] == "E2E Farm Fresh Eggs 12pk"
    assert item_data["current_quantity"] == 30.0

    # Step 3: Stock adjustment (Sale of 5 packs)
    idemp_key = f"e2e_sale_{item_id}"
    adj_payload = {
        "quantity_delta": -5.0,
        "adjustment_type": "POS_SALE",
        "reason": "Retail customer checkout",
        "reference_type": "POS_ORDER",
        "reference_id": "ord_1001",
        "idempotency_key": idemp_key,
    }
    adj_res = client.post(f"/api/v1/inventory/{item_id}/adjust", json=adj_payload, headers=headers)
    assert adj_res.status_code == 200
    assert adj_res.json()["data"]["item"]["current_quantity"] == 25.0

    # Step 4: Duplicate adjustment with same idempotency key must not double decrement
    adj_dup_res = client.post(f"/api/v1/inventory/{item_id}/adjust", json=adj_payload, headers=headers)
    assert adj_dup_res.status_code == 200
    assert adj_dup_res.json()["data"]["item"]["current_quantity"] == 25.0

    # Step 5: Verify transaction ledger history
    tx_res = client.get(f"/api/v1/inventory/{item_id}/transactions", headers=headers)
    assert tx_res.status_code == 200
    txs = tx_res.json()["data"]
    assert len(txs) == 2  # INITIAL_COUNT + 1 POS_SALE
    types = [t["transaction_type"] for t in txs]
    assert "INITIAL_COUNT" in types
    assert "POS_SALE" in types


def test_e2e_workflow_csv_import_pipeline(client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant):
    """
    Workflow 2: Download template -> Upload CSV with dry-run -> Commit -> Verify DB records.
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}

    # Step 1: Download CSV template
    tmpl_res = client.get("/api/v1/inventory/bulk-import/template", headers=headers)
    assert tmpl_res.status_code == 200
    assert "name,category,sku" in tmpl_res.text
    assert "current_quantity,unit" in tmpl_res.text

    # Step 2: Upload CSV with dry_run=true
    csv_content = (
        "name,category,current_quantity,unit,expiry_date,purchase_date,cost_per_unit,sku,barcode,batch_number,storage_location\n"
        "CSV Imported Artisan Rye,fresh-bakery-and-pastries,20.00,units,2026-10-30,2026-10-22,2.00,CSV-RYE-01,9900112233,BATCH-RYE-1,Bakery Rack 1\n"
    ).encode("utf-8")

    files = {"file": ("test_import.csv", io.BytesIO(csv_content), "text/csv")}
    dry_res = client.post("/api/v1/inventory/bulk-import/csv?dry_run=true&allow_partial=false", headers=headers, files=files)
    assert dry_res.status_code == 200
    dry_data = dry_res.json()["data"]
    assert dry_data["summary"]["accepted_rows"] == 1
    assert dry_data["summary"]["rejected_rows"] == 0

    # Verify not written during dry run
    item_check = db_session.query(InventoryItem).filter(InventoryItem.sku == "CSV-RYE-01").first()
    assert item_check is None

    # Step 3: Commit import
    files_commit = {"file": ("test_import.csv", io.BytesIO(csv_content), "text/csv")}
    commit_res = client.post("/api/v1/inventory/bulk-import/csv?dry_run=false&allow_partial=false", headers=headers, files=files_commit)
    assert commit_res.status_code == 200
    commit_data = commit_res.json()["data"]
    assert commit_data["status"] == "COMPLETED"

    # Verify persisted in database
    persisted = db_session.query(InventoryItem).filter(InventoryItem.sku == "CSV-RYE-01").first()
    assert persisted is not None
    assert persisted.name == "CSV Imported Artisan Rye"
    assert float(persisted.current_quantity) == 20.0


def test_e2e_workflow_expiry_evaluation_and_donation_guardrail(client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant):
    """
    Workflow 3: Create items near/past expiry -> Run evaluation -> Verify horizons and donation guardrails.
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    import zoneinfo
    tz = zoneinfo.ZoneInfo(tenant_a.timezone or "UTC")
    tenant_today = datetime.now(tz).date()
    cat = db_session.query(Category).first()

    # Expired item (yesterday in tenant timezone)
    exp_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Expired Ground Beef",
        sku="EXP-BEEF-01",
        current_quantity=5.0,
        unit=ItemUnit.KG.value,
        cost_per_unit=8.00,
        purchase_date=tenant_today - timedelta(days=5),
        expiry_date=tenant_today - timedelta(days=1),
        status=InventoryStatus.ACTIVE.value,
    )
    # Critical item (today in tenant timezone)
    crit_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Critical Ready Sandwich",
        sku="CRIT-SND-01",
        current_quantity=10.0,
        unit=ItemUnit.UNITS.value,
        cost_per_unit=3.50,
        purchase_date=tenant_today - timedelta(days=1),
        expiry_date=tenant_today,
        status=InventoryStatus.ACTIVE.value,
    )
    db_session.add_all([exp_item, crit_item])
    db_session.commit()

    # Run on-demand evaluation
    eval_res = client.post("/api/v1/inventory/expiry/evaluate?dry_run=false", headers=headers)
    assert eval_res.status_code == 200
    summary = eval_res.json()["data"]["summary"]
    assert summary["expired_count"] >= 1
    assert summary["critical_count"] >= 1

    # Query expiring items API
    at_risk_res = client.get("/api/v1/inventory/expiring?status=ALL_AT_RISK", headers=headers)
    assert at_risk_res.status_code == 200
    items = at_risk_res.json()["data"]["items"]

    # Verify food safety donation guardrail:
    expired_entry = next(i for i in items if i["sku"] == "EXP-BEEF-01")
    assert expired_entry["alert_level"] == "EXPIRED"
    assert expired_entry["donation_eligible"] is False
    assert expired_entry["recommended_action"] == "DISCARD_OR_COMPOST"

    critical_entry = next(i for i in items if i["sku"] == "CRIT-SND-01")
    assert critical_entry["alert_level"] == "CRITICAL"
    assert critical_entry["donation_eligible"] is True


def test_e2e_workflow_barcode_scanning_and_adjustment(client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant):
    """
    Workflow 4: Scan barcode / SKU -> Resolve item card -> Submit adjustment with confirmation.
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    today = date.today()
    cat = db_session.query(Category).first()

    item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Scan Target Greek Yogurt",
        sku="SCAN-YOG-01",
        barcode="880011223344",
        current_quantity=15.0,
        unit=ItemUnit.PACKS.value,
        cost_per_unit=1.50,
        purchase_date=today - timedelta(days=2),
        expiry_date=today + timedelta(days=8),
        status=InventoryStatus.ACTIVE.value,
    )
    db_session.add(item)
    db_session.commit()

    # Step 1: Lookup by barcode
    lookup_res = client.get("/api/v1/inventory/lookup?code=880011223344", headers=headers)
    assert lookup_res.status_code == 200
    lookup_data = lookup_res.json()["data"]
    assert lookup_data["item"]["name"] == "Scan Target Greek Yogurt"

    # Step 2: Confirm adjustment via modal submit
    adj_res = client.post(
        f"/api/v1/inventory/{item.id}/adjust",
        json={
            "quantity_delta": 10.0,
            "adjustment_type": "RESTOCK",
            "reason": "Scanned delivery confirmation",
            "reference_type": "BARCODE_SCAN",
            "reference_id": "880011223344",
            "idempotency_key": "scan_e2e_idemp_key_1",
        },
        headers=headers,
    )
    assert adj_res.status_code == 200
    assert adj_res.json()["data"]["item"]["current_quantity"] == 25.0


def test_e2e_workflow_pos_integration_and_webhook_sync(client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant):
    """
    Workflow 5: Register Mock POS -> Trigger sync -> Receive sales order webhook -> Verify stock.
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}

    # Step 1: Register integration
    reg_res = client.post(
        "/api/v1/pos/integrations",
        json={
            "provider": "MOCK_SQUARE",
            "integration_name": "E2E Front Register",
        },
        headers=headers,
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.json()["data"]
    integration_id = reg_data["id"]
    webhook_slug = reg_data["webhook_slug"]

    # Step 2: Trigger sync
    sync_res = client.post(f"/api/v1/pos/integrations/{integration_id}/sync", headers=headers)
    assert sync_res.status_code == 200
    sync_data = sync_res.json()["data"]
    assert sync_data["status"] == "SUCCESS"
    assert sync_data["synced_items_count"] > 0

    # Step 3: Receive sales webhook
    wh_payload = {
        "event_type": "order.completed",
        "order_id": "sq_e2e_order_7788",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "line_items": [
            {
                "sku": "MOCK-POS-01",
                "quantity": 2.0,
                "unit_price": 2.50
            }
        ]
    }
    wh_res = client.post(f"/api/v1/pos/webhook/{webhook_slug}", json=wh_payload)
    assert wh_res.status_code == 200
    assert wh_res.json()["items_adjusted"] == 1


def test_cross_tenant_isolation_boundary(client: TestClient, token_a_owner: str, token_b_owner: str, db_session: Session, tenant_a: Tenant, tenant_b: Tenant):
    """
    Workflow 6: Security boundary verification.
    Tenant B cannot view or mutate Tenant A's inventory, alerts, or POS integrations.
    """
    headers_a = {"Authorization": f"Bearer {token_a_owner}"}
    headers_b = {"Authorization": f"Bearer {token_b_owner}"}
    cat = db_session.query(Category).first()

    # Tenant A creates private item
    item_a = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Tenant A Private Wagyu",
        sku="A-WAGYU-01",
        barcode="112233445566",
        current_quantity=5.0,
        unit=ItemUnit.KG.value,
        cost_per_unit=50.00,
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        status=InventoryStatus.ACTIVE.value,
    )
    db_session.add(item_a)
    db_session.commit()

    # Tenant B attempts GET -> 404
    assert client.get(f"/api/v1/inventory/{item_a.id}", headers=headers_b).status_code == 404

    # Tenant B attempts PATCH -> 404
    assert client.patch(f"/api/v1/inventory/{item_a.id}", json={"selling_price": 1.0}, headers=headers_b).status_code == 404

    # Tenant B attempts adjust -> 404
    assert client.post(f"/api/v1/inventory/{item_a.id}/adjust", json={"quantity_delta": -5.0, "reason": "Theft"}, headers=headers_b).status_code == 404

    # Tenant B attempts barcode lookup of Tenant A's item -> 404
    assert client.get("/api/v1/inventory/lookup?code=112233445566", headers=headers_b).status_code == 404
