# Milestone 1 Acceptance Test Specification

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Document**: Test Cases, Test Scenarios & Verification Matrix  
**Phase**: Phase 1 — Detailed Design  

---

## 1. Test Suite Overview

This document specifies the complete test suite required to verify Milestone 1. Tests are divided into 8 focused categories:
1. **Schema Validation & Input Boundaries** (`TC-VAL-*`)
2. **Authentication & Authorization / RBAC** (`TC-AUTH-*`)
3. **Multi-Tenant Data Isolation & Security** (`TC-TENANT-*`)
4. **Duplicate Records & Uniqueness Constraints** (`TC-UNIQ-*`)
5. **Date Boundaries & Expiry Evaluation** (`TC-EXPIRY-*`)
6. **Stock Ledger Integrity & Invariants** (`TC-LEDGER-*`)
7. **CSV Bulk Import & Failure Diagnostics** (`TC-CSV-*`)
8. **POS Webhook Integration & External Failure Modes** (`TC-POS-*`)

---

## 2. Test Case Specifications

### 2.1 Category 1: Schema Validation & Input Boundaries

| Test ID | Test Scenario | Input / Action | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| `TC-VAL-001` | Valid inventory item creation | `POST /api/v1/inventory` with complete valid payload (`name="Milk"`, `qty=10`, `unit="liters"`, `purchase_date="2026-10-22"`, `expiry_date="2026-10-27"`) | HTTP 201 Created | Item created with UUID, `status="ACTIVE"`, initial stock transaction recorded. |
| `TC-VAL-002` | Reject empty or whitespace-only product name | `POST /api/v1/inventory` with `name="   "` | HTTP 422 Unprocessable Entity | Error envelope contains `field="name"` with validation explanation. |
| `TC-VAL-003` | Reject negative initial quantity | `POST /api/v1/inventory` with `initial_quantity=-5.00` | HTTP 422 Unprocessable Entity | Error envelope specifies quantity must be $\ge 0$. |
| `TC-VAL-004` | Reject unsupported measurement unit | `POST /api/v1/inventory` with `unit="lightyears"` | HTTP 422 Unprocessable Entity | Error specifies `unit` must be one of `kg`, `g`, `liters`, `ml`, `units`, `boxes`, `packs`. |
| `TC-VAL-005` | Reject negative cost or selling price | `POST /api/v1/inventory` with `cost_per_unit=-1.50` | HTTP 422 Unprocessable Entity | Cost field rejected with value bounds message. |
| `TC-VAL-006` | Reject non-existent category ID | `POST /api/v1/inventory` with `category_id="non_existent_uuid"` | HTTP 404 / 422 | Foreign key validation failure handled cleanly without database crash. |
| `TC-VAL-007` | Stock adjustment exceeding available quantity | `POST /api/v1/inventory/{id}/adjust` with `quantity_delta=-100` on item with `current_quantity=20` | HTTP 400 Bad Request / 422 | Rejects reduction that would yield negative physical inventory. |
| `TC-VAL-008` | Stock adjustment without reason | `POST /api/v1/inventory/{id}/adjust` with `quantity_delta=-2` and `reason=""` | HTTP 422 Unprocessable Entity | Operational justification mandatory on manual adjustments. |

---

### 2.2 Category 2: Authentication & Authorization (RBAC)

| Test ID | Test Scenario | Input / Action | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| `TC-AUTH-001` | Unauthenticated access to private inventory | `GET /api/v1/inventory` with missing `Authorization` header | HTTP 401 Unauthorized | Standard error code `UNAUTHORIZED`. |
| `TC-AUTH-002` | Tampered JWT access token | `GET /api/v1/inventory` with modified signature token | HTTP 401 Unauthorized | Cryptographic signature verification rejects altered payload. |
| `TC-AUTH-003` | Expired JWT access token | `GET /api/v1/inventory` with token whose `exp` is in the past | HTTP 401 Unauthorized | Error message indicates token expired; advises refresh. |
| `TC-AUTH-004` | Staff role restricted from deleting items | `DELETE /api/v1/inventory/{id}` executed by user with role `INVENTORY_STAFF` | HTTP 403 Forbidden | Only `STORE_MANAGER` and `BUSINESS_OWNER` can delete inventory items. |
| `TC-AUTH-005` | Staff role restricted from viewing audit ledger | `GET /api/v1/transactions` executed by user with role `INVENTORY_STAFF` | HTTP 403 Forbidden | Rejects access; audit logs reserved for managers and owners. |
| `TC-AUTH-006` | Staff role permitted for barcode quick-scan | `POST /api/v1/inventory/quick-scan-action` executed by `INVENTORY_STAFF` | HTTP 200 OK | Stock increment succeeds with staff member recorded as author. |
| `TC-AUTH-007` | NGO user restricted from business inventory write | `POST /api/v1/inventory` executed by user with role `RECIPIENT_NGO` | HTTP 403 Forbidden | Dual-sided separation enforced; NGO accounts cannot create donor stock. |
| `TC-AUTH-008` | Login rate limiting on repeated failures | 6 consecutive failed logins from single IP within 60 seconds | HTTP 429 Too Many Requests | Brute-force protection triggers on 6th attempt with `Retry-After` header. |

