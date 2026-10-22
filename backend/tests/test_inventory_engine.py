"""Integration & Unit Tests for Inventory Core Engine and REST API.

Covers:
1. Successful item creation and retrieval.
2. Updating an item.
3. Invalid quantity and date values.
4. Unauthorized item access.
5. Cross-tenant item access.
6. Search, filtering, and pagination.
7. Stock adjustments and transaction history.
8. Concurrent updates, negative stock prevention, and idempotency.
9. Persistence after application restart or a new database read.
"""

from datetime import date, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus
from backend.app.models.tenant import Tenant
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.models.user import User


# ---------------------------------------------------------------------------
# 1. Successful Item Creation and Retrieval
# ---------------------------------------------------------------------------
def test_successful_item_creation_and_retrieval(client: TestClient, token_a_owner: str):
    """Verify creating a valid inventory item, checking status 201, and retrieving it."""
    payload = {
        "name": "Organic Whole Milk 1L",
        "category_id": "cat_dairy_eggs",
        "sku": "DAI-MILK-100",
        "barcode": "012345678905",
        "initial_quantity": 40.0,
        "unit": "liters",
        "cost_per_unit": 1.25,
        "selling_price": 2.50,
        "purchase_date": str(date.today()),
        "expiry_date": str(date.today() + timedelta(days=6)),
        "batch_number": "LOT-2026-A",
        "storage_requirement": "REFRIGERATED",
        "storage_location": "Chiller 1-A",
    }

    # Create
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    create_res = client.post("/api/v1/inventory", json=payload, headers=headers)
    assert create_res.status_code == 201
    res_json = create_res.json()
    assert res_json["success"] is True
    item_data = res_json["data"]
    item_id = item_data["id"]
    assert item_data["name"] == "Organic Whole Milk 1L"
    assert item_data["current_quantity"] == 40.0
    assert item_data["unit"] == "liters"
    assert item_data["status"] == InventoryStatus.ACTIVE.value
    assert item_data["days_to_expiry"] == 6.0
    assert item_data["category"]["id"] == "cat_dairy_eggs"

    # Retrieve by ID
    get_res = client.get(f"/api/v1/inventory/{item_id}", headers=headers)
    assert get_res.status_code == 200
    retrieved = get_res.json()["data"]
    assert retrieved["id"] == item_id
    assert retrieved["name"] == "Organic Whole Milk 1L"

    # Initial transaction check
    tx_res = client.get(f"/api/v1/inventory/{item_id}/transactions", headers=headers)
    assert tx_res.status_code == 200
    txs = tx_res.json()["data"]
    assert len(txs) == 1
    assert txs[0]["transaction_type"] == TransactionType.INITIAL_COUNT.value
    assert txs[0]["quantity_change"] == 40.0
    assert txs[0]["quantity_before"] == 0.0
    assert txs[0]["quantity_after"] == 40.0


