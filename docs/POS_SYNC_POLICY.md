# POS Synchronization Policy & Idempotent Stock Deduction Rules

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 6 — Barcode/QR Scanning and POS REST API Integration  
**Status**: APPROVED SPECIFICATION  

---

## 1. Webhook Ingestion & Stock Deduction Policy

When a retail sale occurs at an external Point-of-Sale terminal:

1. **Webhook Reception**: The external provider POSTs to `/api/v1/pos/webhook/{provider}`.
2. **Signature Verification**: The raw byte payload is validated against the stored HMAC-SHA256 signature header. Invalid signatures fail immediately with `401 Unauthorized` without reading payload JSON.
3. **Idempotency & Replay Protection**:
   - The webhook event carries an external order identifier (`order_id`).
   - The application constructs a deterministic idempotency key:
     `pos_wh_{integ_id[:8]}_{order_id[:30]}_{idx}_{item_id[:8]}`
   - If an event with this idempotency key was previously processed, the system returns `200 OK` with `status: ALREADY_PROCESSED` without double-decrementing stock.
4. **Unit Normalization**: External vendor measurement units (`lbs`, `oz`, `grams`, `liters`) are automatically mapped to standard platform units.
5. **Inventory Decrement**:
   - Matches item by SKU or Barcode within the active tenant partition.
   - Atomically decrements `current_quantity`.
   - Records an immutable `StockTransaction` with:
     - `transaction_type = "POS_SALE"`
     - `reference_type = "POS_ORDER"`
     - `reference_id = idempotency_key`
     - `reason = "POS sale via {provider} order #{order_id}"`

---

## 2. Unmatched SKU Policy (Triage Queue)

If a sales webhook arrives for a product SKU or barcode that does not exist in the tenant's inventory:
1. The transaction is **not dropped silently**.
2. An audit log is written to `audit_events` with `event_type = "POS_UNMATCHED_SKU"`.
3. The event payload is stored in the unmatched triage queue for staff to link to an existing item or create a new inventory record.

---

## 3. Catalog Synchronization Policy

When an on-demand catalog sync is triggered (`POST /api/v1/pos/integrations/{id}/sync`):
- Paginates through external items (default 100 per page).
- Updates catalog metadata (selling price, product name) if matched by SKU.
- **Local physical stock is NEVER overwritten silently**. Stock changes require explicit confirmation or dedicated sales webhook events.