---

### 2.3 Category 3: Multi-Tenant Data Isolation

| Test ID | Test Scenario | Input / Action | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| `TC-TENANT-001` | Cross-tenant inventory list segregation | Tenant A creates 5 items. Tenant B authenticates and calls `GET /api/v1/inventory`. | HTTP 200 OK | Response contains exactly 0 items belonging to Tenant A. |
| `TC-TENANT-002` | Cross-tenant direct read rejection | Tenant B attempts `GET /api/v1/inventory/{item_id_from_tenant_a}` | HTTP 404 Not Found | Returns 404 (not 403) to prevent ID enumeration across tenants. |
| `TC-TENANT-003` | Cross-tenant patch modification rejection | Tenant B attempts `PATCH /api/v1/inventory/{item_id_from_tenant_a}` with new price | HTTP 404 Not Found | Tenant A's item remains completely unchanged in database. |
| `TC-TENANT-004` | Cross-tenant deletion rejection | Tenant B attempts `DELETE /api/v1/inventory/{item_id_from_tenant_a}` | HTTP 404 Not Found | Tenant A's item remains active and unmodified. |
| `TC-TENANT-005` | Cross-tenant barcode lookup segregation | Tenant A registers item with barcode `123456`. Tenant B calls `GET /api/v1/inventory/lookup?code=123456`. | HTTP 404 Not Found (`BARCODE_UNREGISTERED`) | Tenant B cannot detect or access Tenant A's item by barcode. |
| `TC-TENANT-006` | Tenant context spoofing in body | Tenant B sends `POST /api/v1/inventory` with explicit `"tenant_id": "tenant_a_uuid"` in payload | HTTP 201 Created | Created item has `tenant_id` set to Tenant B's UUID from JWT token. Tenant A cannot see it. |
| `TC-TENANT-007` | Cross-tenant audit ledger isolation | Tenant B queries `GET /api/v1/transactions` | HTTP 200 OK | All returned transaction entries strictly have `tenant_id == tenant_b_uuid`. |

---

### 2.4 Category 4: Duplicate Records & Uniqueness Constraints

| Test ID | Test Scenario | Input / Action | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| `TC-UNIQ-001` | Duplicate SKU within same tenant | Tenant A creates item with `sku="SKU-100"`, then attempts creating second item with `sku="SKU-100"` | HTTP 409 Conflict | Uniqueness constraint prevents duplicate SKU within same tenant. |
| `TC-UNIQ-002` | Identical SKU across different tenants permitted | Tenant A has item with `sku="SKU-100"`. Tenant B creates item with `sku="SKU-100"`. | HTTP 201 Created | Both items exist independently without collision. |
| `TC-UNIQ-003` | Duplicate user email registration | Attempt `POST /api/v1/auth/register` with an email address already registered | HTTP 409 Conflict | Returns `EMAIL_ALREADY_EXISTS`; no duplicate user or tenant created. |
| `TC-UNIQ-004` | Duplicate tenant business slug | Attempt registering two businesses whose names generate the same slug | HTTP 201 Created | Auto-slugifier appends unique numerical suffix (e.g., `market-1`, `market-2`). |
| `TC-UNIQ-005` | Multiple null SKUs permitted | Tenant creates 3 items with `sku=null` | HTTP 201 Created | Null SKUs allowed without triggering unique index collision. |

---

### 2.5 Category 5: Date Boundaries & Expiry Evaluation

| Test ID | Test Scenario | Input / Action | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| `TC-EXPIRY-001` | Reject expiry date prior to purchase date | `POST /api/v1/inventory` with `purchase_date="2026-10-22"` and `expiry_date="2026-10-20"` | HTTP 422 Unprocessable Entity | Constraint `chk_expiry_after_purchase` blocks invalid chronological order. |
| `TC-EXPIRY-002` | Item expiring on current date | Item with `expiry_date = today` evaluated by expiry engine | Severity: `CRITICAL` | Calculated days remaining is $\le 1.0$; item flagged with critical alert. |
| `TC-EXPIRY-003` | Item past expiration date | Item with `expiry_date = yesterday` | Severity: `EXPIRED` | Calculated days remaining $\le 0$; status updated to `EXPIRED`. |
| `TC-EXPIRY-004` | Item within warning threshold | Tenant threshold = 3 days; item expires in 2.5 days | Severity: `EXPIRING_SOON` | Appears in `GET /api/v1/inventory/expiring?status=EXPIRING_SOON`. |
| `TC-EXPIRY-005` | Item outside warning threshold | Item expires in 10 days; tenant warning threshold = 3 days | Severity: `GOOD` | Does not trigger alert notifications or warning banners. |
| `TC-EXPIRY-006` | Leap year date handling | Item created with `purchase_date="2028-02-28"` and `expiry_date="2028-02-29"` | HTTP 201 Created | Validates Feb 29 on leap year; rejects Feb 29 on non-leap year (`2027-02-29` $\to$ 422). |
| `TC-EXPIRY-007` | UTC midnight transition | Evaluate item expiring at `00:00:00Z` from different tenant timezones | Deterministic calculation | Expiry evaluation respects tenant configured timezone. |

