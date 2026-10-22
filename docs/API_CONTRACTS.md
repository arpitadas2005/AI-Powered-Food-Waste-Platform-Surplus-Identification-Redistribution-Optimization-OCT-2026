# REST API Contracts Specification

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Document**: REST API Specification & Data Contracts  
**Phase**: Phase 1 — Detailed Design  
**Version**: `v1`  
**Base Path**: `/api/v1`

---

## 1. Global Standards & Conventions

### 1.1 Content Types & Encoding
- All endpoints accept and return `application/json; charset=utf-8` unless explicitly documented (e.g., CSV file uploads and template downloads).
- Timestamps are formatted as ISO-8601 UTC strings: `YYYY-MM-DDTHH:MM:SSZ`.
- Dates are formatted as ISO-8601 strings: `YYYY-MM-DD`.

### 1.2 Authentication & Authorization Headers
- Standard endpoints require a Bearer token:
  ```http
  Authorization: Bearer <JWT_ACCESS_TOKEN>
  ```
- POS Adapter Webhook endpoints require signature and idempotency headers:
  ```http
  X-POS-Signature: sha256=<HMAC_HEX_DIGEST>
  X-Idempotency-Key: <UNIQUE_EVENT_OR_TRANSACTION_ID>
  ```

### 1.3 Standard Response Envelopes

#### Success Envelope (Single Entity)
```json
{
  "success": true,
  "data": { ... }
}
```

#### Success Envelope (Paginated Collection)
```json
{
  "success": true,
  "data": [ ... ],
  "pagination": {
    "page": 1,
    "size": 50,
    "total": 128,
    "total_pages": 3,
    "has_next": true,
    "has_prev": false
  }
}
```

#### Error Envelope
All client and server errors adhere to a uniform structure:
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "One or more fields failed validation criteria",
    "details": [
      {
        "field": "expiry_date",
        "issue": "expiry_date must be greater than or equal to purchase_date"
      }
    ],
    "request_id": "req_01h9x72b98e1"
  }
}
```

Standard Error Codes:
- `UNAUTHORIZED` (401)
- `FORBIDDEN` (403)
- `NOT_FOUND` (404)
- `CONFLICT` (409)
- `VALIDATION_FAILED` (422)
- `RATE_LIMITED` (429)
- `INTERNAL_SERVER_ERROR` (500)

---

## 2. Authentication & Tenant Endpoints

### 2.1 `POST /api/v1/auth/register`
Registers a new food business tenant and its initial `BUSINESS_OWNER` user account.

- **Access**: Public
- **Request Body**:
```json
{
  "business_name": "Fresh Market Downtown",
  "business_type": "SUPERMARKET",
  "contact_email": "owner@freshmarket.example",
  "phone": "+1-555-0199",
  "address": "123 Market St, San Francisco, CA",
  "timezone": "America/Los_Angeles",
  "currency": "USD",
  "owner_full_name": "Alice Chen",
  "owner_email": "alice@freshmarket.example",
  "password": "SecurePassword123!"
}
```
- **Validation**:
  - `business_name`: 2–255 chars.
  - `business_type`: must be one of `SUPERMARKET`, `RESTAURANT`, `BAKERY`, `HOTEL`, `WHOLESALER`, `NGO_RECIPIENT`.
  - `owner_email`: valid RFC 5322 format.
  - `password`: min 8 chars, at least 1 uppercase, 1 lowercase, 1 digit, 1 special character.
- **Response (201 Created)**:
```json
{
  "success": true,
  "data": {
    "tenant": {
      "id": "ten_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "name": "Fresh Market Downtown",
      "slug": "fresh-market-downtown",
      "business_type": "SUPERMARKET",
      "timezone": "America/Los_Angeles"
    },
    "user": {
      "id": "usr_4a2c0f1e-1234-5678-abcd-ef0123456789",
      "email": "alice@freshmarket.example",
      "full_name": "Alice Chen",
      "role": "BUSINESS_OWNER"
    },
    "tokens": {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer",
      "expires_in": 1800
    }
  }
}
```

---

### 2.2 `POST /api/v1/auth/login`
Authenticates a user and returns a signed JWT access token containing tenant and role claims.

- **Access**: Public
- **Request Body**:
```json
{
  "email": "alice@freshmarket.example",
  "password": "SecurePassword123!"
}
```
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 1800,
    "user": {
      "id": "usr_4a2c0f1e-1234-5678-abcd-ef0123456789",
      "tenant_id": "ten_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "email": "alice@freshmarket.example",
      "full_name": "Alice Chen",
      "role": "BUSINESS_OWNER"
    }
  }
}
```