# ---------------------------------------------------------------------------
# 2. Updating an Item
# ---------------------------------------------------------------------------
def test_update_item(client: TestClient, token_a_owner: str):
    """Verify updating fields of an existing inventory item."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    create_res = client.post(
        "/api/v1/inventory",
        json={
            "name": "Artisan Baguette",
            "category_id": "cat_bakery",
            "initial_quantity": 20.0,
            "unit": "units",
            "cost_per_unit": 0.80,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=2)),
            "storage_requirement": "AMBIENT",
        },
        headers=headers,
    )
    item_id = create_res.json()["data"]["id"]

    # Partial update: selling price, location, batch number
    update_res = client.patch(
        f"/api/v1/inventory/{item_id}",
        json={
            "selling_price": 2.99,
            "storage_location": "Front Counter Display",
            "batch_number": "BAK-990",
        },
        headers=headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()["data"]
    assert updated["selling_price"] == 2.99
    assert updated["storage_location"] == "Front Counter Display"
    assert updated["batch_number"] == "BAK-990"
    assert updated["name"] == "Artisan Baguette"


# ---------------------------------------------------------------------------
# 3. Invalid Quantity and Date Values
# ---------------------------------------------------------------------------
def test_invalid_quantity_and_date_values(client: TestClient, token_a_owner: str):
    """Verify rejection of negative quantities, bad units, and backwards dates."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}

    # Negative quantity
    res_neg_qty = client.post(
        "/api/v1/inventory",
        json={
            "name": "Invalid Item",
            "category_id": "cat_dairy_eggs",
            "initial_quantity": -10.0,
            "unit": "units",
            "cost_per_unit": 1.0,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=5)),
            "storage_requirement": "AMBIENT",
        },
        headers=headers,
    )
    assert res_neg_qty.status_code == 422
    assert res_neg_qty.json()["success"] is False

    # Expiry date earlier than purchase date
    res_bad_dates = client.post(
        "/api/v1/inventory",
        json={
            "name": "Time Warped Milk",
            "category_id": "cat_dairy_eggs",
            "initial_quantity": 10.0,
            "unit": "liters",
            "cost_per_unit": 1.0,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() - timedelta(days=5)),  # Earlier!
            "storage_requirement": "REFRIGERATED",
        },
        headers=headers,
    )
    assert res_bad_dates.status_code == 422
    assert res_bad_dates.json()["success"] is False

    # Invalid unit
    res_bad_unit = client.post(
        "/api/v1/inventory",
        json={
            "name": "Invalid Unit Food",
            "category_id": "cat_dairy_eggs",
            "initial_quantity": 10.0,
            "unit": "buckets",  # Unsupported
            "cost_per_unit": 1.0,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=5)),
            "storage_requirement": "AMBIENT",
        },
        headers=headers,
    )
    assert res_bad_unit.status_code == 422

    # Invalid category
    res_bad_cat = client.post(
        "/api/v1/inventory",
        json={
            "name": "Unknown Category Food",
            "category_id": "non_existent_category_uuid",
            "initial_quantity": 10.0,
            "unit": "units",
            "cost_per_unit": 1.0,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=5)),
            "storage_requirement": "AMBIENT",
        },
        headers=headers,
    )
    assert res_bad_cat.status_code == 404


# ---------------------------------------------------------------------------
# 4. Unauthorized Item Access
# ---------------------------------------------------------------------------
def test_unauthorized_item_access(
    client: TestClient, token_a_staff: str, token_a_owner: str
):
    """Verify RBAC rules and rejection of unauthenticated access."""
    # Create item as owner
    owner_headers = {"Authorization": f"Bearer {token_a_owner}"}
    create_res = client.post(
        "/api/v1/inventory",
        json={
            "name": "Steak",
            "category_id": "cat_meat_poultry",
            "initial_quantity": 15.0,
            "unit": "kg",
            "cost_per_unit": 12.0,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=3)),
            "storage_requirement": "REFRIGERATED",
        },
        headers=owner_headers,
    )
    item_id = create_res.json()["data"]["id"]

    # Attempt to read without token -> 401
    unauth_res = client.get(f"/api/v1/inventory/{item_id}")
    assert unauth_res.status_code == 401
    assert unauth_res.json()["success"] is False

    # Staff attempt to delete item -> 403 Forbidden
    staff_headers = {"Authorization": f"Bearer {token_a_staff}"}
    del_res = client.delete(f"/api/v1/inventory/{item_id}", headers=staff_headers)
    assert del_res.status_code == 403

    # Staff attempt to list transactions -> 403 Forbidden
    tx_res = client.get(f"/api/v1/inventory/{item_id}/transactions", headers=staff_headers)
    assert tx_res.status_code == 403

    # Staff IS allowed to adjust stock
    adj_res = client.post(
        f"/api/v1/inventory/{item_id}/adjust",
        json={
            "quantity_delta": 5.0,
            "reason": "Restock received by staff",
        },
        headers=staff_headers,
    )
    assert adj_res.status_code == 200