---

### 2.6 Category 6: Stock Ledger Mathematical Invariants

| Test ID | Test Scenario | Input / Action | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| `TC-LEDGER-001` | Initial stock transaction creation | Create item with `initial_quantity=50.00` | HTTP 201 Created | One row created in `stock_transactions` with `type="INITIAL_COUNT"`, `before=0`, `delta=+50`, `after=50`. |
| `TC-LEDGER-002` | Sequential stock adjustments reconciliation | Execute 3 adjustments: `+20`, `-15`, `-5` on initial 50 stock | Final stock = 50 | Transaction ledger has 4 entries; sum of `quantity_change` ($50 + 20 - 15 - 5 = 50$) matches `current_quantity`. |
| `TC-LEDGER-003` | Immutable transaction log | Direct attempt to execute `UPDATE stock_transactions` or `DELETE stock_transactions` | Operational / ORM Error | Database trigger or repository rules prevent modifying or deleting ledger entries. |
| `TC-LEDGER-004` | Surplus donation hold allocation | Earmark 15 units of 50 available stock for donation listing | HTTP 201 Created | Available retail stock decrements to 35; transaction recorded with `type="DONATION_HOLD"`, `delta=-15`. |

---

### 2.7 Category 7: CSV Bulk Import & Failure Diagnostics

| Test ID | Test Scenario | Input / Action | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| `TC-CSV-001` | Clean CSV import in dry-run mode | Upload valid 50-row CSV with `dry_run=true` | HTTP 200 OK | Returns summary `total=50, success=50, failed=0`; 0 items added to database. |
| `TC-CSV-002` | Clean CSV import commit mode | Upload valid 50-row CSV with `dry_run=false` | HTTP 200 OK | 50 items persisted in database; 50 ledger entries recorded. |
| `TC-CSV-003` | Missing mandatory column headers | Upload CSV missing `expiry_date` header | HTTP 422 Unprocessable Entity | Rejection with clear message identifying missing mandatory headers. |
| `TC-CSV-004` | Row-level validation failure in strict mode | Upload CSV with 1 invalid date on Row 12, with `allow_partial=false` | HTTP 422 / Rollback | Complete transaction rolled back; 0 items inserted; row 12 error details returned. |
| `TC-CSV-005` | Row-level validation failure in partial mode | Upload CSV with 1 invalid date on Row 12, with `allow_partial=true` | HTTP 200 OK | 49 valid items inserted; row 12 returned in `errors` list with code `INVALID_DATE_FORMAT`. |
| `TC-CSV-006` | Formula injection defense in CSV cells | Upload CSV with item name `=cmd|'/C calc'!A0` | HTTP 200 OK | Cell escaped with single quote prefix; prevented from executing in spreadsheet viewers. |
| `TC-CSV-007` | Large batch performance | Upload 1,000 row valid CSV | HTTP 200 OK | Completed in $<2.5$ seconds using bulk insert operations. |

---

### 2.8 Category 8: POS Webhook Integration & External Failure Modes

| Test ID | Test Scenario | Input / Action | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| `TC-POS-001` | Valid POS order webhook sale | Send signed Square webhook with 2 units of SKU `DAI-MILK-001` | HTTP 200 OK | Matching item stock decrements by 2; transaction recorded with `type="POS_SALE"`. |
| `TC-POS-002` | Invalid HMAC signature rejection | Send POS webhook with modified or missing `X-POS-Signature` header | HTTP 401 Unauthorized | Request immediately aborted without parsing payload body or altering stock. |
| `TC-POS-003` | Idempotent duplicate webhook event | Send identical webhook payload with same `X-Idempotency-Key` twice | HTTP 200 OK | Second call returns `ALREADY_PROCESSED`; inventory is decremented only once. |
| `TC-POS-004` | Unmatched SKU in POS order | Webhook contains SKU `UNKNOWN-SKU-999` not present in inventory | HTTP 200 OK | Webhook does not crash; event logged in triage queue for manual staff mapping. |
| `TC-POS-005` | Partial SKU match in multi-item order | Order has 1 valid SKU and 1 unmatched SKU | HTTP 200 OK | Valid SKU stock decremented; unmatched SKU flagged in response diagnostics. |
