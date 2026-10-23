# Security Design & Multi-Tenant Isolation Architecture

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Document**: Security Architecture, Authentication, RBAC, and Tenant Isolation  
**Phase**: Phase 1 — Detailed Design  

---

## 1. Authentication & Identity Management

### 1.1 Password Hashing & Storage
- Passwords are never stored or logged in plain text.
- Passwords are cryptographically hashed using **bcrypt** (via `passlib[bcrypt]`) with a minimum work factor / cost parameter of **12**, or **Argon2id**.
- Password complexity requirements enforced on registration and reset:
  - Minimum 8 characters.
  - At least one uppercase letter `[A-Z]`.
  - At least one lowercase letter `[a-z]`.
  - At least one decimal digit `[0-9]`.
  - At least one special symbol `[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]`.

### 1.2 JWT Token Architecture
- Authentication uses short-lived, signed JSON Web Tokens (JWT) adhering to RFC 7519.
- Algorithm: HMAC-SHA256 (`HS256`) with a cryptographically secure 256-bit secret key loaded exclusively from the environment variable `JWT_SECRET_KEY`.
- Token Lifespans:
  - **Access Token**: 30 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES = 30`).
  - **Refresh Token**: 7 days (`REFRESH_TOKEN_EXPIRE_DAYS = 7`), stored in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie.
- JWT Payload Claims:
  ```json
  {
    "sub": "usr_4a2c0f1e-1234-5678-abcd-ef0123456789",
    "tenant_id": "ten_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "role": "STORE_MANAGER",
    "email": "manager@freshmarket.example",
    "iat": 1729627200,
    "exp": 1729629000,
    "iss": "food-waste-platform"
  }
  ```

---

## 2. Multi-Tenant Isolation Strategy

The platform employs a **Shared-Database, Shared-Schema Architecture** with strict, defense-in-depth **Logical Tenant Isolation**.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Incoming Client Request                          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Dependency Pipeline                         │
│  1. `get_current_user`: Validates JWT signature, expiration, active flag│
│  2. `get_current_tenant`: Extracts `tenant_id` claim, queries `tenants` │
│     verifying tenant status is `is_active = TRUE`.                      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Injects `CurrentTenant` dataclass
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Service & ORM Layer                             │
│  Enforces `tenant_id` filter across all query generation:               │
│  `select(InventoryItem).where(                                          │
│      InventoryItem.id == item_id,                                       │
│      InventoryItem.tenant_id == current_tenant.id                       │
│  )`                                                                     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   PostgreSQL Row-Level Security (RLS)                   │
│             (Layer 2 Defense: Defense-in-Depth for Production)          │
│  `CREATE POLICY tenant_isolation_policy ON inventory_items              │
│   USING (tenant_id = current_setting('app.current_tenant_id'));`        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Defense Layer 1: Server-Side Query Scoping
In the application service layer, all database queries are bound to the caller's tenant context:
1. All database models inheriting from `TenantScopedModel` must declare:
   ```python
   tenant_id: Mapped[str] = mapped_column(
       ForeignKey("tenants.id", ondelete="CASCADE"), 
       index=True, 
       nullable=False
   )
   ```
2. Repository query builders require the `tenant_id` parameter. Direct unfiltered queries on tenant-scoped tables are forbidden by code linting and unit tests.
3. On item creation or CSV import, `item.tenant_id` is assigned directly from the validated session context—never trusted from user request bodies.

### 2.2 Defense Layer 2: PostgreSQL Row-Level Security (RLS)
For production PostgreSQL deployments, native database-level RLS provides defense-in-depth:
```sql
-- Enable RLS on all tenant-owned tables
ALTER TABLE inventory_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_alert_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE expiry_alert_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE csv_import_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE csv_import_row_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE pos_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE surplus_listings ENABLE ROW LEVEL SECURITY;

