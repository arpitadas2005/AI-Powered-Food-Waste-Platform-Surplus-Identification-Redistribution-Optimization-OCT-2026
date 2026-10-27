# Analytics & Sustainability REST API Contract (API v1)

## Milestone 3 — Phase 3 Deliverable

All endpoints reside under the `/api/v1/analytics` path prefix and require JWT Bearer authentication or development test headers (`X-Test-User-Id`, `X-Test-Tenant-Id`).

---

## 1. Endpoints Summary

| Method | Path | Required Role(s) | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/business/summary` | `BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF`, `SYSTEM_ADMIN` | High-level commercial inventory, waste risk, surplus listings, claims, and pickups. |
| `GET` | `/api/v1/analytics/ngo/summary` | `RECIPIENT_NGO`, `SYSTEM_ADMIN` | Recipient NGO intake overview, available surplus, claims status, and meals served. |
| `GET` | `/api/v1/analytics/sustainability` | All authenticated roles | Verified environmental (EPA WARM v15), social (meals), and financial impact metrics. |
| `GET` | `/api/v1/analytics/time-series` | All authenticated roles | Chronological time-series redistribution points for line and bar chart rendering. |
| `GET` | `/api/v1/analytics/export/csv` | All authenticated roles | Streaming CSV export of completed transfers with formula-injection sanitization. |

---

## 2. Endpoint Details

### 2.1 GET `/api/v1/analytics/business/summary`

Returns executive operational and risk metrics for the authenticated food business tenant.

#### Request Headers
```http
Authorization: Bearer <JWT_TOKEN>
```

#### Response (200 OK)
```json
{
  "success": true,
  "data": {
    "tenant_id": "tenant_a_green_grocer",
    "tenant_name": "Green Grocer Downtown",
    "total_inventory_items": 42,
    "total_stock_value": 3480.50,
    "items_expiring_soon_count": 6,
    "at_risk_value": 412.00,
    "high_risk_items_count": 4,
    "active_surplus_listings_count": 3,
    "pending_claims_count": 2,
    "upcoming_pickups_count": 1,
    "completed_transfers_count": 8,
    "cancelled_or_expired_listings_count": 1,
    "total_value_rescued": 620.00,
    "total_food_rescued_kg": 155.0,
    "co2e_avoided_kg": 387.50,
    "meals_provided": 369,
    "recent_activity": [
      {
        "type": "claim",
        "id": "claim_uuid_123",
        "listing_id": "listing_uuid_456",
        "listing_title": "Organic Greek Yogurt 1kg",
        "claimed_quantity": 20.0,
        "unit": "kg",
        "status": "COMPLETED",
        "created_at": "2026-10-27T14:30:00Z"
      }
    ]
  }
}
```

#### Error (403 Forbidden)
```json
{
  "success": false,
  "error": {
    "code": "HTTP_ERROR",
    "message": "NGO organizations should access /api/v1/analytics/ngo/summary instead.",
    "details": null,
    "request_id": "req_abc123"
  }
}
```

---

### 2.2 GET `/api/v1/analytics/ngo/summary`

Returns operational intake and impact metrics for the authenticated recipient organization.

#### Response (200 OK)
```json
{
  "success": true,
  "data": {
    "tenant_id": "tenant_ngo_community_pantry",
    "organization_name": "Metropolitan Food Rescue",
    "organization_type": "FOOD_BANK",
    "is_verified": true,
    "service_radius_km": 25.0,
    "accepted_categories": ["Dairy & Eggs", "Bakery", "Produce"],
    "storage_facilities": ["AMBIENT", "REFRIGERATED"],
    "eligible_surplus_listings_count": 5,
    "pending_claims_count": 2,
    "accepted_claims_count": 1,
    "upcoming_pickups_count": 1,
    "completed_collections_count": 12,
    "total_food_rescued_kg": 340.50,
    "total_food_rescued_units": 45.0,
    "meals_provided": 810,
    "value_received": 1420.75,
    "recent_claims": [
      {
        "claim_id": "claim_uuid_789",
        "listing_id": "listing_uuid_456",
        "listing_title": "Surplus Sourdough Bread Loaves",
        "quantity": 15.0,
        "unit": "kg",
        "status": "READY_FOR_PICKUP",
        "donor_tenant_id": "tenant_b_artisan_bakery",
        "pickup_time": "2026-10-28T10:00:00Z",
        "created_at": "2026-10-27T16:00:00Z"
      }
    ]
  }
}
```

---

### 2.3 GET `/api/v1/analytics/sustainability`

Returns verified EPA WARM v15 and Feeding America impact metrics computed exclusively from `COMPLETED` transfers.

#### Query Parameters
* `date_from` *(optional, string)*: Filter start date (`YYYY-MM-DD`).
* `date_to` *(optional, string)*: Filter end date (`YYYY-MM-DD`).
* `tenant_id` *(optional, string, Admin only)*: Target tenant override.

#### Response (200 OK)
```json
{
  "success": true,
  "data": {
    "total_rescued_weight_kg": 500.0,
    "total_rescued_units_count": 50.0,
    "total_value_rescued": 2100.00,
    "co2e_avoided_kg": 1250.0,
    "total_meals_provided": 1190,
    "completed_claims_count": 18,
    "participating_businesses_count": 3,
    "participating_ngos_count": 4,
    "equivalencies": {
      "co2e_avoided_kg": 1250.0,
      "trees_planted_equivalent": 57.42,
      "passenger_car_miles_avoided": 3180.66
    },
    "category_breakdown": [
      {
        "category_id": "cat_produce",
        "category_name": "Produce & Fresh Greens",
        "rescued_kg": 280.0,
        "rescued_units": 0.0,
        "value_rescued": 840.00,
        "co2e_avoided_kg": 700.0,
        "meals_provided": 666
      },
      {
        "category_id": "cat_dairy_eggs",
        "category_name": "Dairy & Eggs",
        "rescued_kg": 220.0,
        "rescued_units": 50.0,
        "value_rescued": 1260.00,
        "co2e_avoided_kg": 550.0,
        "meals_provided": 523
      }
    ],
    "methodology_notes": "EPA WARM v15: 2.5 kg CO2e avoided per kg food rescued. Feeding America benchmark: 0.42 kg (1.2 lbs) per meal equivalent. Trees equivalent: 21.77 kg CO2/tree. Car miles: 0.393 kg CO2e/mile."
  }
}
```

---

### 2.4 GET `/api/v1/analytics/time-series`

Provides continuous time-series data for interactive SVG chart rendering.

#### Query Parameters
* `date_from` *(optional, string)*: Start date (`YYYY-MM-DD`). Default: 30 days ago.
* `date_to` *(optional, string)*: End date (`YYYY-MM-DD`). Default: today.
* `interval` *(optional, string)*: `"daily"` (default) or `"monthly"`.

#### Response (200 OK)
```json
{
  "success": true,
  "data": {
    "interval": "daily",
    "start_date": "2026-09-27",
    "end_date": "2026-10-27",
    "total_points": 3,
    "points": [
      {
        "date": "2026-10-15",
        "rescued_kg": 45.0,
        "claims_count": 2,
        "co2e_avoided_kg": 112.50,
        "meals_provided": 107,
        "value_rescued": 190.00
      },
      {
        "date": "2026-10-22",
        "rescued_kg": 80.0,
        "claims_count": 3,
        "co2e_avoided_kg": 200.00,
        "meals_provided": 190,
        "value_rescued": 340.00
      }
    ]
  }
}
```

---

### 2.5 GET `/api/v1/analytics/export/csv`

Streams a formula-injection-sanitized CSV file download.

#### Response Headers
```http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="redistribution_sustainability_report_2026-10-27.csv"
```

#### CSV Body Example
```csv
Claim ID,Completed Date,Listing Title,Category,Donor Business,Recipient Organization,Claimed Quantity,Unit,Normalized Weight (kg),Estimated Value ($),Avoided CO2e (kg),Meal Equivalents,Claim Status
claim_001,2026-10-25 14:20:00,Surplus Bread Loaves,Bakery,Artisan Bakery Uptown,Metropolitan Food Rescue,20.00,kg,20.00,60.00,50.00,47,COMPLETED
claim_002,2026-10-26 09:15:00,'=cmd|'/C calc'!A0,Dairy & Eggs,Green Grocer Downtown,Metropolitan Food Rescue,10.00,kg,10.00,40.00,25.00,23,COMPLETED
```
*(Notice that the second row listing title begins with `'=` to neutralize spreadsheet formula injection).*