---

### 2.3 `GET /api/v1/auth/me`
Retrieves authenticated user profile and associated tenant details.

- **Access**: Authenticated (`BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF`, `RECIPIENT_NGO`, `SYSTEM_ADMIN`)
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "usr_4a2c0f1e-1234-5678-abcd-ef0123456789",
      "email": "alice@freshmarket.example",
      "full_name": "Alice Chen",
      "role": "BUSINESS_OWNER",
      "created_at": "2026-10-22T10:00:00Z"
    },
    "tenant": {
      "id": "ten_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "name": "Fresh Market Downtown",
      "slug": "fresh-market-downtown",
      "business_type": "SUPERMARKET",
      "timezone": "America/Los_Angeles",
      "currency": "USD"
    }
  }
}
```

---

## 3. Food Category Endpoints

### 3.1 `GET /api/v1/categories`
Lists food taxonomy categories (combining global system standards and tenant-defined custom categories).

- **Access**: Authenticated
- **Query Parameters**:
  - `perishability_tier` (optional): `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`
  - `recommended_storage` (optional): `AMBIENT`, `REFRIGERATED`, `FROZEN`, `DRY_PANTRY`
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": [
    {
      "id": "cat_dairy_eggs",
      "name": "Dairy & Eggs",
      "slug": "dairy-and-eggs",
      "perishability_tier": "HIGH",
      "recommended_storage": "REFRIGERATED",
      "temp_min_celsius": 2.0,
      "temp_max_celsius": 4.0,
      "humidity_min_pct": null,
      "humidity_max_pct": null,
      "default_shelf_life_days": 14,
      "description": "Perishable dairy products, butter, yogurt, and pasteurized eggs requiring cold storage.",
      "is_custom": false
    },
    {
      "id": "cat_leafy_greens",
      "name": "Leafy Greens & Soft Produce",
      "slug": "leafy-greens",
      "perishability_tier": "CRITICAL",
      "recommended_storage": "REFRIGERATED",
      "temp_min_celsius": 4.0,
      "temp_max_celsius": 7.0,
      "humidity_min_pct": 85.0,
      "humidity_max_pct": 95.0,
      "default_shelf_life_days": 5,
      "description": "Lettuce, spinach, herbs, and delicate fruits prone to rapid wilting.",
      "is_custom": false
    }
  ]
}
```

---

## 4. Inventory Management Endpoints

### 4.1 `GET /api/v1/inventory`
Searches, filters, and paginates inventory items belonging strictly to the caller's tenant.

