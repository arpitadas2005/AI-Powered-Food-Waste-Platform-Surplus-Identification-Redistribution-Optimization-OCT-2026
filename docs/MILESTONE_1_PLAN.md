# MILESTONE 1 PLAN: INVENTORY MANAGEMENT & EXPIRY TRACKING SYSTEM

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Document**: Milestone 1 Implementation Plan & Architecture Specification  
**Phase**: Phase 1 — Detailed Design Complete  
**Date**: October 2026  
**Status**: DETAILED DESIGN COMPLETE / PENDING IMPLEMENTATION APPROVAL  

---

## 0. Phase 1 Detailed Design Artifacts

The detailed architectural design and specifications for Milestone 1 are documented in dedicated specifications:
- **Database Schema**: [DATABASE_SCHEMA.md](file:///D:/Waste%20management/docs/DATABASE_SCHEMA.md) (11 entities, field types, constraints, ER diagram, indexes)
- **API Contracts**: [API_CONTRACTS.md](file:///D:/Waste%20management/docs/API_CONTRACTS.md) (Endpoints, request/response schemas, pagination, error envelopes)
- **Security Design**: [SECURITY_DESIGN.md](file:///D:/Waste%20management/docs/SECURITY_DESIGN.md) (Multi-tenancy, RBAC, HMAC webhook security, input sanitization)
- **Acceptance Tests**: [PHASE_1_ACCEPTANCE_TESTS.md](file:///D:/Waste%20management/docs/PHASE_1_ACCEPTANCE_TESTS.md) (42 test cases across 8 test suites)  

---

## 1. Executive Summary & Current Repository State

This document establishes the architectural baseline, gap analysis, and implementation roadmap for **Milestone 1 (Weeks 1–2: Inventory Management & Expiry Tracking System)** of the AI-Powered Food Waste Management Platform.

### 1.1 Repository State
- **Workspace Directory**: `D:\Waste management`
- **Current State**: Greenfield repository (0 files, 0 directories initialized).
- **Git Repository**: Not initialized.
- **Runtimes Detected**:
  - Python: `3.13.5` (global environment has `fastapi 0.139.0`, `SQLAlchemy 2.0.51`, `pydantic 2.13.4`, `pytest 9.1.1`, `uvicorn 0.49.0`, `scikit-learn 1.9.0`, `numpy 2.5.0`, `passlib 1.7.4`, `python-jose 3.5.0`, `httpx 0.28.1`).
  - Node.js: `v24.18.0`.
  - npm: `11.16.0` (accessible via `npm.cmd` / `npx.cmd`; PowerShell execution policy blocks `.ps1`).
  - SQLite: `3.49.1` (built into Python standard library).
  - External services: Docker, `mongod`, and `psql` are not installed in the Windows system PATH.
- **Feature Status Summary**: All 11 Milestone 1 functional requirements are currently **MISSING** in this workspace and must be implemented following the verified architecture defined herein.

---

## 2. Baseline Test & Build Report

Prior to code authoring, the following baseline commands were executed to establish ground truth:

| Command Executed | Exit Code | Result / Output | Diagnostic Analysis |
| :--- | :--- | :--- | :--- |
| `pytest` | `1` | `collected 0 items / no tests ran in 0.02s` | No test suites exist in root. Expected for greenfield repo. |
| `npm.cmd test` | `1` | `npm error enoent Could not read package.json` | `package.json` does not exist yet. |
| `npm.cmd run build` | `1` | `npm error enoent Could not read package.json` | Build script unavailable; repository uninitialized. |
| `git status` | `128` | `fatal: not a git repository` | Git version control not yet initialized. |
| `python -c "import sqlite3; print(sqlite3.sqlite_version)"` | `0` | `3.49.1` | Embedded SQLite engine is verified and available. |

---

## 3. Architecture Assessment & Technology Selection

### 3.1 Technology Stack Recommendation (Minimal Safe Footprint)
To avoid unnecessary operational complexity while maintaining high performance, enterprise modularity, and strict multi-tenancy:
1. **Backend**:
   - **Framework**: `FastAPI` (Python 3.13) with asynchronous route handlers and Pydantic v2 schemas.
   - **ORM / Database Access**: `SQLAlchemy 2.0` with mapped dataclass models and session dependency injection.
   - **Database Engine**: Dual-mode engine:
     - Development/Testing: SQLite (`sqlite:///./waste_management.db` or in-memory `:memory:`) with `foreign_keys=ON` WAL mode.
     - Production: PostgreSQL (`postgresql+psycopg://...`).
   - **Auth**: Stateless JWT tokens (via `python-jose`) with bcrypt password hashing (`passlib[bcrypt]`), plus SHA-256 hashed API Keys for POS integrations.
2. **Frontend**:
   - **Framework**: `Next.js` (App Router, React 19, TypeScript).
   - **Styling**: `Tailwind CSS` for responsive, accessible UI components.
   - **Icons**: `lucide-react`.
   - **Camera / Scanning**: HTML5 Barcode Detection API with `html5-qrcode` fallback for cross-browser mobile scanning.
3. **Database Architecture & Multi-Tenancy**:
   - Shared-database, shared-schema pattern with strict **Row-Level Tenant Isolation** (`tenant_id` foreign key on every business entity).
   - Automated SQLAlchemy session enforcement: all queries filter on active `tenant_id` extracted from the authenticated JWT session or API key.

### 3.2 Subsystem Architecture Breakdown

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Next.js Mobile-Friendly Web Client                   │
│  (Inventory Table, CSV Uploader, Camera Scanner, Expiry Alerts, POS)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS / REST JSON
┌───────────────────────────────────▼────────────────────────────────────┐
│                        FastAPI API Gateway                             │
│  ┌───────────────────────┬──────────────────────┬───────────────────┐  │
│  │ JWT & RBAC Middleware │ Tenant Context Dep   │ Error Handler     │  │
│  └───────────────────────┴──────────────────────┴───────────────────┘  │
│  ┌──────────────┬──────────────┬──────────────┬───────────┬─────────┐  │
│  │ Auth & Users │ Inventory    │ CSV Importer │ POS Sync  │ Alerts  │  │
│  └──────┬───────┴──────┬───────┴──────┬───────┴─────┬─────┴────┬────┘  │
└─────────┼──────────────┼──────────────┼─────────────┼──────────┼───────┘
          │              │              │             │          │
┌─────────▼──────────────▼──────────────▼─────────────▼──────────▼───────┐
│               Service Layer & Business Domain Logic                    │
│  - Tenant Isolation Enforcer                                           │
│  - Expiry Engine (Days-to-Expiry, Dynamic Severity Classification)     │
│  - Food Categorization & Storage Temperature Compliance Rules          │
│  - Immutable Stock Transaction Ledger (Audit Trail)                    │
│  - POS Adapter Interface (Square, Clover, Generic Webhooks)            │
│  - Surplus Listing & Donation Hold Foundation                          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ SQLAlchemy 2.0 ORM
┌───────────────────────────────────▼────────────────────────────────────┐
│                     Relational Database Layer                          │
│     (PostgreSQL in Production / SQLite in Local Dev & Pytest)          │
│  Tables: tenants, users, categories, inventory_items,                  │
│          stock_transactions, surplus_listings, pos_integrations        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Comprehensive Requirement-by-Requirement Plan

### Requirement 1: Manual Inventory Entry and Editing
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/models/inventory.py`
  - `backend/app/schemas/inventory.py`
  - `backend/app/api/v1/inventory.py`
  - `backend/app/services/inventory_service.py`
  - `frontend/src/app/inventory/page.tsx`
  - `frontend/src/components/inventory/ItemFormModal.tsx`
  - `frontend/src/components/inventory/InventoryTable.tsx`
- **Missing Dependencies**: Frontend scaffolding, backend inventory router & CRUD services.
- **Implementation Plan**:
  - Implement full CRUD REST API endpoints (`POST`, `GET`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`).
  - Pydantic schema validation: non-empty name, positive quantity, valid units (`kg`, `g`, `liters`, `units`, `packs`), price $\ge 0$, valid date range (`expiry_date` $\ge$ `purchase_date`).
  - Automatic creation of an initial `STOCK_IN` transaction entry upon item creation.
  - Patch updates recalculate stock variance and create adjustment transaction records.
- **Acceptance Criteria**:
  - Business users can add and edit food items with immediate validation.
  - Cross-tenant edit or deletion attempts return HTTP 404/403.
- **Required Tests**:
  - Unit tests for Pydantic schema validation (negative quantities, invalid date ranges).
  - Integration tests for inventory CRUD and tenant boundaries.
  - UI form validation and submission tests.

---

### Requirement 2: CSV Bulk Import with Row-Level Validation
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/services/csv_service.py`
  - `backend/app/schemas/import_export.py`
  - `backend/app/api/v1/import_export.py`
  - `frontend/src/components/inventory/CsvImportModal.tsx`
  - `frontend/src/components/inventory/CsvValidationReport.tsx`
- **Missing Dependencies**: Ingestion pipeline and frontend uploader.
- **Implementation Plan**:
  - Standard library `csv` / `io.StringIO` streaming parser to minimize memory footprint.
  - Two-stage ingestion endpoint:
    - `dry_run=true`: Validates all rows and returns a structured diagnostic report without persisting records.
    - `dry_run=false`: Commits valid rows; supports `allow_partial=true` (commits valid rows and reports failures) or `allow_partial=false` (atomic transaction rollback on any invalid row).
  - Row validation checks: Header matching, mandatory fields, ISO-8601 date parsing, positive numeric stock, category lookup.
  - Endpoint to download standardized CSV template with inline documentation.
- **Acceptance Criteria**:
  - Processes CSV files with detailed per-row error diagnostics (row number, field, value, reason).
  - Bulk items are associated with the authenticated tenant.
  - Bulk imports record batch transaction logs.
- **Required Tests**:
  - Unit tests with: perfectly valid CSV, missing mandatory headers, bad date formats, negative quantity, unmapped categories.
  - Transactional rollback test when `allow_partial=false`.
  - Batch insertion speed test (1,000 rows in <1.5s).

---

### Requirement 3: POS Integration Through REST API Adapters
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/integrations/pos/base.py`
  - `backend/app/integrations/pos/square.py`
  - `backend/app/integrations/pos/clover.py`
  - `backend/app/integrations/pos/generic.py`
  - `backend/app/api/v1/pos.py`
  - `frontend/src/app/settings/pos/page.tsx`
- **Missing Dependencies**: POS interface abstractions, signature validation routines.
- **Implementation Plan**:
  - Define extensible `POSAdapter` abstract base class with methods: `verify_signature()`, `parse_payload()`, `sync_catalog()`, `handle_order_event()`.
  - Webhook endpoint: `POST /api/v1/pos/webhook/{adapter_name}` with HMAC-SHA256 signature verification.
  - Deduplication via `external_order_id` to ensure idempotency.
  - Automatic decrement of inventory stock matching SKU/barcode with `POS_SALE` transaction logging.
  - Unmatched SKU triage queue: records events for items not yet in inventory for manual linking.
- **Acceptance Criteria**:
  - Webhook requests with invalid signatures are rejected with 401 Unauthorized.
  - Repeated webhook calls with the same order ID do not double-decrement stock.
  - Successful sale decrements matching SKU and writes to transaction history.
- **Required Tests**:
  - HMAC signature validation unit test.
  - Idempotent order processing test.
  - Missing SKU triage queue logging test.

---

### Requirement 4: Expiry Tracking and Configurable Alerts
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/services/expiry_service.py`
  - `backend/app/models/alerts.py`
  - `backend/app/schemas/alerts.py`
  - `backend/app/api/v1/alerts.py`
  - `frontend/src/components/dashboard/ExpiryAlertBanner.tsx`
  - `frontend/src/app/alerts/page.tsx`
- **Missing Dependencies**: Expiry evaluation engine, alert threshold storage.
- **Implementation Plan**:
  - Tenant-level alert configuration table (`tenant_alert_configs`):
    - `critical_hours`: default 24 hours.
    - `warning_days`: default 3 days.
    - `notice_days`: default 7 days.
  - Real-time days-to-expiry calculation:
    $$\Delta t = \frac{\text{expiry\_date} - \text{current\_utc\_time}}{86400}$$
  - Dynamic status classifications:
    - `EXPIRED`: $\Delta t \le 0$
    - `CRITICAL`: $0 < \Delta t \le 1.0$
    - `EXPIRING_SOON`: $1.0 < \Delta t \le \text{warning\_days}$
    - `GOOD`: $\Delta t > \text{warning\_days}$
  - API endpoint: `GET /api/v1/inventory/expiring` with sorting, category filtering, and status segmentation.
- **Acceptance Criteria**:
  - Correct categorization across UTC midnight and timezone boundaries.
  - Configurable alert thresholds per tenant.
  - Query response times <50ms for inventory expiry queries.
- **Required Tests**:
  - Boundary tests for items expiring today, tomorrow, and past expiry.
  - Tenant threshold override test.
  - Expiry alert generation test.

---

### Requirement 5: Food Categorization by Perishability and Storage Requirements
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/models/category.py`
  - `backend/app/schemas/category.py`
  - `backend/app/api/v1/categories.py`
  - `backend/app/core/taxonomy.py`
  - `frontend/src/components/inventory/CategorySelector.tsx`
- **Missing Dependencies**: Seed taxonomy and storage boundary schema.
- **Implementation Plan**:
  - Standardized food taxonomy database table (`categories`):
    - Fields: `id`, `name`, `perishability_tier` (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), `recommended_storage` (`AMBIENT`, `REFRIGERATED`, `FROZEN`, `DRY_PANTRY`), `temp_min_celsius`, `temp_max_celsius`, `default_shelf_life_days`.
  - Built-in initial seed covering:
    - Dairy & Eggs (High perishability, refrigerated 2–4°C)
    - Fresh Meat & Poultry (Critical perishability, refrigerated 0–2°C)
    - Seafood (Critical perishability, refrigerated 0–2°C)
    - Fresh Bakery & Pastries (High perishability, ambient 18–22°C)
    - Leafy Greens & Soft Produce (High perishability, refrigerated 4–7°C)
    - Root Vegetables & Hard Fruits (Medium perishability, cool/ambient 10–14°C)
    - Pantry & Canned Goods (Low perishability, ambient 18–24°C)
  - Automatic inheritance: When a product is created under a category, default storage requirements and baseline shelf-life days are suggested.
- **Acceptance Criteria**:
  - All standard food categories seeded and queryable.
  - Inventory items correctly inherit storage temperature bounds and perishability tiers.
- **Required Tests**:
  - Seed idempotency test (can run repeatedly without duplicate key violations).
  - Category retrieval and filtering tests.

---

### Requirement 6: Barcode/QR Scanning in a Mobile-Friendly Interface
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `frontend/src/components/scanner/BarcodeScannerModal.tsx`
  - `frontend/src/hooks/useBarcodeScanner.ts`
  - `frontend/src/app/scanner/page.tsx`
  - `backend/app/api/v1/inventory.py` (`GET /lookup?barcode=...`)
- **Missing Dependencies**: Scanner components and lookup endpoint.
- **Implementation Plan**:
  - Mobile web camera scanner leveraging browser `BarcodeDetector` API with `html5-qrcode` fallback.
  - Supported barcode formats: UPC-A, EAN-13, EAN-8, Code 128, QR Code.
  - Real-time camera viewfinder with scanning target overlay, flashlight toggle, and camera switcher (front/rear).
  - Rapid workflows on scan:
    - Fast Lookup: Displays current stock, expiry date, storage location.
    - Quick Stock-In: Modal to increment quantity.
    - Quick Surplus-Mark: 1-click action to mark item for donation listing.
- **Acceptance Criteria**:
  - Camera scanner opens smoothly on mobile screens ($<350\text{ms}$).
  - Barcode lookup instantly retrieves item or offers fast "Add New Item" with pre-filled barcode.
- **Required Tests**:
  - Backend barcode lookup endpoint unit test.
  - Scanner mock camera stream integration test.
  - Mobile viewport layout verification.

---

### Requirement 7: Multi-Tenant Storage for Business Inventory Records
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/models/tenant.py`
  - `backend/app/models/base.py`
  - `backend/app/core/tenant.py`
  - `backend/app/db/session.py`
- **Missing Dependencies**: Tenant scoped base model and tenant context resolver.
- **Implementation Plan**:
  - Tenant entity: `tenants` table (`id` UUID primary key, `name`, `slug`, `contact_email`, `status`, `created_at`).
  - Base tenant-scoped entity: `TenantScopedModel` incorporating indexed `tenant_id` foreign key.
  - FastAPI dependency `get_current_tenant` extracts `tenant_id` from verified JWT claims or API key headers.
  - Repository / Service query helper enforcing `filter(Model.tenant_id == current_tenant.id)` on every query.
- **Acceptance Criteria**:
  - Total isolation: Tenant A cannot read, query, update, or delete any record created by Tenant B.
  - ID enumeration attempts on resources of another tenant return 404 (preventing information disclosure).
- **Required Tests**:
  - Multi-tenant data segregation test (assert 0 records of Tenant B returned when queried as Tenant A).
  - Cross-tenant injection / update rejection test.

---

### Requirement 8: Stock Transaction History and Surplus Donation Foundations
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/models/transaction.py`
  - `backend/app/models/donation.py`
  - `backend/app/schemas/transaction.py`
  - `backend/app/schemas/donation.py`
  - `backend/app/api/v1/transactions.py`
  - `backend/app/api/v1/donations.py`
  - `frontend/src/app/transactions/page.tsx`
  - `frontend/src/components/inventory/StockLedgerDrawer.tsx`
- **Missing Dependencies**: Ledger data models, transaction service, donation schema.
- **Implementation Plan**:
  - Immutable audit ledger table `stock_transactions`:
    - `id`, `tenant_id`, `item_id`, `transaction_type` (`INITIAL`, `RESTOCK`, `MANUAL_ADJUSTMENT`, `POS_SALE`, `WASTE_DISCARD`, `DONATION_HOLD`, `DONATION_DISPATCH`), `quantity_change`, `quantity_before`, `quantity_after`, `reason`, `reference_id`, `created_by_user_id`, `created_at`.
  - Surplus donation listings foundation table `surplus_listings`:
    - `id`, `tenant_id`, `item_id`, `quantity`, `unit`, `expiry_date`, `status` (`DRAFT`, `AVAILABLE`, `CLAIMED`, `PICKED_UP`, `EXPIRED`), `pickup_address`, `available_from`, `available_until`, `created_at`.
  - Atomicity: Every stock change updates `inventory_items.current_quantity` and inserts a `stock_transactions` row in a single atomic database transaction.
- **Acceptance Criteria**:
  - Ledger cannot be updated or deleted (append-only).
  - Mathematical integrity: Item current quantity strictly equals the sum of quantity changes over time.
  - Creating a surplus listing places item on `DONATION_HOLD` to prevent double-selling.
- **Required Tests**:
  - Reconciliation test: sum of transactions matches item stock balance.
  - Append-only immutability test.
  - Surplus donation reservation test.

---

### Requirement 9: Authentication, Authorization, and Tenant Isolation
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/core/security.py`
  - `backend/app/models/user.py`
  - `backend/app/schemas/auth.py`
  - `backend/app/api/v1/auth.py`
  - `backend/app/core/deps.py`
  - `frontend/src/context/AuthContext.tsx`
  - `frontend/src/app/login/page.tsx`
- **Missing Dependencies**: Auth router, password hasher, JWT utilities.
- **Implementation Plan**:
  - Secure bcrypt hashing (`cost >= 12`) via `passlib`.
  - JWT token generation with expiration (30-minute access token, 7-day refresh token).
  - Role-Based Access Control (RBAC):
    - `BUSINESS_OWNER`: Full tenant administration, API keys, user management.
    - `STORE_MANAGER`: Inventory management, CSV imports, POS configuration, donation approvals.
    - `INVENTORY_STAFF`: Stock entry, barcode scanning, quantity updates.
    - `RECIPIENT_NGO`: (Prepares for Milestone 3) Viewing surplus food listings and requesting pickups.
    - `SYSTEM_ADMIN`: Platform-wide oversight.
  - FastAPI dependency `require_roles([Role.STORE_MANAGER, Role.BUSINESS_OWNER])`.
- **Acceptance Criteria**:
  - Unauthenticated requests rejected with 401.
  - Unauthorized roles rejected with 403 Forbidden.
  - Passwords never stored or logged in plain text.
- **Required Tests**:
  - Password hashing and verification unit tests.
  - Token expiration and tampered signature rejection tests.
  - RBAC permission matrix endpoint tests.

---

### Requirement 10: Frontend / Backend / Database Integration
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - Full project structure: `backend/`, `frontend/`, `docker-compose.yml`, `.env.example`.
  - `frontend/src/lib/api.ts` (Typed HTTP client with automatic auth header and error unwrapping).
  - `backend/app/main.py` (FastAPI app factory, CORS, health routes).
- **Missing Dependencies**: Repository structure and integration contracts.
- **Implementation Plan**:
  - Configure root and module directory structure.
  - Establish CORS policy allowing Next.js client access (`http://localhost:3000`).
  - Health check endpoints:
    - `GET /health`: Fast liveness probe.
    - `GET /health/ready`: Readiness probe verifying database connectivity.
  - Environment configuration (`.env.example`) with sane local defaults.
- **Acceptance Criteria**:
  - Frontend boots on port 3000; backend boots on port 8000.
  - Frontend queries backend `/health` and live inventory endpoints cleanly.
- **Required Tests**:
  - API liveness and database readiness probe tests.
  - End-to-end integration test of login, create inventory item, and retrieve item.

---

### Requirement 11: Error Handling, Performance, and Regression Tests
- **Current Status**: MISSING
- **Relevant Files / Modules**:
  - `backend/app/core/exceptions.py`
  - `backend/app/middleware/error_handler.py`
  - `backend/tests/` (unit, integration, and security test suites)
  - `frontend/src/components/ui/ErrorBoundary.tsx`
- **Missing Dependencies**: Test suites, custom exception classes.
- **Implementation Plan**:
  - Standardized error response envelope:
    ```json
    {
      "success": false,
      "error": {
        "code": "ITEM_NOT_FOUND",
        "message": "The requested inventory item does not exist or belongs to another tenant",
        "details": null,
        "request_id": "req_01h9..."
      }
    }
    ```
  - Global FastAPI exception handler capturing unhandled errors and returning 500 without leaking stack traces.
  - Database index strategy:
    - `inventory_items(tenant_id, expiry_date)` (for fast expiry queries).
    - `inventory_items(tenant_id, barcode)` (for scan lookups).
    - `stock_transactions(tenant_id, item_id, created_at)` (for ledger queries).
- **Acceptance Criteria**:
  - All errors adhere to uniform JSON envelope.
  - Automated test suite runs in under 30 seconds with 100% pass rate.
  - No database N+1 queries on inventory list with category joins.
- **Required Tests**:
  - Negative validation test suite (422, 404, 401, 403, 409).
  - Bulk query index performance verification.
  - Regression suite executable with a single `pytest` command.

---

## 5. Proposed Database Schema Design

```sql
-- 1. Tenants (Businesses)
CREATE TABLE tenants (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    business_type VARCHAR(50) NOT NULL, -- SUPERMARKET, RESTAURANT, BAKERY, HOTEL, PRODUCE_WHOLESALER
    contact_email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    address TEXT,
    timezone VARCHAR(50) DEFAULT 'UTC',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Users & Roles
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL, -- BUSINESS_OWNER, STORE_MANAGER, INVENTORY_STAFF, RECIPIENT_NGO, ADMIN
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_users_tenant ON users(tenant_id);

-- 3. Food Categories & Storage Taxonomy
CREATE TABLE categories (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    perishability_tier VARCHAR(20) NOT NULL, -- CRITICAL, HIGH, MEDIUM, LOW
    recommended_storage VARCHAR(30) NOT NULL, -- AMBIENT, REFRIGERATED, FROZEN, DRY_PANTRY
    temp_min_celsius NUMERIC(4, 1),
    temp_max_celsius NUMERIC(4, 1),
    default_shelf_life_days INTEGER NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Inventory Items
CREATE TABLE inventory_items (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category_id VARCHAR(36) NOT NULL REFERENCES categories(id),
    name VARCHAR(255) NOT NULL,
    sku VARCHAR(100),
    barcode VARCHAR(100),
    current_quantity NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    unit VARCHAR(20) NOT NULL, -- kg, g, liters, units, boxes, packs
    cost_per_unit NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    selling_price NUMERIC(10, 2),
    purchase_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    batch_number VARCHAR(100),
    storage_requirement VARCHAR(30) NOT NULL, -- AMBIENT, REFRIGERATED, FROZEN
    storage_location VARCHAR(100), -- Shelf A1, Cooler 2, Freezer B
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_inventory_tenant_expiry ON inventory_items(tenant_id, expiry_date);
CREATE INDEX idx_inventory_tenant_barcode ON inventory_items(tenant_id, barcode);
CREATE INDEX idx_inventory_tenant_category ON inventory_items(tenant_id, category_id);

-- 5. Stock Transactions (Immutable Audit Ledger)
CREATE TABLE stock_transactions (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    transaction_type VARCHAR(30) NOT NULL, -- INITIAL, RESTOCK, ADJUSTMENT, POS_SALE, DISCARD, DONATION_HOLD
    quantity_change NUMERIC(10, 2) NOT NULL,
    quantity_before NUMERIC(10, 2) NOT NULL,
    quantity_after NUMERIC(10, 2) NOT NULL,
    reason VARCHAR(255),
    reference_id VARCHAR(100), -- POS Order ID, CSV Import Batch ID, Donation Listing ID
    created_by_user_id VARCHAR(36) REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_transactions_tenant_item ON stock_transactions(tenant_id, item_id, created_at);

-- 6. Tenant Alert Configurations
CREATE TABLE tenant_alert_configs (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    critical_threshold_hours INTEGER DEFAULT 24,
    warning_threshold_days INTEGER DEFAULT 3,
    notice_threshold_days INTEGER DEFAULT 7,
    auto_flag_for_donation BOOLEAN DEFAULT TRUE,
    email_notifications_enabled BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Surplus Donation Listings (Foundation for Milestone 3)
CREATE TABLE surplus_listings (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    quantity NUMERIC(10, 2) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    expiry_date DATE NOT NULL,
    status VARCHAR(30) DEFAULT 'AVAILABLE', -- DRAFT, AVAILABLE, CLAIMED, PICKED_UP, EXPIRED, CANCELLED
    pickup_address TEXT NOT NULL,
    available_from TIMESTAMP WITH TIME ZONE NOT NULL,
    available_until TIMESTAMP WITH TIME ZONE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_surplus_tenant_status ON surplus_listings(tenant_id, status);

-- 8. POS Integrations
CREATE TABLE pos_integrations (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL, -- SQUARE, CLOVER, TOAST, GENERIC
    api_key_hash VARCHAR(255) NOT NULL,
    webhook_secret VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. Proposed REST API Specification

| Method | Path | Summary & Purpose | Auth & Permissions |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Register new business tenant & owner user | Public |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT access token | Public |
| `GET` | `/api/v1/auth/me` | Fetch current user & tenant profile | Authenticated |
| `GET` | `/api/v1/categories` | List food taxonomy categories | Authenticated |
| `GET` | `/api/v1/inventory` | List tenant inventory with filtering & pagination | Authenticated |
| `POST` | `/api/v1/inventory` | Create new inventory item (triggers stock transaction) | Staff, Manager, Owner |
| `GET` | `/api/v1/inventory/{id}` | Retrieve single item details | Authenticated |
| `PATCH` | `/api/v1/inventory/{id}` | Update item quantity, price, or storage details | Staff, Manager, Owner |
| `DELETE` | `/api/v1/inventory/{id}` | Soft-delete / deactivate item | Manager, Owner |
| `GET` | `/api/v1/inventory/lookup` | Lookup item by barcode / QR code | Authenticated |
| `GET` | `/api/v1/inventory/expiring` | Query items approaching expiry with status filter | Authenticated |
| `POST` | `/api/v1/inventory/bulk-import/csv` | Ingest inventory via CSV (dry-run & commit) | Manager, Owner |
| `GET` | `/api/v1/inventory/bulk-import/template` | Download standard CSV import template | Authenticated |
| `GET` | `/api/v1/transactions` | Query audit ledger transaction history | Manager, Owner |
| `POST` | `/api/v1/pos/webhook/{provider}` | Ingest real-time POS sales webhook | HMAC Signature / API Key |
| `GET` | `/api/v1/alerts/config` | Get tenant expiry alert thresholds | Authenticated |
| `PUT` | `/api/v1/alerts/config` | Update tenant expiry alert thresholds | Manager, Owner |
| `GET` | `/api/v1/donations` | List surplus items earmarked for donation | Authenticated |
| `POST` | `/api/v1/donations` | List an item as surplus donation (holds stock) | Staff, Manager, Owner |
| `GET` | `/health` | Application liveness probe | Public |
| `GET` | `/health/ready` | Database readiness check | Public |

---

## 7. Ordered Implementation Plan (Phased Roadmap)

1. **Phase 1: Project Scaffolding & Database Foundations**
   - Initialize Git repository and directory layout (`backend/`, `frontend/`, `docs/`).
   - Configure Python dependencies (`requirements.txt`) and SQLite/PostgreSQL database engine.
   - Author SQLAlchemy models (`tenants`, `users`, `categories`, `inventory_items`, `stock_transactions`, `tenant_alert_configs`, `surplus_listings`, `pos_integrations`).
   - Implement category taxonomy seeder script.
   - Establish backend application factory (`backend/app/main.py`) and health probes.

2. **Phase 2: Authentication, Authorization & Multi-Tenancy**
   - Implement password hashing, JWT generation, and token validation.
   - Build FastAPI tenant resolver dependency (`get_current_tenant`).
   - Implement `/api/v1/auth` endpoints (`register`, `login`, `me`).
   - Write unit and integration tests for tenant data boundary isolation.

3. **Phase 3: Core Inventory Engine & Transaction Ledger**
   - Implement inventory CRUD service with atomic transaction ledger logging.
   - Expose `/api/v1/inventory` endpoints.
   - Implement barcode lookup endpoint (`/api/v1/inventory/lookup`).
   - Author comprehensive unit tests for schema constraints and stock recalculations.

4. **Phase 4: Expiry Tracking & Dynamic Alert Engine**
   - Implement expiry evaluation engine with UTC timezone handling.
   - Implement tenant-configurable alert thresholds (`tenant_alert_configs`).
   - Expose `/api/v1/inventory/expiring` and alert configuration endpoints.
   - Test threshold transitions (Normal -> Notice -> Warning -> Critical -> Expired).

5. **Phase 5: CSV Bulk Ingestion Engine**
   - Implement streaming CSV parser with row-level validation diagnostics.
   - Support `dry_run=true` preview and `allow_partial` flags.
   - Provide standard CSV sample template download endpoint.
   - Test invalid formatting, missing fields, and atomic rollback modes.

6. **Phase 6: POS Integration REST Adapter**
   - Implement POS adapter base interface with HMAC-SHA256 signature verification.
   - Implement Square and Generic webhook handlers.
   - Implement idempotency protection using `external_order_id`.
   - Implement stock decrement and missing SKU triage queue.
   - Test duplicate payloads and signature tampering rejection.

7. **Phase 7: Mobile-Friendly Frontend Implementation**
   - Scaffold Next.js 16 / React 19 / Tailwind CSS application.
   - Build responsive layout with navigation, auth context, and tenant indicator.
   - Build Inventory Management Table with real-time search, filters, and status badges.
   - Build Add/Edit Item modal with instant field validation.
   - Build CSV drag-and-drop import modal with row-by-row error preview table.
   - Build mobile camera Barcode/QR scanner modal with vibration/sound feedback and quick stock actions.
   - Build Expiry Alerts dashboard widget and dedicated alert center.

8. **Phase 8: End-to-End Integration, Security Audit & Regression Verification**
   - Connect frontend API client with backend routes and test full user workflows.
   - Run complete test suite (`pytest`) verifying 100% pass rate.
   - Execute frontend production build (`npm.cmd run build`) verifying 0 errors.
   - Document verification results in `docs/MILESTONE_1_VERIFICATION.md`.

---

## 8. Risks, External Dependencies & Environment Constraints

1. **PowerShell Script Execution Policy**:
   - Running `npm` directly invokes `npm.ps1`, which is blocked by PowerShell execution policy on Windows.
   - **Mitigation**: Always execute `npm.cmd` and `npx.cmd`.
2. **Local Database Service Absence**:
   - `psql`, `mongod`, and `docker` are not currently in the Windows PATH.
   - **Mitigation**: Develop the database layer using SQLAlchemy 2.0 with clean SQLite support (WAL mode) for local execution, unit tests, and CI, while maintaining 100% PostgreSQL compatibility via standard SQL DDL and connection string abstraction.
3. **Camera Hardware Availability**:
   - Desktop development machines may lack camera access for barcode testing.
   - **Mitigation**: Provide both real camera stream detection and a mock camera / manual barcode entry fallback mode in the UI.
4. **Timezone Handling**:
   - Expiry dates must be treated as date boundaries in the business's local timezone while stored uniformly in UTC.
   - **Mitigation**: Store timestamps as UTC ISO-8601; compute days-to-expiry relative to tenant configured timezone.

---

## 9. Immediate Next Action for Phase 1

The exact next action upon approval of Phase 0 is:
1. Initialize the git repository: `git init`.
2. Scaffold the project directories: `backend/`, `frontend/`, `docs/`.
3. Create `backend/requirements.txt` and establish database models and migration scripts.
