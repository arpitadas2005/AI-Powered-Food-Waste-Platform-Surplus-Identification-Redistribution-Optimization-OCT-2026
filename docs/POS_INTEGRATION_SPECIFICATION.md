# POS Integration Specification & Provider Adapter Architecture

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 6 — Barcode/QR Scanning and POS REST API Integration  
**Status**: APPROVED SPECIFICATION  

---

## 1. Provider-Independent Adapter Contract

All POS adapters implement the abstract base class `BasePOSAdapter`:

```python
class BasePOSAdapter(ABC):
    @abstractmethod
    def verify_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """Verify HMAC-SHA256 signature against stored webhook secret."""
        pass

    @abstractmethod
    def parse_sales_event(self, payload: Dict[str, Any]) -> List[POSSaleItem]:
        """Normalize vendor payload into standardized POSSaleItem list."""
        pass

    @abstractmethod
    def sync_inventory_catalog(self, page_size: int = 100) -> POSCatalogSyncResult:
        """Fetch external product catalog with pagination."""
        pass
```

---

## 2. Supported POS Provider Adapters

### 2.1 Square POS Adapter (`SquarePOSAdapter`)
- **Webhook Event**: `order.updated` / `payment.updated`.
- **HMAC Signature**: Validates `X-Square-HMAC-SHA256` header using the tenant's webhook signing key.
- **Unit Normalization**: Maps Square measurement units (`SQUARE_MEASUREMENT_UNIT_KILOGRAM` $\to$ `kg`, `SQUARE_MEASUREMENT_UNIT_LITER` $\to$ `liters`, etc.).

### 2.2 Clover POS Adapter (`CloverPOSAdapter`)
- **Webhook Event**: `ORDERS` notification.
- **HMAC Signature**: Validates `X-Clover-Signature` using SHA-256 HMAC digest.
- **Unit Normalization**: Maps Clover `unitOfMeasure` strings to lowercase standard representations.

### 2.3 Generic REST Adapter (`GenericPOSAdapter`)
- Standardized open webhook format for custom ERPs, Shopify, Lightspeed, or legacy register systems.
- Verifies `X-POS-Signature: sha256=<hex_digest>`.

---

## 3. Mock Adapter for Safe Testing

In development and isolated testing environments where live merchant developer accounts are unavailable:
- The `GenericPOSAdapter` acts as a deterministic mock adapter.
- Accepts synthetic sales orders and catalog payloads.
- Exercises the complete parsing, unit normalization, database lookup, and transaction ledger pipeline.
- Simulates rate limits (HTTP 429), timeouts, and duplicate replay attacks.

---

## 4. Secret Protection & Redaction

1. **At-Rest Hashing**:
   - `api_key_hash`: SHA-256 hash of the API key string (`VARCHAR(64)`).
   - `webhook_secret_hash`: SHA-256 hash of the webhook signing secret (`VARCHAR(64)`).
   - Plaintext credentials are **never stored** in the database.
2. **API Response Redaction**:
   - Outbound REST schemas (`PosIntegrationResponse`) strictly omit hash values and raw secrets.
   - Newly created integrations receive a single-view secret banner on registration (`POST /api/v1/pos/integrations`), which is never readable thereafter.