- **Access**: Authenticated (`BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF`)
- **Query Parameters**:
  - `page` (int, default `1`): page number.
  - `size` (int, default `50`, max `100`): items per page.
  - `search` (string, optional): search term matching product name, SKU, or barcode.
  - `category_id` (string, optional): category filter.
  - `storage_requirement` (string, optional): `AMBIENT`, `REFRIGERATED`, `FROZEN`, `DRY_PANTRY`.
  - `status` (string, optional): `ACTIVE`, `EXPIRING_SOON`, `EXPIRED`, `DEPLETED`.
  - `sort_by` (string, default `expiry_date`): `expiry_date`, `name`, `current_quantity`, `created_at`.
  - `sort_order` (string, default `asc`): `asc`, `desc`.
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": [
    {
      "id": "inv_88e0b621-1234-5678-abcd-000000000001",
      "name": "Fresh Whole Milk 1L",
      "sku": "DAI-MILK-001",
      "barcode": "012345678905",
      "category": {
        "id": "cat_dairy_eggs",
        "name": "Dairy & Eggs",
        "perishability_tier": "HIGH"
      },
      "current_quantity": 42.00,
      "unit": "liters",
      "cost_per_unit": 1.20,
      "selling_price": 2.49,
      "purchase_date": "2026-10-20",
      "expiry_date": "2026-10-25",
      "days_to_expiry": 2.50,
      "batch_number": "LOT-2026-10-A",
      "storage_requirement": "REFRIGERATED",
      "storage_location": "Walk-in Cooler 1",
      "status": "EXPIRING_SOON",
      "created_at": "2026-10-20T08:00:00Z",
      "updated_at": "2026-10-22T14:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "size": 50,
    "total": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

---

### 4.2 `POST /api/v1/inventory`
Creates a new inventory item and automatically records an `INITIAL_COUNT` stock transaction.

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF`
- **Request Body**:
```json
{
  "name": "Artisan Sourdough Loaf",
  "category_id": "cat_bakery",
  "sku": "BAK-SOUR-500G",
  "barcode": "098765432109",
  "initial_quantity": 25.00,
  "unit": "units",
  "cost_per_unit": 1.80,
  "selling_price": 4.50,
  "purchase_date": "2026-10-22",
  "expiry_date": "2026-10-24",
  "batch_number": "BATCH-BAK-22",
  "storage_requirement": "AMBIENT",
  "storage_location": "Bakery Rack A",
  "notes": "Baked fresh daily"
}
```
- **Validation Rules**:
  - `name`: 2–255 chars, mandatory.
  - `category_id`: valid existing category ID.
  - `initial_quantity`: $\ge 0$.
  - `unit`: one of `kg`, `g`, `liters`, `ml`, `units`, `boxes`, `packs`.
  - `cost_per_unit`: $\ge 0$.
  - `purchase_date`: valid ISO date $\le$ current date.
  - `expiry_date`: valid ISO date $\ge$ `purchase_date`.
- **Response (201 Created)**:
```json
{
  "success": true,
  "data": {
    "id": "inv_99f1c732-2345-6789-bcde-111111111111",
    "name": "Artisan Sourdough Loaf",
    "sku": "BAK-SOUR-500G",
    "barcode": "098765432109",
    "current_quantity": 25.00,
    "unit": "units",
    "status": "ACTIVE",
    "days_to_expiry": 1.95,
    "created_at": "2026-10-22T20:30:00Z"
  }
}
```

---

### 4.3 `GET /api/v1/inventory/{id}`
Retrieves a single inventory item by ID.

- **Access**: Authenticated (`BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF`)
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "id": "inv_99f1c732-2345-6789-bcde-111111111111",
    "tenant_id": "ten_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "name": "Artisan Sourdough Loaf",
    "sku": "BAK-SOUR-500G",
    "barcode": "098765432109",
    "current_quantity": 25.00,
    "unit": "units",
    "cost_per_unit": 1.80,
    "selling_price": 4.50,
    "purchase_date": "2026-10-22",
    "expiry_date": "2026-10-24",
    "batch_number": "BATCH-BAK-22",
    "storage_requirement": "AMBIENT",
    "storage_location": "Bakery Rack A",
    "status": "ACTIVE",
    "created_at": "2026-10-22T20:30:00Z",
    "updated_at": "2026-10-22T20:30:00Z"
  }
}
```
- **Error (404 Not Found)**:
```json
{
  "success": false,
  "error": {
    "code": "ITEM_NOT_FOUND",
    "message": "Inventory item not found",
    "request_id": "req_01h9x72b98e1"
  }
}
```
*(Returned both when item does not exist AND when item belongs to another tenant, preventing identifier enumeration).*

---

### 4.4 `PATCH /api/v1/inventory/{id}`
Partially updates inventory item details (pricing, storage location, notes, status).

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`
- **Request Body**:
```json
{
  "selling_price": 3.99,
  "storage_location": "Discount Table Front",
  "notes": "Marked down 10% for quick clearance"
}
```
- **Response (200 OK)**: Returns updated entity.

---

### 4.5 `DELETE /api/v1/inventory/{id}`
Soft-deletes / deactivates an inventory item.

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "id": "inv_99f1c732-2345-6789-bcde-111111111111",
    "is_active": false,
    "deactivated_at": "2026-10-22T20:35:00Z"
  }
}
```

---

## 5. Barcode & QR Code Endpoints

### 5.1 `GET /api/v1/inventory/lookup`
Fast barcode/QR lookup endpoint for mobile scanning interfaces.

- **Access**: Authenticated
- **Query Parameters**:
  - `code` (string, required): scanned UPC, EAN, or internal QR code string.
- **Response (200 OK - Found)**:
```json
{
  "success": true,
  "data": {
    "match_type": "EXACT",
    "item": {
      "id": "inv_88e0b621-1234-5678-abcd-000000000001",
      "name": "Fresh Whole Milk 1L",
      "sku": "DAI-MILK-001",
      "barcode": "012345678905",
      "current_quantity": 42.00,
      "unit": "liters",
      "expiry_date": "2026-10-25",
      "days_to_expiry": 2.50,
      "storage_location": "Walk-in Cooler 1",
      "status": "EXPIRING_SOON"
    }
  }
}
```
- **Response (404 Not Found - Unregistered Code)**:
```json
{
  "success": false,
  "error": {
    "code": "BARCODE_UNREGISTERED",
    "message": "No inventory item is associated with this barcode",
    "details": {
      "scanned_code": "079357318992"
    },
    "request_id": "req_01h9x72b98e2"
  }
}
```

---

### 5.2 `POST /api/v1/inventory/quick-scan-action`
Executes rapid in-field stock actions from a handheld scanner (stock increment or decrement).

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF`
- **Request Body**:
```json
{
  "barcode": "012345678905",
  "action": "STOCK_IN",
  "quantity_delta": 10.00,
  "reason": "Replenishment delivery received"
}
```
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "item_id": "inv_88e0b621-1234-5678-abcd-000000000001",
    "name": "Fresh Whole Milk 1L",
    "quantity_before": 42.00,
    "quantity_after": 52.00,
    "transaction_id": "tx_55a1b2c3-1234-5678-90ab-cdef01234567"
  }
}
```

---

## 6. Stock Adjustments & Transaction Ledger Endpoints

### 6.1 `POST /api/v1/inventory/{id}/adjust`
Executes an explicit manual stock adjustment with mandatory operational justification.

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF`
- **Request Body**:
```json
{
  "adjustment_type": "MANUAL_ADJUSTMENT",
  "quantity_delta": -3.00,
  "reason": "Dropped and damaged packaging during restocking",
  "reference_id": null
}
```
- **Validation**:
  - `quantity_delta`: non-zero number.
  - Resulting stock (`current_quantity + quantity_delta`) must be $\ge 0$.
  - `reason`: minimum 5 characters explaining adjustment.
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "item_id": "inv_88e0b621-1234-5678-abcd-000000000001",
    "quantity_before": 52.00,
    "quantity_change": -3.00,
    "quantity_after": 49.00,
    "transaction": {
      "id": "tx_66b2c3d4-2345-6789-01bc-def012345678",
      "transaction_type": "MANUAL_ADJUSTMENT",
      "created_at": "2026-10-22T20:40:00Z"
    }
  }
}
```

---

### 6.2 `GET /api/v1/transactions`
Retrieves immutable stock ledger transactions across the entire tenant with filtering.

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`
- **Query Parameters**:
  - `page` (int, default `1`)
  - `size` (int, default `50`)
  - `item_id` (string, optional)
  - `transaction_type` (string, optional): `INITIAL_COUNT`, `RESTOCK`, `POS_SALE`, `MANUAL_ADJUSTMENT`, `DONATION_HOLD`, `SPOILAGE_DISCARD`
  - `from_date` (ISO date, optional)
  - `to_date` (ISO date, optional)
- **Response (200 OK)**: Returns paginated list of transactions with item names and actor details.

---

## 7. CSV Bulk Ingestion Endpoints

### 7.1 `POST /api/v1/inventory/bulk-import/csv`
Uploads a CSV file of inventory records. Supports dry-run validation preview and atomic vs partial commit modes.

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`
- **Content-Type**: `multipart/form-data`
- **Form Parameters**:
  - `file`: binary CSV file (max 10MB).
  - `dry_run` (boolean, default `true`): if true, executes validation and returns row report without writing to database.
  - `allow_partial` (boolean, default `false`): if true, valid rows are saved even if some fail; if false, any invalid row triggers an atomic rollback.
- **Response (200 OK - Dry Run or Commit)**:
```json
{
  "success": true,
  "data": {
    "job_id": "csv_77c3d4e5-3456-7890-12cd-ef0123456789",
    "filename": "weekly_inventory_oct22.csv",
    "dry_run": false,
    "allow_partial": true,
    "summary": {
      "total_rows": 100,
      "successful_rows": 98,
      "failed_rows": 2
    },
    "errors": [
      {
        "row_number": 14,
        "field_name": "expiry_date",
        "invalid_value": "2025-13-45",
        "error_code": "INVALID_DATE_FORMAT",
        "error_message": "Date '2025-13-45' could not be parsed as YYYY-MM-DD"
      },
      {
        "row_number": 62,
        "field_name": "current_quantity",
        "invalid_value": "-15",
        "error_code": "NEGATIVE_QUANTITY",
        "error_message": "Quantity must be greater than or equal to 0"
      }
    ]
  }
}
```

---

### 7.2 `GET /api/v1/inventory/bulk-import/template`
Downloads standard CSV template file with required headers and documentation comments.

- **Access**: Authenticated
- **Response (200 OK)**:
  - `Content-Type: text/csv`
  - `Content-Disposition: attachment; filename="inventory_import_template.csv"`
  - Content:
    ```csv
    name,category_slug,sku,barcode,current_quantity,unit,cost_per_unit,selling_price,purchase_date,expiry_date,storage_requirement,storage_location
    Fresh Spinach 250g,leafy-greens,PRD-SPIN-250,012345678912,50,packs,0.80,1.99,2026-10-22,2026-10-27,REFRIGERATED,Produce Chiller 2
    ```

---

## 8. Expiry Tracking & Alerts Endpoints

### 8.1 `GET /api/v1/inventory/expiring`
Queries items approaching expiry segmented by severity thresholds.

- **Access**: Authenticated
- **Query Parameters**:
  - `status` (string, optional): `CRITICAL`, `EXPIRING_SOON`, `EXPIRED`, `ALL_AT_RISK`
  - `days_threshold` (int, optional): custom override threshold (e.g., `5` days).
  - `category_id` (string, optional).
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "summary": {
      "expired_count": 2,
      "critical_count": 5,
      "warning_count": 12,
      "total_at_risk_value": 348.50
    },
    "items": [
      {
        "id": "inv_88e0b621-1234-5678-abcd-000000000001",
        "name": "Fresh Whole Milk 1L",
        "category_name": "Dairy & Eggs",
        "current_quantity": 42.00,
        "unit": "liters",
        "expiry_date": "2026-10-25",
        "days_remaining": 2.50,
        "severity": "EXPIRING_SOON",
        "recommended_action": "MARK_FOR_DONATION"
      }
    ]
  }
}
```

---

### 8.2 `GET /api/v1/alerts/config` & `PUT /api/v1/alerts/config`
Retrieves or updates the tenant's expiry threshold preferences.

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`
- **Request Body (PUT)**:
```json
{
  "critical_threshold_hours": 36,
  "warning_threshold_days": 4,
  "notice_threshold_days": 7,
  "auto_flag_for_donation": true,
  "email_notifications_enabled": true
}
```
- **Response (200 OK)**: Returns updated configuration.

