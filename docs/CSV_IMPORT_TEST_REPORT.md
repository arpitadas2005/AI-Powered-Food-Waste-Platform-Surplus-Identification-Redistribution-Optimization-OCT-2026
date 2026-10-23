# CSV Ingestion & Data Quality Test Report

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 4 — CSV Ingestion, Raw Data Cleaning and Data Quality Engine  
**Date**: October 23, 2026  
**Test Suite Status**: **12 / 12 PASSING (100%)**  

---

## 1. Test Suite Execution Summary

Executed using `pytest` against an isolated SQLite test environment:
- **Command**: `.\.venv\Scripts\pytest.exe backend/tests/test_csv_ingestion.py -v`
- **Result**: **12 passed, 0 failed in 3.33s**

```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0
rootdir: D:\Waste management
configfile: pytest.ini
collected 12 items

backend/tests/test_csv_ingestion.py::test_download_csv_template PASSED   [  8%]
backend/tests/test_csv_ingestion.py::test_valid_csv_dry_run_vs_commit PASSED [ 16%]
backend/tests/test_csv_ingestion.py::test_missing_required_columns PASSED [ 25%]
backend/tests/test_csv_ingestion.py::test_invalid_dates_and_chronology PASSED [ 33%]
backend/tests/test_csv_ingestion.py::test_negative_and_non_numeric_quantities PASSED [ 41%]
backend/tests/test_csv_ingestion.py::test_unknown_category_rejection PASSED [ 50%]
backend/tests/test_csv_ingestion.py::test_duplicate_sku_detection_in_file_and_database PASSED [ 58%]
backend/tests/test_csv_ingestion.py::test_empty_and_headers_only_file PASSED [ 66%]
backend/tests/test_csv_ingestion.py::test_malformed_encoding_rejection PASSED [ 75%]
backend/tests/test_csv_ingestion.py::test_partial_failure_and_rollback_modes PASSED [ 83%]
backend/tests/test_csv_ingestion.py::test_csv_formula_injection_defense PASSED [ 91%]
backend/tests/test_csv_ingestion.py::test_cross_tenant_import_isolation PASSED [100%]

======================== 12 passed, 1 warning in 3.33s ========================
```

---

## 2. Synthetic Test Fixtures & Verification Matrix (20 Scenarios)

