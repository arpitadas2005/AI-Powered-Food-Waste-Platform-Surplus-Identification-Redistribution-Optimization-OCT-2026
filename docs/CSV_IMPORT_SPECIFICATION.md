# CSV Import Specification & Pipeline Architecture

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 4 — CSV Ingestion, Raw Data Cleaning and Data Quality Engine  
**Status**: APPROVED SPECIFICATION  

---

## 1. Overview & Ingestion Architecture

The CSV Ingestion Pipeline enables business users to bulk-import physical inventory and product catalog records safely into their isolated multi-tenant database partition. The pipeline is designed around an ordered multi-stage architecture guaranteeing data quality, tenant boundary enforcement, and stock ledger integrity.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Uploaded CSV File (RFC 4180 / UTF-8)                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Stage A: File Validation (Size <= 10MB, UTF-8 / UTF-8-BOM, MIME)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Stage B: Raw Parsing & Header Matching (DictReader, Case-Insensitive)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Stage C: Data Profiling & Duplicate Detection (File & DB SKU conflicts)│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Stage D: Normalization & Cleaning (Trim, Unit/Category canonical map)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Stage E: Validation & Formula Sanitization (CWE-1236, Bounds, Dates)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Stage F: Preview & Diagnostic Generation (Row error reporting table)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
             ┌──────────────────────┴──────────────────────┐
             │ Dry-Run = True                              │ Dry-Run = False
             ▼                                             ▼
┌───────────────────────────────┐             ┌──────────────────────────┐
│ Return Preview & Error Report │             │ Stage G: Persistence     │
│ (Zero Database Changes)       │             │ (Strict vs. Partial Mode)│
└───────────────────────────────┘             └────────────┬─────────────┘
                                                           │
                                                           ▼
                                              ┌──────────────────────────┐
                                              │ Stage H: Audit & Ledger  │
                                              │ (Job log + Stock Tx)     │
                                              └──────────────────────────┘
```

---

## 2. Supported Columns & Schema Mapping

| Column Header | Requirement | Accepted Values / Formats | Validation & Normalization Rules |
| :--- | :---: | :--- | :--- |
| `name` | **Required** | Text (2–255 chars) | Stripped of whitespace. Sanitized against formula injection. Must be non-empty. |
| `category` | **Required** | Slug or Display Name | Matched case-insensitively against canonical slug (`dairy-and-eggs`) or display name (`Dairy & Eggs`). Mapped to `category_id`. |
| `current_quantity` | **Required** | Numeric ($\ge 0.00$) | Must be a valid non-negative float. Decimals permitted (e.g. `12.50`). Negative or non-numeric values rejected. |
| `unit` | **Required** | `kg`, `g`, `liters`, `ml`, `units`, `boxes`, `packs` | Normalized to lowercase standard units. Unsupported units rejected with `INVALID_UNIT`. |
| `purchase_date` | **Required** | `YYYY-MM-DD` | Valid ISO-8601 calendar date. Cannot be in the future. |
| `expiry_date` | **Required** | `YYYY-MM-DD` | Valid ISO-8601 calendar date. Must be $\ge$ `purchase_date`. |
| `sku` | *Optional* | Alphanumeric (max 100 chars) | Unique identifier within tenant. Checked for duplicates within file and against active database items. |
| `barcode` | *Optional* | Numeric/Text (max 100 chars) | Scanned UPC-A, EAN-13, Code 128, or internal QR code string. |
| `cost_per_unit` | *Optional* | Numeric ($\ge 0.00$) | Acquisition cost per unit. Defaults to `0.00` if omitted. |
| `selling_price` | *Optional* | Numeric ($\ge 0.00$) | Intended retail price. Stored as `null` if omitted. |
| `batch_number` | *Optional* | Text (max 100 chars) | Supplier lot or manufacturing batch number. |
| `storage_requirement` | *Optional* | `AMBIENT`, `REFRIGERATED`, `FROZEN`, `DRY_PANTRY`, `CLIMATE_CONTROLLED` | Storage condition. If omitted, automatically inherits recommended storage from mapped Category. |
| `storage_location` | *Optional* | Text (max 100 chars) | Location label within facility (e.g. `Walk-in Chiller 1`, `Aisle 3`). |

---

## 3. Ingestion Pipeline Execution Policy

The endpoint operates at:
`POST /api/v1/inventory/bulk-import/csv?dry_run=true|false&allow_partial=true|false`

### 3.1 Dry-Run Simulation (`dry_run=true`)
- Executes all validation, category mapping, date chronology checks, and conflict detection without writing records to `inventory_items` or `stock_transactions`.
- Creates a `csv_import_jobs` record with status `DRY_RUN_PASSED` (if 0 errors) or `DRY_RUN_FAILED` (if errors found).
- Returns the complete diagnostic error array and a 5-item sample preview of normalized valid rows.

### 3.2 Commit Policy (`dry_run=false`)
- **Strict All-or-Nothing Mode (`allow_partial=false`)**:
  - If **any** row in the file fails validation or generates a conflict, the entire batch is rejected.
  - Zero inventory records are created.
  - All row-level errors are persisted to `csv_import_row_errors` and returned in the HTTP response.
  - Job status: `FAILED`.
- **Permissive Partial Mode (`allow_partial=true`)**:
  - Valid rows are committed atomically to `inventory_items`.
  - For every created item, an initial `StockTransaction` (`INITIAL_COUNT`) is recorded linking `reference_type = "CSV_IMPORT_JOB"` and `reference_id = job.id`.
  - Invalid rows are rejected, recorded in `csv_import_row_errors`, and returned in the response summary.
  - Job status: `COMPLETED` (or `FAILED` if 0 rows succeeded).

---

## 4. Security & Safety Controls

1. **Strict Multi-Tenancy**: The tenant ownership is extracted directly from the authenticated JWT claims. Client requests cannot specify or override `tenant_id`.
2. **Formula Injection Defense (CWE-1236)**: Any cell beginning with dangerous formula characters (`=`, `+`, `-`, `@`, `\t`, `\r`) is prepended with a single quote (`'`) to neutralize dynamic spreadsheet execution in Excel/Google Sheets.
3. **Resource Protection**: Maximum file size 10MB; maximum row limit 10,000 rows per upload to protect memory and database connection pools.
4. **Encoding Resilience**: Supports UTF-8, UTF-8 with BOM (`utf-8-sig`), and Latin-1/ISO-8859-1 fallback.
