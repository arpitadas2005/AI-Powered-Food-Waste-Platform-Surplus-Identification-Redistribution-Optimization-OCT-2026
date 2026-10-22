# CSV Ingestion Data Contract & Specification

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 4 — CSV Ingestion and Data Quality  
**Status**: APPROVED SPECIFICATION  

---

## 1. Overview & File Specifications

The CSV ingestion pipeline enables food businesses to bulk import catalog and physical inventory stock into their isolated multi-tenant repository.

### File Requirements & Constraints
- **File Format**: Standard RFC 4180 Comma-Separated Values (CSV).
- **Encoding**: UTF-8 or UTF-8 with BOM (`utf-8-sig`). ASCII is accepted.
- **Max File Size**: 10 Megabytes ($10 \times 1024 \times 1024$ bytes). Files exceeding this limit are rejected with HTTP 413 / 422.
- **Max Row Count**: 10,000 data rows per batch upload.
- **Header Row**: Must be the very first row of the CSV file. Column names are case-insensitive and trimmed of whitespace.

---

## 2. Column Specification

| Column Header | Requirement | Accepted Values / Format | Description & Validation Rules |
| :--- | :---: | :--- | :--- |
| `name` | **Required** | Text (2–255 characters) | Descriptive product name (e.g. `Fresh Organic Spinach 250g`). Cannot be empty or whitespace. |
| `category` | **Required** | Category Slug or Name | Food taxonomy category. Matches either canonical slug (e.g. `dairy-and-eggs`, `leafy-greens-and-soft-produce`) or display name (`Dairy & Eggs`). Case-insensitive. |
| `current_quantity` | **Required** | Non-negative numeric | Physical stock count. Must be a valid positive float or zero ($\ge 0.00$). E.g. `25.50`. |
| `unit` | **Required** | `kg`, `g`, `liters`, `ml`, `units`, `boxes`, `packs` | Measurement unit. Case-insensitive; normalized to lowercase. |
| `purchase_date` | **Required** | `YYYY-MM-DD` | ISO-8601 date when stock was acquired. Cannot be in the future. |
| `expiry_date` | **Required** | `YYYY-MM-DD` | ISO-8601 date. Must be on or after `purchase_date`. |
| `sku` | *Optional* | Alphanumeric (max 100 chars) | Stock Keeping Unit. Must be unique within the tenant's inventory. Duplicate SKUs within the same CSV or conflicting with existing active tenant items are rejected. |
| `barcode` | *Optional* | Digits/Text (max 100 chars) | Scanned UPC-A, EAN-13, or custom QR code string. E.g. `012345678905`. |
| `cost_per_unit` | *Optional* | Non-negative numeric | Acquisition price per unit ($\ge 0.00$). Defaults to `0.00`. |
| `selling_price` | *Optional* | Non-negative numeric | Retail sale price per unit ($\ge 0.00$). Defaults to `null`. |
| `batch_number` | *Optional* | Text (max 100 chars) | Supplier lot or manufacturing batch number. |
| `storage_requirement` | *Optional* | `AMBIENT`, `REFRIGERATED`, `FROZEN`, `DRY_PANTRY`, `CLIMATE_CONTROLLED` | Storage condition. Defaults to category's recommended storage if omitted. |
| `storage_location` | *Optional* | Text (max 100 chars) | Facility location label (e.g. `Chiller A-2`, `Aisle 4 Shelf 3`). |

---

## 3. Ingestion Modes & Execution Policies

The upload endpoint accepts two boolean control parameters:
`POST /api/v1/inventory/bulk-import/csv?dry_run=true|false&allow_partial=true|false`

### 3.1 `dry_run` Mode
- `dry_run = true` (*Default*):
  - Parses the entire file, executes full row-level schema validation, checks duplicate SKUs, and maps categories.
  - **Zero database items are persisted**.
  - Returns a complete diagnostics summary with exact row-by-row error messages and a preview of valid items.
  - Logs a `csv_import_jobs` record with status `DRY_RUN_PASSED` or `DRY_RUN_FAILED`.
- `dry_run = false`:
  - Commits valid records to the database according to the `allow_partial` flag.

### 3.2 Commit Policy (`allow_partial`)
- `allow_partial = false` (*All-or-Nothing / Strict Mode*):
  - If **any** row fails validation or has a duplicate conflict, the entire batch is rolled back atomically.
  - 0 inventory items are inserted.
  - Complete list of row errors is returned for user correction.
  - Status: `FAILED`.
- `allow_partial = true` (*Permissive / Partial Import Mode*):
  - All valid rows are persisted to `inventory_items` and assigned corresponding `stock_transactions` audit logs.
  - Invalid rows are rejected, recorded in `csv_import_row_errors`, and returned in the response report.
  - Status: `COMPLETED` (or `FAILED` if all rows failed).

---

## 4. Security & Untrusted Input Defenses

1. **Tenant Isolation**:
   - The authenticated user's `tenant_id` is extracted from verified JWT credentials and assigned to all created items and jobs.
   - Cross-tenant injection is architecturally impossible; files uploaded in Tenant A's session can only write to Tenant A's database partition.
2. **CSV Formula Injection Defense (CWE-1236)**:
   - Untrusted spreadsheet cells starting with dangerous characters (`=`, `+`, `-`, `@`, `\t`, `\r`) are sanitized by prefixing with a single quote (`'`) to prevent formula execution in external spreadsheet applications.
3. **Memory Safety**:
   - Streaming text parser using Python standard library `csv.DictReader` over decoded in-memory buffers with chunked reading up to 10MB to prevent memory exhaustion.
4. **Idempotency & Audit**:
   - Every import job receives a UUID `job_id`.
   - Every created inventory item generates an initial `StockTransaction` linking `reference_type = "CSV_IMPORT_JOB"` and `reference_id = job.id`.

---

## 5. Sample CSV Content

```csv
name,category,sku,barcode,current_quantity,unit,cost_per_unit,selling_price,purchase_date,expiry_date,storage_requirement,storage_location
Organic Whole Milk 1L,dairy-and-eggs,DAI-MILK-001,012345678905,50,liters,1.20,2.49,2026-10-22,2026-10-28,REFRIGERATED,Walk-in Chiller 1
Fresh Atlantic Salmon,seafood-and-fish,SEA-SALM-002,012345678912,20,kg,14.50,22.00,2026-10-22,2026-10-24,REFRIGERATED,Seafood Counter
Artisan Sourdough Loaf,fresh-bakery-and-pastries,BAK-SOUR-003,012345678929,35,units,1.50,3.99,2026-10-22,2026-10-25,AMBIENT,Bakery Rack B
Baby Spinach 250g,leafy-greens-and-soft-produce,VEG-SPIN-004,012345678936,40,packs,0.90,1.99,2026-10-22,2026-10-27,REFRIGERATED,Produce Chiller 2
```