| Fixture ID | Test Scenario | Input Data Pattern | Expected Result | Pass Criteria | Status |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **TF-01** | Download Template | `GET /bulk-import/template` | HTTP 200 `text/csv` | Contains required headers and sample rows. | **PASS** |
| **TF-02** | Valid CSV (Dry-Run) | 3 valid items, `dry_run=true` | HTTP 200, accepted=3 | 0 records created in database. | **PASS** |
| **TF-03** | Valid CSV (Commit) | 3 valid items, `dry_run=false` | HTTP 200, accepted=3 | 3 records created; 3 stock transactions logged. | **PASS** |
| **TF-04** | Missing Required Column | Omitted `unit` header | HTTP 422 `MISSING_HEADERS` | Returns exact missing column list. | **PASS** |
| **TF-05** | Missing Required Value | Row with empty product name | HTTP 200 (report error) | Row rejected with `INVALID_NAME`. | **PASS** |
| **TF-06** | Invalid Date Format | `purchase_date="10/22/2026"` | Row error | Rejected with `INVALID_PURCHASE_DATE`. | **PASS** |
| **TF-07** | Chronological Inversion | `expiry_date < purchase_date` | Row error | Rejected with `EXPIRY_BEFORE_PURCHASE`. | **PASS** |
| **TF-08** | Future Purchase Date | `purchase_date="2099-01-01"` | Row error | Rejected with `FUTURE_PURCHASE_DATE`. | **PASS** |
| **TF-09** | Negative Quantity | `current_quantity="-15.00"` | Row error | Rejected with `INVALID_QUANTITY`. | **PASS** |
| **TF-10** | Non-Numeric Quantity | `current_quantity="twenty"` | Row error | Rejected with `INVALID_QUANTITY`. | **PASS** |
| **TF-11** | Unsupported Unit | `unit="gallons"` | Row error | Rejected with `INVALID_UNIT`. | **PASS** |
| **TF-12** | Unknown Category | `category="extraterrestrial"` | Row error | Rejected with `UNKNOWN_CATEGORY`. | **PASS** |
| **TF-13** | Duplicate SKU in File | Rows 2 and 4 share `SKU-99` | Row error on row 4 | Row 4 rejected with `DUPLICATE_SKU_IN_FILE`. | **PASS** |
| **TF-14** | Database SKU Collision | SKU matches existing item | Row error | Rejected with `EXISTING_SKU_CONFLICT`. | **PASS** |
| **TF-15** | Empty File | 0 bytes payload | HTTP 422 / 400 | Rejects empty upload with descriptive message. | **PASS** |
| **TF-16** | Headers Only File | Header row with 0 data rows | HTTP 200, total_rows=0 | Returns 0 accepted, 0 rejected cleanly. | **PASS** |
| **TF-17** | Corrupted Encoding | Non-UTF8 binary byte stream | HTTP 422 `MALFORMED_ENCODING` | Safe rejection without unhandled exception. | **PASS** |
| **TF-18** | Strict Rollback Mode | 1 valid row + 1 bad row, `allow_partial=false` | Status: `FAILED`, accepted=0 | **Zero** items committed to database. | **PASS** |
| **TF-19** | Partial Import Mode | 1 valid row + 1 bad row, `allow_partial=true` | Status: `COMPLETED`, accepted=1, rejected=1 | Valid item committed; invalid item skipped. | **PASS** |
| **TF-20** | Formula Injection | `name="=cmd|' /C calc'!A0"` | Sanitized on commit | Single quote prepended (`'=cmd...`). | **PASS** |
| **TF-21** | Cross-Tenant Isolation | Tenant A uploads CSV | Checked Tenant B DB | Tenant B contains 0 imported records. | **PASS** |

---

## 3. Performance Benchmark Measurements

Captured using [`backend/tests/run_performance_benchmark.py`](file:///D:/Waste%20management/backend/tests/run_performance_benchmark.py):

| Ingestion Benchmark Scenario | Row Count | Execution Time | Throughput | DB Records Created | Memory Peak |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **CSV Dry-Run Validation** | 500 rows | **128.54 ms** | **3,890 rows/sec** | 0 items | <16 MB |
| **CSV Dry-Run Validation** | 1,000 rows | **189.86 ms** | **5,267 rows/sec** | 0 items | <16 MB |
| **CSV Live Commit (Strict Mode)** | 500 rows | **1,045.09 ms** | **478 rows/sec** | 500 items + 500 stock transactions | <16 MB |

---

## 4. Database Integrity Verification

Direct assertions executed on the test database following import runs:
1. **Committed Row Counts**:
   ```python
   # In test_valid_csv_dry_run_vs_commit:
   items = db_session.execute(select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)).scalars().all()
   assert len(items) == 3
   ```
2. **Stock Transaction Creation**:
   ```python
   # In test_valid_csv_dry_run_vs_commit:
   txs = db_session.execute(select(StockTransaction).where(StockTransaction.tenant_id == tenant_a.id)).scalars().all()
   assert len(txs) == 3
   assert all(tx.reference_type == ReferenceType.CSV_IMPORT_JOB.value for tx in txs)
   ```
3. **Cross-Tenant Segregation**:
   ```python
   # In test_cross_tenant_import_isolation:
   items_a = db_session.execute(select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)).scalars().all()
   items_b = db_session.execute(select(InventoryItem).where(InventoryItem.tenant_id == tenant_b.id)).scalars().all()
   assert len(items_a) == 1
   assert len(items_b) == 0
   ```
4. **Formula Sanitization Check**:
   ```python
   # In test_csv_formula_injection_defense:
   item = db_session.execute(select(InventoryItem).where(InventoryItem.tenant_id == tenant_a.id)).scalar_one()
   assert item.name.startswith("'=")
   assert item.sku.startswith("'+")
   ```