---

## 9. POS Integration REST Endpoints

### 9.1 `POST /api/v1/pos/integrations`
Configures a new POS provider adapter (Square, Clover, Toast, Generic).

- **Access**: `BUSINESS_OWNER`
- **Request Body**:
```json
{
  "provider": "SQUARE",
  "integration_name": "POS Register Terminal #1"
}
```
- **Response (201 Created)**:
```json
{
  "success": true,
  "data": {
    "integration_id": "pos_11a2b3c4-4567-8901-23de-f01234567890",
    "provider": "SQUARE",
    "integration_name": "POS Register Terminal #1",
    "webhook_url": "https://api.foodwasteplatform.example/api/v1/pos/webhook/pos_11a2b3c4-4567-8901-23de-f01234567890",
    "webhook_signing_secret": "whsec_7f9a2b8c4d1e3f6a5b8c9d0e1f2a3b4c",
    "note": "Save the webhook_signing_secret now. It will not be shown again."
  }
}
```

---

### 9.2 `POST /api/v1/pos/webhook/{slug}`
Public callback endpoint invoked by external POS systems upon sales or inventory transactions.

- **Access**: Public / HMAC Authenticated via `X-POS-Signature`
- **Headers**:
  - `X-POS-Signature`: `sha256=<HMAC_HEX_DIGEST>`
  - `X-Idempotency-Key`: `evt_sq_987654321`
