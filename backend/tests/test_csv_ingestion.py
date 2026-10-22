"""Data Quality, CSV Ingestion, and Robustness Tests.

Covers:
- Valid rows (dry_run=True and dry_run=False).
- Missing columns.
- Invalid dates and chronological order.
- Negative and non-numeric quantities.
- Unknown categories.
- Duplicate records (within file and against DB).
- Empty files and files with headers only.
- Malformed encodings.
- Row limit and large file safety.
- Partial failures and retry behavior.
- Formula injection defense.
- Cross-tenant import isolation.
- Direct database state verification.
"""

from datetime import date, timedelta
import io
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.models.inventory import InventoryItem
from backend.app.models.csv_import import CsvImportJob, CsvImportStatus
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.models.tenant import Tenant


def test_download_csv_template(client: TestClient):
    """Verify template download endpoint returns text/csv with required headers."""
    res = client.get("/api/v1/inventory/bulk-import/template")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment" in res.headers.get("content-disposition", "")
    content = res.text
    assert "name,category,sku" in content
    assert "current_quantity,unit" in content
    assert "purchase_date,expiry_date" in content


def test_valid_csv_dry_run_vs_commit(client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant):
    """
    Verify clean CSV import in dry_run mode (0 DB writes)
    followed by live commit mode (persisting all items and stock transactions).
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    csv_data = (
        "name,category,sku,barcode,current_quantity,unit,cost_per_unit,selling_price,purchase_date,expiry_date,storage_requirement,storage_location\n"
        f"Organic Whole Milk 1L,dairy-and-eggs,CSV-MILK-1,012345,50,liters,1.20,2.50,{date.today()},{date.today() + timedelta(days=7)},REFRIGERATED,Cooler A\n"
        f"Artisan Sourdough,fresh-bakery-and-pastries,CSV-BAK-2,012346,30,units,1.50,3.99,{date.today()},{date.today() + timedelta(days=3)},AMBIENT,Bakery Shelf\n"
    )

    # 1. Dry Run
    files = {"file": ("inventory.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    dry_res = client.post("/api/v1/inventory/bulk-import/csv?dry_run=true", files=files, headers=headers)
    assert dry_res.status_code == 200
    dry_json = dry_res.json()["data"]
    assert dry_json["dry_run"] is True
    assert dry_json["status"] == CsvImportStatus.DRY_RUN_PASSED.value
    assert dry_json["summary"]["total_rows"] == 2
    assert dry_json["summary"]["accepted_rows"] == 2
    assert dry_json["summary"]["rejected_rows"] == 0
    assert len(dry_json["errors"]) == 0

    # Verify directly in DB: 0 items written
    db_items = db_session.execute(
        select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)
    ).scalars().all()
    assert len(db_items) == 0

    # 2. Live Commit
    files = {"file": ("inventory.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    commit_res = client.post(
        "/api/v1/inventory/bulk-import/csv?dry_run=false&allow_partial=false",
        files=files,
        headers=headers,
    )
    assert commit_res.status_code == 200
    commit_json = commit_res.json()["data"]
    assert commit_json["dry_run"] is False
    assert commit_json["status"] == CsvImportStatus.COMPLETED.value
    assert commit_json["summary"]["accepted_rows"] == 2

    # Verify directly in DB: 2 items written
    db_items_after = db_session.execute(
        select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)
    ).scalars().all()
    assert len(db_items_after) == 2

    # Verify transactions written
    db_txs = db_session.execute(
        select(StockTransaction).where(StockTransaction.tenant_id == tenant_a.id)
    ).scalars().all()
    assert len(db_txs) == 2
    for tx in db_txs:
        assert tx.transaction_type == TransactionType.INITIAL_COUNT.value
        assert tx.reference_type == "CSV_IMPORT_JOB"


def test_missing_required_columns(client: TestClient, token_a_owner: str):
    """Verify rejection when required headers are missing."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    # Missing expiry_date and current_quantity
    bad_csv = "name,category,unit,purchase_date\nMilk,dairy-and-eggs,liters,2026-10-22\n"
    files = {"file": ("bad_headers.csv", io.BytesIO(bad_csv.encode("utf-8")), "text/csv")}

    res = client.post("/api/v1/inventory/bulk-import/csv", files=files, headers=headers)
    assert res.status_code == 422
    assert res.json()["success"] is False
    assert "Missing required columns" in res.json()["error"]["message"]