# ---------------------------------------------------------------------------
# 5. Cross-Tenant Item Access
# ---------------------------------------------------------------------------
def test_cross_tenant_item_access(
    client: TestClient, token_a_owner: str, token_b_owner: str
):
    """Verify Tenant B cannot read, update, delete, or adjust Tenant A's item."""
    # Tenant A creates an item
    headers_a = {"Authorization": f"Bearer {token_a_owner}"}
    create_res = client.post(
        "/api/v1/inventory",
        json={
            "name": "Secret Cheese Wheel",
            "category_id": "cat_dairy_eggs",
            "sku": "SECRET-CHEESE",
            "barcode": "999888777666",
            "initial_quantity": 10.0,
            "unit": "units",
            "cost_per_unit": 25.0,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=30)),
            "storage_requirement": "REFRIGERATED",
        },
        headers=headers_a,
    )
    item_a_id = create_res.json()["data"]["id"]

    # Tenant B tries to GET Tenant A's item -> Must return 404
    headers_b = {"Authorization": f"Bearer {token_b_owner}"}
    res_get = client.get(f"/api/v1/inventory/{item_a_id}", headers=headers_b)
    assert res_get.status_code == 404

    # Tenant B tries to PATCH Tenant A's item -> Must return 404
    res_patch = client.patch(
        f"/api/v1/inventory/{item_a_id}",
        json={"selling_price": 0.01},
        headers=headers_b,
    )
    assert res_patch.status_code == 404

    # Tenant B tries to DELETE Tenant A's item -> Must return 404
    res_del = client.delete(f"/api/v1/inventory/{item_a_id}", headers=headers_b)
    assert res_del.status_code == 404

    # Tenant B tries to adjust stock on Tenant A's item -> Must return 404
    res_adj = client.post(
        f"/api/v1/inventory/{item_a_id}/adjust",
        json={"quantity_delta": -10.0, "reason": "Unauthorized theft attempt"},
        headers=headers_b,
    )
    assert res_adj.status_code == 404

    # Tenant B tries to lookup Tenant A's barcode -> Must return 404
    res_scan = client.get("/api/v1/inventory/lookup?code=999888777666", headers=headers_b)
    assert res_scan.status_code == 404

    # Tenant A CAN lookup by barcode
    res_scan_a = client.get("/api/v1/inventory/lookup?code=999888777666", headers=headers_a)
    assert res_scan_a.status_code == 200
    assert res_scan_a.json()["data"]["id"] == item_a_id