-- Define RLS Policy for inventory items
CREATE POLICY tenant_isolation_inventory ON inventory_items
    FOR ALL
    TO application_user
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));
```
During request setup, the database connection executes:
```sql
SET LOCAL app.current_tenant_id = 'ten_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d';
```

### 2.3 Defense Layer 3: Enumeration & ID Disclosure Prevention
- When a user requests a resource by ID (`GET /api/v1/inventory/{id}`) that exists in the database but belongs to a different tenant:
  - The server **MUST** return `404 Not Found` (never `403 Forbidden`).
  - Reason: Returning `403 Forbidden` confirms to an attacker that the targeted resource ID exists in another tenant's private inventory. Returning `404 Not Found` reveals zero metadata about existence.

---

## 3. Role-Based Access Control (RBAC) Matrix

The system enforces 5 distinct roles:
1. `BUSINESS_OWNER`: Full administrative control over business settings, staff accounts, API integrations, and financial data.
2. `STORE_MANAGER`: Operational authority over inventory, bulk imports, alert thresholds, donation authorizations, and staff activity.
3. `INVENTORY_STAFF`: Day-to-day stock handlers (stock in, stock out, scanning barcodes, manual adjustments).
4. `RECIPIENT_NGO`: Partner organization representatives (browses surplus donation listings, schedules collections).
5. `SYSTEM_ADMIN`: Platform-wide DevOps / administrative oversight.

| Permission / Action | `BUSINESS_OWNER` | `STORE_MANAGER` | `INVENTORY_STAFF` | `RECIPIENT_NGO` | `SYSTEM_ADMIN` |
| :--- | :---: | :---: | :---: | :---: | :---: |
| View Inventory Items | **Yes** | **Yes** | **Yes** | No | Read-only |
| Create / Edit Inventory Items | **Yes** | **Yes** | **Yes** | No | No |
| Soft-Delete Inventory Items | **Yes** | **Yes** | No | No | No |
| CSV Bulk Import | **Yes** | **Yes** | No | No | No |
| Barcode Quick-Scan Actions | **Yes** | **Yes** | **Yes** | No | No |
| Manual Stock Adjustments | **Yes** | **Yes** | **Yes** (Reason req.) | No | No |
| View Audit Ledger / Transactions | **Yes** | **Yes** | No | No | Read-only |
| Configure Expiry Alerts | **Yes** | **Yes** | No | No | No |
| Acknowledge Expiry Alerts | **Yes** | **Yes** | **Yes** | No | No |
| Configure POS Integrations | **Yes** | No | No | No | No |
| Post Surplus Donation Listing | **Yes** | **Yes** | No | No | No |
| View Surplus Donation Feed | **Yes** | **Yes** | No | **Yes** | Read-only |
| Manage Staff Accounts | **Yes** | No | No | No | Platform users |

---

## 4. POS Integration Secret & Key Security

Integrating with external POS providers (Square, Clover, Toast, Generic Webhook) involves webhook callbacks and API credentials that must be secured against exposure.

### 4.1 Storage of POS Credentials
1. **Never Store Plaintext Secrets**: The database stores **only** a one-way cryptographic SHA-256 hash of the webhook signing secret and API keys (`webhook_secret_hash`, `api_key_hash`).
2. **One-Time Secret Display**: When a user creates or rotates a POS integration, the raw secret is generated via `secrets.token_hex(32)`, returned once in the HTTP response, and never persisted in clear text.
3. **Outbound API Tokens (if applicable)**: If the platform makes outbound requests to an external POS, tokens are encrypted at rest using **AES-256-GCM** using a master encryption key stored in the environment (`POS_ENCRYPTION_KEY`).

### 4.2 Webhook Signature Verification Protocol
Every inbound webhook from a POS must be cryptographically verified before parsing:
```python
import hmac
import hashlib

def verify_webhook_signature(payload_bytes: bytes, signature_header: str, secret: str) -> bool:
    """
    Verifies HMAC-SHA256 signature in constant time to prevent timing attacks.
    """
    if not signature_header.startswith("sha256="):
        return False
    expected_hash = signature_header.split("sha256=", 1)[1]
    computed_hash = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_hash, computed_hash)