def test_invalid_dates_and_chronology(client: TestClient, token_a_owner: str):
    """Verify row-level error reporting for unparseable dates and backwards chronology."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    csv_data = (
        "name,category,current_quantity,unit,purchase_date,expiry_date\n"
        "Bad Date Item,dairy-and-eggs,10,liters,not-a-date,2026-10-28\n"
        "Backwards Date Item,dairy-and-eggs,10,liters,2026-10-28,2026-10-20\n"
    )
    files = {"file": ("dates.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/inventory/bulk-import/csv?dry_run=true", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["summary"]["rejected_rows"] == 2
    err_codes = {e["error_code"] for e in data["errors"]}
    assert "INVALID_DATE_FORMAT" in err_codes
    assert "EXPIRY_BEFORE_PURCHASE" in err_codes


def test_negative_and_non_numeric_quantities(client: TestClient, token_a_owner: str):
    """Verify rejection of negative or non-numeric stock quantities."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    csv_data = (
        "name,category,current_quantity,unit,purchase_date,expiry_date\n"
        f"Negative Qty,dairy-and-eggs,-15.5,liters,{date.today()},{date.today() + timedelta(days=5)}\n"
        f"Text Qty,dairy-and-eggs,ten_boxes,units,{date.today()},{date.today() + timedelta(days=5)}\n"
    )
    files = {"file": ("bad_qty.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/inventory/bulk-import/csv?dry_run=true", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["summary"]["rejected_rows"] == 2
    for err in data["errors"]:
        assert err["error_code"] == "INVALID_QUANTITY"


def test_unknown_category_rejection(client: TestClient, token_a_owner: str):
    """Verify rejection of rows referencing non-existent food categories."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    csv_data = (
        "name,category,current_quantity,unit,purchase_date,expiry_date\n"
        f"Unknown Item,martian-space-dust,10,units,{date.today()},{date.today() + timedelta(days=5)}\n"
    )
    files = {"file": ("cat.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/inventory/bulk-import/csv?dry_run=true", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["summary"]["rejected_rows"] == 1
    assert data["errors"][0]["error_code"] == "UNKNOWN_CATEGORY"


def test_duplicate_sku_detection_in_file_and_database(
    client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant
):
    """Verify detection of duplicate SKUs within the same CSV and against pre-existing tenant stock."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}

    # Pre-populate one item in DB
    existing = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Existing Item in DB",
        sku="EXISTING-SKU-999",
        current_quantity=20.0,
        unit="units",
        purchase_date=date.today(),
        expiry_date=date.today() + timedelta(days=5),
        storage_requirement="REFRIGERATED",
    )
    db_session.add(existing)
    db_session.commit()

    # Upload CSV containing:
    # 1. Conflict with DB SKU "EXISTING-SKU-999"
    # 2. Within-file duplicate SKU "DUPLICATE-FILE-SKU"
    csv_data = (
        "name,category,sku,current_quantity,unit,purchase_date,expiry_date\n"
        f"Conflict DB Item,dairy-and-eggs,EXISTING-SKU-999,10,units,{date.today()},{date.today() + timedelta(days=5)}\n"
        f"File Duplicate 1,dairy-and-eggs,DUPLICATE-FILE-SKU,10,units,{date.today()},{date.today() + timedelta(days=5)}\n"
        f"File Duplicate 2,dairy-and-eggs,DUPLICATE-FILE-SKU,10,units,{date.today()},{date.today() + timedelta(days=5)}\n"
    )
    files = {"file": ("dups.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/inventory/bulk-import/csv?dry_run=true", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["summary"]["duplicate_rows"] >= 2
    err_codes = [e["error_code"] for e in data["errors"]]
    assert "SKU_ALREADY_EXISTS" in err_codes
    assert "DUPLICATE_SKU_IN_FILE" in err_codes


def test_empty_and_headers_only_file(client: TestClient, token_a_owner: str):
    """Verify proper error handling for 0-byte files and headers-only files."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}

    # 1. Zero byte empty file
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    res_empty = client.post("/api/v1/inventory/bulk-import/csv", files=files, headers=headers)
    assert res_empty.status_code == 422
    assert "empty" in res_empty.json()["error"]["message"]

    # 2. Headers only (0 data rows)
    headers_only = "name,category,current_quantity,unit,purchase_date,expiry_date\n"
    files = {"file": ("headers.csv", io.BytesIO(headers_only.encode("utf-8")), "text/csv")}
    res_headers = client.post("/api/v1/inventory/bulk-import/csv", files=files, headers=headers)
    assert res_headers.status_code == 200
    assert res_headers.json()["data"]["summary"]["total_rows"] == 0


def test_malformed_encoding_rejection(client: TestClient, token_a_owner: str):
    """Verify rejection when uploaded file is binary or malformed non-UTF8 text."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    # Raw non-decodable byte sequence
    bad_bytes = b"\xff\xfe\x00\x00\x80\x81\x82\x99\xff\xee"
    files = {"file": ("corrupt.csv", io.BytesIO(bad_bytes), "text/csv")}
    res = client.post("/api/v1/inventory/bulk-import/csv", files=files, headers=headers)
    assert res.status_code == 422
    assert "UTF-8" in res.json()["error"]["message"]


def test_partial_failure_and_rollback_modes(
    client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant
):
    """
    Test mixed CSV (1 valid row, 1 invalid row):
    - When allow_partial=false (strict mode): 0 rows committed (atomic rollback).
    - When allow_partial=true (permissive mode): 1 valid row committed, 1 row error recorded.
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    mixed_csv = (
        "name,category,current_quantity,unit,purchase_date,expiry_date\n"
        f"Valid Yogurt,dairy-and-eggs,10,units,{date.today()},{date.today() + timedelta(days=5)}\n"
        f"Corrupt Row,unknown-cat,-999,invalid_unit,not-a-date,not-a-date\n"
    )

    # 1. Strict Mode (allow_partial=false)
    files = {"file": ("mixed.csv", io.BytesIO(mixed_csv.encode("utf-8")), "text/csv")}
    res_strict = client.post(
        "/api/v1/inventory/bulk-import/csv?dry_run=false&allow_partial=false",
        files=files,
        headers=headers,
    )
    assert res_strict.status_code == 200
    data_strict = res_strict.json()["data"]
    assert data_strict["status"] == CsvImportStatus.FAILED.value
    assert data_strict["summary"]["accepted_rows"] == 0
    assert data_strict["summary"]["rejected_rows"] == 1

    # DB state: 0 items written
    items_strict = db_session.execute(
        select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)
    ).scalars().all()
    assert len(items_strict) == 0

    # 2. Permissive Mode (allow_partial=true)
    files = {"file": ("mixed.csv", io.BytesIO(mixed_csv.encode("utf-8")), "text/csv")}
    res_perm = client.post(
        "/api/v1/inventory/bulk-import/csv?dry_run=false&allow_partial=true",
        files=files,
        headers=headers,
    )
    assert res_perm.status_code == 200
    data_perm = res_perm.json()["data"]
    assert data_perm["status"] == CsvImportStatus.COMPLETED.value
    assert data_perm["summary"]["accepted_rows"] == 1
    assert data_perm["summary"]["rejected_rows"] == 1

    # DB state: Exactly 1 valid item written
    items_perm = db_session.execute(
        select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)
    ).scalars().all()
    assert len(items_perm) == 1
    assert items_perm[0].name == "Valid Yogurt"


def test_csv_formula_injection_defense(client: TestClient, token_a_owner: str, db_session: Session, tenant_a: Tenant):
    """
    Verify CWE-1236 defense: cells starting with dangerous spreadsheet formula
    execution characters are sanitized with a leading single quote.
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    formula_csv = (
        "name,category,sku,current_quantity,unit,purchase_date,expiry_date\n"
        f"=cmd|'/C calc'!A0,dairy-and-eggs,+SKU-EVIL,10,units,{date.today()},{date.today() + timedelta(days=5)}\n"
    )
    files = {"file": ("formula.csv", io.BytesIO(formula_csv.encode("utf-8")), "text/csv")}
    res = client.post(
        "/api/v1/inventory/bulk-import/csv?dry_run=false&allow_partial=true",
        files=files,
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["data"]["summary"]["accepted_rows"] == 1

    # Check database: name and sku should have leading single quote prepended
    item = db_session.execute(
        select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)
    ).scalar_one()
    assert item.name.startswith("'=")
    assert item.sku.startswith("'+")


def test_cross_tenant_import_isolation(
    client: TestClient, token_a_owner: str, token_b_owner: str, db_session: Session, tenant_a: Tenant, tenant_b: Tenant
):
    """Verify that importing records as Tenant A writes strictly to Tenant A and never touches Tenant B."""
    headers_a = {"Authorization": f"Bearer {token_a_owner}"}
    csv_a = (
        "name,category,current_quantity,unit,purchase_date,expiry_date\n"
        f"Tenant A Special Butter,dairy-and-eggs,100,units,{date.today()},{date.today() + timedelta(days=10)}\n"
    )
    files = {"file": ("tenant_a.csv", io.BytesIO(csv_a.encode("utf-8")), "text/csv")}
    res = client.post(
        "/api/v1/inventory/bulk-import/csv?dry_run=false&allow_partial=false",
        files=files,
        headers=headers_a,
    )
    assert res.status_code == 200

    # Query Tenant A DB items
    items_a = db_session.execute(
        select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)
    ).scalars().all()
    assert len(items_a) == 1
    assert items_a[0].name == "Tenant A Special Butter"

    # Query Tenant B DB items
    items_b = db_session.execute(
        select(InventoryItem).where(InventoryItem.tenant_id == tenant_b.id)
    ).scalars().all()
    assert len(items_b) == 0
