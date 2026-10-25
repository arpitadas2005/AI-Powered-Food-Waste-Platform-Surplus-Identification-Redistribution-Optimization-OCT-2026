# Forecast & Waste-Risk REST API Contract

## 1. Overview & Authentication
All endpoints are mounted under `/api/v1` and protected by JWT Bearer token authentication with tenant isolation:
- Base URL: `http://localhost:8000/api/v1`
- Authorization: `Bearer <jwt_token>` (Claims include `tenant_id`, `role`, `sub`)
- Multi-Tenancy: Strictly enforced via `TenantContext`. Cross-tenant queries return `404 NOT FOUND` or `403 FORBIDDEN`.

---

## 2. Endpoints Summary

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/forecasts/health` | Model health, loaded artifacts, fallback status | No |
| `GET` | `/forecasts/sku/{sku}` | Daily trajectory & 80% intervals for a specific SKU | Yes |
| `GET` | `/forecasts/summary` | Aggregate multi-SKU portfolio forecast | Yes |
| `POST` | `/waste-risk/evaluate` | On-demand risk assessment for an item or ad-hoc payload | Yes |
| `GET` | `/waste-risk/alerts` | Filter active surplus alerts by minimum risk tier | Yes |
| `GET` | `/waste-risk/reorders` | Active smart replenishment recommendations | Yes |
| `POST` | `/waste-risk/batch-evaluate` | Trigger immediate tenant-wide batch risk evaluation | Yes (Manager/Owner) |

---

## 3. Endpoint Specifications

### 3.1 Model Health Check
**`GET /forecasts/health`**
- **Description**: Returns model loading status, model file paths, feature cache counts, and fallback activation state.
- **Response** (`200 OK`):
```json
{
  "status": "HEALTHY",
  "is_using_fallback": false,
  "models": {
    "model_1d_loaded": true,
    "model_1d_path": "data/models/champion_1d_forecaster.joblib",
    "model_7d_loaded": true,
    "model_7d_path": "data/models/champion_7d_forecaster.joblib"
  },
  "reference_skus_cached": 15,
  "checked_at": "2026-10-25T04:15:00.123456"
}
```

---

### 3.2 Single-SKU Multi-Horizon Forecast
**`GET /forecasts/sku/{sku}?horizon_days=7`**
- **Parameters**:
  - `sku` (path, string, required): Product SKU belonging to the authenticated tenant.
  - `horizon_days` (query, integer, optional, default: 7, min: 1, max: 28): Forecast trajectory window.
- **Tenant Isolation**: If the SKU does not exist or belongs to another tenant, returns `404 Not Found`.
- **Response** (`200 OK`):
```json
{
  "sku": "DAI-MILK-01",
  "product_name": "Whole Milk 1L",
  "horizon_days": 7,
  "predicted_7d_demand": 142.50,
  "daily_forecasts": [
    {
      "date": "2026-10-26",
      "horizon_step": 1,
      "predicted_sales": 20.35,
      "lower_bound_80": 17.50,
      "upper_bound_80": 23.20
    },
    {
      "date": "2026-10-27",
      "horizon_step": 2,
      "predicted_sales": 19.80,
      "lower_bound_80": 16.90,
      "upper_bound_80": 22.70
    }
  ],
  "model_used": "champion_random_forest",
  "generated_at": "2026-10-25T04:15:00.123456"
}
```

---

### 3.3 Forecast Summary
**`GET /forecasts/summary?horizon_days=7&limit=50`**
- **Description**: Returns multi-SKU forecasted demand across tenant active inventory items.
- **Response** (`200 OK`):
```json
{
  "tenant_id": "tenant-abc-123",
  "horizon_days": 7,
  "total_predicted_units": 1845.20,
  "sku_summaries": [
    {
      "sku": "DAI-MILK-01",
      "product_name": "Whole Milk 1L",
      "predicted_demand": 142.50,
      "daily_average": 20.36
    }
  ],
  "model_used": "champion_multi_horizon_forecasters",
  "generated_at": "2026-10-25T04:15:00.123456"
}
```

---

### 3.4 Waste-Risk Evaluation
**`POST /waste-risk/evaluate`**
- **Request Body**:
```json
{
  "item_id": "item-uuid-1234",
  "sku": "PRO-APP-01",
  "current_stock": 50.0,
  "days_to_expiry": 2.5,
  "unit_cost": 1.20
}
```
- **Response** (`200 OK`):
```json
{
  "item_id": "item-uuid-1234",
  "sku": "PRO-APP-01",
  "product_name": "Honeycrisp Apples",
  "unit": "kg",
  "current_stock": 50.0,
  "days_to_expiry": 2.5,
  "predicted_demand_to_expiry": 15.2,
  "expected_surplus": 34.8,
  "surplus_ratio": 0.696,
  "value_at_risk": 41.76,
  "risk_tier": "HIGH",
  "recommended_action": "AGGRESSIVE_MARKDOWN_OR_DONATE",
  "model_name": "champion_random_forest",
  "assessed_at": "2026-10-25T04:15:00.123456"
}
```

---

### 3.5 Waste-Risk Active Alerts
**`GET /waste-risk/alerts?min_tier=HIGH`**
- **Parameters**:
  - `min_tier` (query, string, optional, default: "HIGH", enum: `["MEDIUM", "HIGH", "CRITICAL"]`).
- **Response** (`200 OK`): Array of active items meeting the risk threshold.

---

### 3.6 Smart Reorder Recommendations
**`GET /waste-risk/reorders`**
- **Response** (`200 OK`): Array of active replenishment recommendations.
```json
[
  {
    "id": "rec-uuid-123",
    "item_id": "item-uuid-456",
    "sku": "DAI-YOG-01",
    "current_stock": 10.0,
    "predicted_daily_demand": 14.5,
    "lead_time_days": 2,
    "safety_stock": 7.67,
    "reorder_point": 36.67,
    "recommended_reorder_quantity": 90.0,
    "status": "RECOMMENDED",
    "reason": "Current stock (10.00) <= ROP (36.67). Target replenishment: 90.00 units.",
    "is_blocked_by_expiry_risk": false,
    "generated_at": "2026-10-25T04:15:00.123456"
  }
]
```

---

### 3.7 Trigger Batch Evaluation
**`POST /waste-risk/batch-evaluate`**
- **Authorization**: Requires `BUSINESS_OWNER`, `STORE_MANAGER`, or `SYSTEM_ADMIN`.
- **Response** (`200 OK`):
```json
{
  "tenant_id": "tenant-abc-123",
  "items_evaluated": 42,
  "errors": 0,
  "risk_counts": {
    "CRITICAL": 3,
    "HIGH": 7,
    "MEDIUM": 12,
    "LOW": 20
  },
  "reorders_recommended_count": 8,
  "reorders_blocked_by_expiry": 4,
  "executed_at": "2026-10-25T04:15:00.123456",
  "elapsed_ms": 32.4
}
```