- **Request Body**:
```json
{
  "event_type": "order.completed",
  "order_id": "sq_ord_881234",
  "timestamp": "2026-10-22T20:45:00Z",
  "line_items": [
    {
      "sku": "DAI-MILK-001",
      "quantity": 2.00,
      "unit_price": 2.49
    }
  ]
}
```
- **Response (200 OK - Processed)**:
```json
{
  "success": true,
  "data": {
    "order_id": "sq_ord_881234",
    "status": "PROCESSED",
    "items_decremented": 1,
    "unmatched_skus": []
  }
}
```
- **Security Rejection (401 Unauthorized)**: Returned if `X-POS-Signature` does not match HMAC of payload body.

---

## 10. Surplus Donation Foundation Endpoints (Milestones 2 & 3 Support)

### 10.1 `POST /api/v1/donations/listings`
Earmarks an at-risk inventory lot for donation redistribution and places a `DONATION_HOLD` transaction on physical stock.

- **Access**: `BUSINESS_OWNER`, `STORE_MANAGER`
- **Request Body**:
```json
{
  "inventory_item_id": "inv_88e0b621-1234-5678-abcd-000000000001",
  "quantity": 20.00,
  "pickup_address": "123 Market St, San Francisco, CA (Rear Dock)",
  "pickup_instructions": "Bring chilled insulated boxes. Ask for Warehouse Manager.",
  "available_from": "2026-10-23T08:00:00Z",
  "available_until": "2026-10-24T18:00:00Z"
}
```
- **Response (201 Created)**:
```json
{
  "success": true,
  "data": {
    "listing_id": "sur_99d0e1f2-5678-9012-34ef-012345678901",
    "status": "AVAILABLE",
    "item_name": "Fresh Whole Milk 1L",
    "quantity_listed": 20.00,
    "remaining_retail_stock": 22.00,
    "available_until": "2026-10-24T18:00:00Z"
  }
}
```