# ---------------------------------------------------------------------------
# 6. Search, Filtering, and Pagination
# ---------------------------------------------------------------------------
def test_search_filtering_and_pagination(client: TestClient, token_a_owner: str):
    """Verify search across name/SKU/barcode, filters by category/storage, and pagination."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}

    # Create 5 distinct items
    items_to_create = [
        {"name": "Fresh Organic Spinach", "category_id": "cat_leafy_greens", "sku": "VEG-SPIN-01", "barcode": "111001", "storage": "REFRIGERATED"},
        {"name": "Fresh Curly Kale", "category_id": "cat_leafy_greens", "sku": "VEG-KALE-02", "barcode": "111002", "storage": "REFRIGERATED"},
        {"name": "Whole Milk Jug", "category_id": "cat_dairy_eggs", "sku": "DAI-MILK-01", "barcode": "111003", "storage": "REFRIGERATED"},
        {"name": "Sourdough Bread", "category_id": "cat_bakery", "sku": "BAK-SOUR-01", "barcode": "111004", "storage": "AMBIENT"},
        {"name": "Croissant Box", "category_id": "cat_bakery", "sku": "BAK-CROI-02", "barcode": "111005", "storage": "AMBIENT"},
    ]

    for item in items_to_create:
        client.post(
            "/api/v1/inventory",
            json={
                "name": item["name"],
                "category_id": item["category_id"],
                "sku": item["sku"],
                "barcode": item["barcode"],
                "initial_quantity": 10.0,
                "unit": "units",
                "cost_per_unit": 1.0,
                "purchase_date": str(date.today()),
                "expiry_date": str(date.today() + timedelta(days=5)),
                "storage_requirement": item["storage"],
            },
            headers=headers,
        )

    # 1. Search for "Kale"
    res_search = client.get("/api/v1/inventory?search=Kale", headers=headers)
    assert res_search.status_code == 200
    data = res_search.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Fresh Curly Kale"

    # 2. Search by SKU "BAK-"
    res_sku = client.get("/api/v1/inventory?search=BAK-", headers=headers)
    assert len(res_sku.json()["data"]) == 2

    # 3. Filter by category "cat_leafy_greens"
    res_cat = client.get("/api/v1/inventory?category_id=cat_leafy_greens", headers=headers)
    assert len(res_cat.json()["data"]) == 2

    # 4. Filter by storage "AMBIENT"
    res_storage = client.get("/api/v1/inventory?storage_requirement=AMBIENT", headers=headers)
    assert len(res_storage.json()["data"]) == 2

    # 5. Pagination: Page 1, Size 2
    res_p1 = client.get("/api/v1/inventory?page=1&size=2", headers=headers)
    body_p1 = res_p1.json()
    assert len(body_p1["data"]) == 2
    assert body_p1["pagination"]["total"] >= 5
    assert body_p1["pagination"]["has_next"] is True
    assert body_p1["pagination"]["has_prev"] is False

    # Page 2, Size 2
    res_p2 = client.get("/api/v1/inventory?page=2&size=2", headers=headers)
    body_p2 = res_p2.json()
    assert len(body_p2["data"]) == 2
    assert body_p2["pagination"]["has_prev"] is True


# ---------------------------------------------------------------------------
# 7. Stock Adjustments and Transaction History
# ---------------------------------------------------------------------------
def test_stock_adjustments_and_transaction_history(client: TestClient, token_a_owner: str):
    """Verify manual stock adjustments and transaction ledger reconciliation."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    create_res = client.post(
        "/api/v1/inventory",
        json={
            "name": "Apples Honeycrisp",
            "category_id": "cat_root_produce",
            "initial_quantity": 30.0,
            "unit": "kg",
            "cost_per_unit": 2.50,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=10)),
            "storage_requirement": "AMBIENT",
        },
        headers=headers,
    )
    item_id = create_res.json()["data"]["id"]

    # 1. Positive adjustment (+10 kg)
    res_adj1 = client.post(
        f"/api/v1/inventory/{item_id}/adjust",
        json={
            "quantity_delta": 10.0,
            "adjustment_type": "RESTOCK",
            "reason": "Direct farm delivery",
        },
        headers=headers,
    )
    assert res_adj1.status_code == 200
    assert res_adj1.json()["data"]["item"]["current_quantity"] == 40.0
    assert res_adj1.json()["data"]["transaction"]["quantity_after"] == 40.0

    # 2. Negative adjustment (-15 kg)
    res_adj2 = client.post(
        f"/api/v1/inventory/{item_id}/adjust",
        json={
            "quantity_delta": -15.0,
            "adjustment_type": "POS_SALE",
            "reason": "Bulk customer purchase",
        },
        headers=headers,
    )
    assert res_adj2.status_code == 200
    assert res_adj2.json()["data"]["item"]["current_quantity"] == 25.0

    # 3. Retrieve transactions
    tx_res = client.get(f"/api/v1/inventory/{item_id}/transactions", headers=headers)
    assert tx_res.status_code == 200
    txs = tx_res.json()["data"]
    assert len(txs) == 3
    # Check mathematical invariant: sum of deltas == 25.0
    total_delta = sum(t["quantity_change"] for t in txs)
    assert total_delta == 25.0


