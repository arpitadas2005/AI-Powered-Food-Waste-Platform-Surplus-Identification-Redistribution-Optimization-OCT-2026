# Surplus Redistribution & NGO Matching REST API Contract

**Version:** 1.0.0  
**Base Path:** `/api/v1/surplus`  
**Authentication:** Standard HTTP Bearer JWT (`Authorization: Bearer <token>`) or Development Headers (`X-Test-User-Id`, `X-Test-Tenant-Id`)

---

## Endpoints Summary

| Method | Path | Required Role(s) | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/listings` | `BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF` | Create new surplus listing from inventory item. |
| `GET` | `/listings` | Authenticated | List surplus listings (donor-scoped or public marketplace). |
| `GET` | `/listings/{id}` | Authenticated | Retrieve details of a specific surplus listing. |
| `PUT` | `/listings/{id}` | `BUSINESS_OWNER`, `STORE_MANAGER` | Update listing details or quantity. |
| `POST` | `/listings/{id}/cancel` | `BUSINESS_OWNER`, `STORE_MANAGER` | Cancel listing and release inventory hold. |
| `GET` | `/listings/{id}/matches` | `BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF` | Run explainable multi-factor NGO matching engine. |
| `POST` | `/claims` | `RECIPIENT_NGO` | Submit claim reservation against active listing. |
| `GET` | `/claims/my` | `RECIPIENT_NGO` | List claims submitted by the authenticated NGO. |
| `GET` | `/listings/{id}/claims` | `BUSINESS_OWNER`, `STORE_MANAGER` | List incoming claims for a donor's listing. |
| `POST` | `/claims/{id}/review` | `BUSINESS_OWNER`, `STORE_MANAGER` | Approve or reject an incoming NGO claim. |
| `POST` | `/claims/{id}/complete` | `BUSINESS_OWNER`, `STORE_MANAGER` | Confirm pickup and deduct physical inventory. |
| `POST` | `/claims/{id}/cancel` | Authenticated (Claim Owner or Donor) | Cancel a claim reservation. |
| `GET` | `/ngo/profile` | Authenticated | Retrieve NGO operational capabilities. |
| `PUT` | `/ngo/profile` | `RECIPIENT_NGO`, `BUSINESS_OWNER` | Update NGO accepted categories, cold-chain, radius. |
| `GET` | `/notifications` | Authenticated | Retrieve in-app surplus notifications. |
| `POST` | `/notifications/{id}/read` | Authenticated | Mark a notification as read. |

---

## Key Payloads & Schemas

### 1. `POST /api/v1/surplus/listings`
**Request:**
```json
{
  "item_id": "item-dairy-yogurt",
  "title": "Surplus Greek Yogurt Batch",
  "quantity": 20.0,
  "pickup_address": "123 Market St, Loading Dock 1",
  "pickup_instructions": "Refrigerated transport required",
  "available_until": "2026-10-29T18:00:00Z"
}
```
**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "id": "e6a21...",
    "tenant_id": "tenant-a",
    "item_id": "item-dairy-yogurt",
    "title": "Surplus Greek Yogurt Batch",
    "product_name": "Greek Yogurt Vanilla 500g",
    "category_name": "Dairy & Eggs",
    "quantity": 20.0,
    "remaining_claimable_quantity": 20.0,
    "unit": "units",
    "expiry_date": "2026-10-30",
    "days_to_expiry": 3.0,
    "storage_requirement": "REFRIGERATED",
    "status": "AVAILABLE",
    "claims_count": 0
  }
}
```

### 2. `GET /api/v1/surplus/listings/{id}/matches`
**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "listing_id": "e6a21...",
    "product_name": "Greek Yogurt Vanilla 500g",
    "quantity": 20.0,
    "unit": "units",
    "storage_requirement": "REFRIGERATED",
    "days_to_expiry": 3.0,
    "total_candidates_evaluated": 2,
    "matching_recommendations": [
      {
        "ngo_tenant_id": "tenant_ngo_food_bank",
        "ngo_name": "Metropolitan Food Rescue",
        "organization_type": "FOOD_BANK",
        "is_verified": true,
        "match_score": 95.0,
        "distance_km": 0.05,
        "max_capacity_units": 800.0,
        "storage_facilities": ["AMBIENT", "REFRIGERATED", "FROZEN"],
        "match_reasons": [
          "Equipped with verified refrigeration/cold-storage",
          "Explicitly accepts 'Dairy & Eggs' category",
          "Readily absorbs 20.0 units (under 25% of 800 max capacity)",
          "Within service range (0.05 km <= 30.0 km radius)",
          "High urgency (≤48 hours to expiry)",
          "Verified community recipient bonus (+5.0 pts)"
        ]
      }
    ]
  }
}
```

### 3. `POST /api/v1/surplus/claims/{id}/complete`
**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "claim_123",
    "listing_id": "e6a21...",
    "listing_title": "Surplus Greek Yogurt Batch",
    "ngo_name": "Metropolitan Food Rescue",
    "claimed_quantity": 20.0,
    "unit": "units",
    "status": "COMPLETED"
  }
}
```
*(Inventory ledger automatically updated via `DONATION_DISPATCH`.)*