```
- Calls failing signature validation immediately abort with `401 Unauthorized` without reading or deserializing the payload JSON.

### 4.3 Webhook Idempotency & Replay Protection
- Attackers or network retries might replay the same webhook payload multiple times, causing duplicate inventory deductions.
- Mitigation: Every POS webhook must supply an `X-Idempotency-Key` or payload `order_id`. The application maintains a deduplication cache/table (`processed_pos_events`) with a 72-hour retention window. If an event ID has already been processed, the system returns `200 OK` with `status: ALREADY_PROCESSED` without double-decrementing stock.

---

## 5. Input Sanitization & Injection Defense

### 5.1 CSV Formula Injection (CWE-1236)
When exporting or importing CSV files, spreadsheet applications (Excel, LibreOffice) may execute malicious cells beginning with `=`, `+`, `-`, `@`, `\t`, or `\r`.
- **Sanitization Rule**: Any text field in CSV imports/exports starting with dangerous formula characters is escaped by prefixing a single quote `'` and stripping control characters before database insertion.

### 5.2 Barcode & SKU Sanitization
- Barcodes and SKUs are scanned directly from physical labels and may contain unexpected characters or malicious payloads.
- **Rule**: Barcodes are strictly validated against a regex pattern: `^[A-Za-z0-9\-_:.]{1,100}$`. Malformed characters are rejected with `422 Unprocessable Entity`.

### 5.3 SQL Injection Defense
- 100% of database interactions are executed through SQLAlchemy 2.0 ORM or parameterized SQL statements. Raw string concatenation or f-strings in queries are strictly prohibited.

---

## 6. Rate Limiting, Audit Logging & Request Tracing

### 6.1 Rate Limiting Policies
- `POST /api/v1/auth/login`: 5 requests per minute per IP (prevents brute-force credential stuffing).
- `POST /api/v1/auth/register`: 3 registrations per hour per IP.
- Public Webhooks (`POST /api/v1/pos/webhook/*`): 100 requests per minute per integration slug.
- General Authenticated Endpoints: 300 requests per minute per authenticated user.

### 6.2 Audit Event Logging
All state-modifying actions write an immutable row to `audit_events`:
- Login successes and failures.
- Bulk CSV imports (job ID, rows processed, failure count).
- Manual inventory stock adjustments with user justification.
- Expiry alert acknowledgments.
- Sensitive configuration changes (alert thresholds, POS integration creation).
- Request context captured: `user_id`, `tenant_id`, `ip_address`, `user_agent`, `timestamp`.

### 6.3 Request Tracing
- A unique request identifier (`X-Request-ID`) is assigned to every inbound HTTP request by middleware.
- The `request_id` is propagated through all application log entries and included in standard error response envelopes, facilitating end-to-end incident investigation without exposing internal stack traces.

---

## 7. Security Implementation & Verification Status

- **Tenant Isolation Test Suite (`backend/tests/test_tenant_security.py`)**: 9 / 9 tests passing:
  - `test_resolve_tenant_context_success`: PASS (Resolves active tenant & user context)
  - `test_resolve_tenant_context_inactive_user`: PASS (Rejects inactive user with 401)
  - `test_resolve_tenant_context_inactive_tenant`: PASS (Rejects deactivated tenant organization with 401)
  - `test_resolve_tenant_context_claim_spoofing`: PASS (Rejects mismatched JWT tenant claim with 403)
  - `test_scope_query_isolation`: PASS (Verifies `scope_query` appends `WHERE tenant_id = ...`)
  - `test_verify_tenant_ownership_cross_access`: PASS (Rejects cross-tenant record mutation with `CrossTenantAccessError`)
  - `test_enforce_tenant_ownership_overrides_client_input`: PASS (Forces `tenant_id` assignment from token)
  - `test_transaction_history_cross_tenant_isolation`: PASS (Transactions strictly isolated by tenant)
  - `test_alert_history_cross_tenant_isolation`: PASS (Alert logs strictly isolated by tenant)

- **Transaction & Cryptography Security Test Suite (`backend/tests/test_transactions_and_rollback.py`)**: 6 / 6 tests passing:
  - `test_transaction_atomic_rollback_on_failure`: PASS (Atomic rollback on mutation errors)
  - `test_stock_adjustment_atomic_ledger_reconciliation`: PASS (Stock balance matches ledger transaction deltas)
  - `test_password_hashing_and_verification`: PASS (Bcrypt salt generation & password verification)
  - `test_jwt_token_minting_and_decoding`: PASS (HS256 minting, claim encoding, and expiration)
  - `test_pos_webhook_hmac_signature_verification`: PASS (HMAC-SHA256 signature verification)
  - `test_pos_secret_hashing`: PASS (SHA-256 secret hashing for POS API keys)