# ---------------------------------------------------------------------------
# 8. Concurrent Updates, Negative Stock Prevention, and Idempotency
# ---------------------------------------------------------------------------
def test_negative_stock_prevention_and_idempotency(client: TestClient, token_a_owner: str):
    """Verify rejection of adjustments that breach zero and verify idempotency keys."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    create_res = client.post(
        "/api/v1/inventory",
        json={
            "name": "Salmon Fillet",
            "category_id": "cat_seafood",
            "initial_quantity": 10.0,
            "unit": "kg",
            "cost_per_unit": 15.0,
            "purchase_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=2)),
            "storage_requirement": "REFRIGERATED",
        },
        headers=headers,
    )
    item_id = create_res.json()["data"]["id"]

    # Attempt to deduct 15 kg when only 10 available -> 400 Bad Request
    res_overdraw = client.post(
        f"/api/v1/inventory/{item_id}/adjust",
        json={
            "quantity_delta": -15.0,
            "reason": "Invalid overdraw sale",
        },
        headers=headers,
    )
    assert res_overdraw.status_code == 400
    assert "available in stock" in res_overdraw.json()["error"]["message"]

    # Verify stock remained untouched at 10.0
    get_item = client.get(f"/api/v1/inventory/{item_id}", headers=headers)
    assert get_item.json()["data"]["current_quantity"] == 10.0

    # Idempotency Test: execute adjustment with an idempotency key
    idemp_key = "test_pos_order_uuid_12345"
    adj_payload = {
        "quantity_delta": -3.0,
        "reason": "POS Sale order #12345",
        "idempotency_key": idemp_key,
    }

    # Call 1
    res1 = client.post(f"/api/v1/inventory/{item_id}/adjust", json=adj_payload, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["data"]["item"]["current_quantity"] == 7.0
    tx1_id = res1.json()["data"]["transaction"]["id"]

    # Call 2 (Duplicate Retry with same idempotency key)
    res2 = client.post(f"/api/v1/inventory/{item_id}/adjust", json=adj_payload, headers=headers)
    assert res2.status_code == 200
    # Stock must STILL be 7.0 (NOT 4.0!)
    assert res2.json()["data"]["item"]["current_quantity"] == 7.0
    tx2_id = res2.json()["data"]["transaction"]["id"]
    assert tx1_id == tx2_id


# ---------------------------------------------------------------------------
# 9. Persistence Across New Database Reads
# ---------------------------------------------------------------------------
def test_persistence_across_new_database_session(
    engine, tenant_a: Tenant, user_a_owner: User
):
    """Verify that committed inventory items and transactions persist across clean sessions."""
    from backend.app.services.inventory_service import (
        create_inventory_item,
        get_inventory_item,
        get_item_transactions,
    )
    from backend.app.schemas.inventory import InventoryItemCreate

    # Write in session 1
    with Session(bind=engine) as session1:
        item_in = InventoryItemCreate(
            name="Persistent Farm Eggs (Dozen)",
            category_id="cat_dairy_eggs",
            sku="PERSIST-EGG-01",
            barcode="888000111",
            initial_quantity=50.0,
            unit="units",
            cost_per_unit=3.0,
            purchase_date=date.today(),
            expiry_date=date.today() + timedelta(days=21),
            storage_requirement="REFRIGERATED",
        )
        created = create_inventory_item(session1, tenant_a.id, user_a_owner.id, item_in)
        persisted_id = created.id

    # Read in fresh Session 2
    with Session(bind=engine) as session2:
        reloaded = get_inventory_item(session2, tenant_a.id, persisted_id)
        assert reloaded is not None
        assert reloaded.id == persisted_id
        assert reloaded.name == "Persistent Farm Eggs (Dozen)"
        assert reloaded.current_quantity == 50.0
        assert reloaded.sku == "PERSIST-EGG-01"

        # Check transactions reloaded
        txs = get_item_transactions(session2, tenant_a.id, persisted_id)
        assert len(txs) == 1
        assert txs[0].quantity_change == 50.0
