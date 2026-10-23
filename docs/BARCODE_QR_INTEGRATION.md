# Barcode & QR Code Scanning Integration Specification

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 6 — Barcode/QR Scanning and POS REST API Integration  
**Status**: APPROVED SPECIFICATION  

---

## 1. Supported Identifier Formats

The platform supports rapid physical inventory identification across industry-standard symbologies:

| Barcode / QR Symbology | Format Characteristics | Target Use Case | Example Raw Value |
| :--- | :--- | :--- | :--- |
| **UPC-A** | 12 numeric digits | North American retail packaged groceries | `012345678905` |
| **EAN-13** | 13 numeric digits | Global retail merchandise and packaged food | `5012345678900` |
| **EAN-8** | 8 numeric digits | Small consumer packages (candies, spices) | `96385074` |
| **Code 128** | Variable alphanumeric | Internal warehouse lots, bin tags, batch codes | `LOT-2026-CHIL-01` |
| **QR Code (Plain)** | Alphanumeric string | SKU code, product URL, or item UUID | `SKU-DAIRY-001` |
| **Structured QR JSON** | Serialized JSON dictionary | Smart GS1-style QR codes embedding barcode, SKU, batch, and expiry | `{"barcode": "012345678905", "sku": "DAI-MILK-100", "batch": "LOT-A"}` |

---

## 2. Scanning Interface & User Workflows

### 2.1 Camera Stream Lifecycle
- **Explicit User Activation**: Camera video streams (`getUserMedia({ video: { facingMode: "environment" } })`) are initialized only when the user explicitly clicks the "Start Camera" action.
- **Permission Recovery**: Displays clear permission recovery guidance when camera access is denied by the browser.
- **Resource Teardown**: Camera media tracks are stopped immediately upon modal close, tab blur, or component unmount.
- **Continuous Stream Decoding**: Decodes live frames using `@zxing/browser` or HTML5 `BarcodeDetector` with continuous debounce (1.5-second cooldown between duplicate triggers).
- **Manual Input Fallback**: A manual input field and "Search Identifier" button are persistently accessible for devices without functional cameras or insecure HTTP contexts.

### 2.2 Explicit Confirmation Safeguard
$$\mathbf{CRITICAL\ RULE}:\ \text{Never silently change inventory upon barcode detection.}$$

When a code is resolved:
1. The system fetches the matching item details (name, category, current balance, expiry date, storage location).
2. The UI renders an **Explicit Action Modal**:
   - Stock Deduction (Sale / Consumption)
   - Stock Increment (Restock)
   - Waste Discard
   - Cancel Action
3. Stock adjustments generate a UUIDv4 idempotency key to prevent accidental duplicate clicks.

---

## 3. Backend Lookup Architecture

Endpoint: `GET /api/v1/inventory/lookup?code={identifier}`

```
Client Scanned Code
         │
         ▼
[Format Detection] ────► [Structured QR JSON Parsing]
         │                              │
         ▼                              ▼
Query by Barcode (`barcode == :code`)   Extract embedded barcode / SKU
         │
         ├───► Found: Return Item + Type ("UPC_OR_EAN" / "BARCODE")
         │
         └───► Not Found ───► Fallback: Query by SKU (`sku == :code`)
                                    │
                                    ├───► Found: Return Item + Type ("SKU")
                                    │
                                    └───► Not Found: Return 404 (`BARCODE_UNREGISTERED`)
```

### Tenant Boundary Isolation
- Queries strictly filter by `tenant_id == current_tenant.id`.
- If Tenant B scans a barcode belonging to Tenant A, the endpoint returns `404 Not Found` with code `BARCODE_UNREGISTERED`. Zero cross-tenant metadata is revealed.
