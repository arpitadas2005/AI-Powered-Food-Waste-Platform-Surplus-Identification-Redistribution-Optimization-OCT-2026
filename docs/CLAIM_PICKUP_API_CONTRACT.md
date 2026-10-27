# Claim Management & Pickup Scheduling API Contract
## Milestone 3 — Phase 2 REST API Specification

---

## 1. Overview

Base URL: `/api/v1/surplus`

All requests require JWT Bearer Authentication (`Authorization: Bearer <token>`). Multi-tenant scoping and role permissions are strictly enforced. Responses follow the standard `SuccessEnvelope[T]` or `PaginatedResponse[T]` schema.

---

## 2. Endpoint Index

| Method | Endpoint | Description | Roles |
| :--- | :--- | :--- | :--- |
| `POST` | `/claims` | Submit surplus food claim | `RECIPIENT_NGO`, `SYSTEM_ADMIN` |
| `GET` | `/claims/my` | List NGO's own claims | `RECIPIENT_NGO`, `SYSTEM_ADMIN` |
| `GET` | `/listings/{id}/claims` | List claims received for donor listing | `BUSINESS_OWNER`, `STORE_MANAGER`, `SYSTEM_ADMIN` |
| `POST` | `/claims/{id}/review` | Approve or reject claim request | `BUSINESS_OWNER`, `STORE_MANAGER`, `SYSTEM_ADMIN` |
| `POST` | `/claims/{id}/schedule` | Schedule pickup window for claim | `RECIPIENT_NGO`, `BUSINESS_OWNER`, `STORE_MANAGER`, `SYSTEM_ADMIN` |
| `POST` | `/claims/{id}/reschedule` | Reschedule pickup window with reason | `RECIPIENT_NGO`, `BUSINESS_OWNER`, `STORE_MANAGER`, `SYSTEM_ADMIN` |
| `POST` | `/claims/{id}/ready` | Mark donation packaged & ready at dock | `BUSINESS_OWNER`, `STORE_MANAGER`, `INVENTORY_STAFF`, `SYSTEM_ADMIN` |
| `POST` | `/claims/{id}/collect` | Confirm collection in-transit | `RECIPIENT_NGO`, `BUSINESS_OWNER`, `STORE_MANAGER`, `SYSTEM_ADMIN` |
| `POST` | `/claims/{id}/complete` | Confirm physical handover & deduct stock | `BUSINESS_OWNER`, `STORE_MANAGER`, `SYSTEM_ADMIN` |
| `POST` | `/claims/{id}/missed` | Flag missed pickup / volunteer no-show | `BUSINESS_OWNER`, `STORE_MANAGER`, `SYSTEM_ADMIN` |
| `POST` | `/claims/{id}/cancel` | Cancel claim & release reservation | Authenticated Tenant Owner |
| `GET` | `/claims/{id}/schedule` | Get pickup schedule for a claim | Authenticated Tenant Owner |
| `GET` | `/pickups` | List scheduled pickups (paginated) | Authenticated Tenant Owner |
| `POST` | `/notifications/read-all` | Mark all notifications as read | Authenticated Tenant Owner |

---

## 3. Detailed Request / Response Payloads

### 3.1 `POST /claims/{id}/schedule`

**Request Body**:
```json
{
  "pickup_date": "2026-10-28",
  "pickup_start_time": "2026-10-28T10:00:00Z",
  "pickup_end_time": "2026-10-28T12:00:00Z",
  "pickup_location": "Dock 4, Bay 2",
  "pickup_instructions": "Ring buzzer at gate",
  "vehicle_type": "VAN",
  "driver_name": "Elena Driver",
  "driver_phone": "+1-555-4321"
}
```

**Response (HTTP 201 Created)**:
```json
{
  "success": true,
  "data": {
    "id": "sched_9876",
    "claim_id": "claim_1234",
    "listing_id": "listing_5678",
    "listing_title": "Surplus Honeycrisp Apples",
    "donor_tenant_id": "tenant_grocer_a",
    "donor_name": "Green Grocer Downtown",
    "ngo_tenant_id": "tenant_harbor_ngo",
    "ngo_name": "Harbor Community Kitchen",
    "pickup_date": "2026-10-28",
    "pickup_start_time": "2026-10-28T10:00:00Z",
    "pickup_end_time": "2026-10-28T12:00:00Z",
    "pickup_location": "Dock 4, Bay 2",
    "pickup_instructions": "Ring buzzer at gate",
    "vehicle_type": "VAN",
    "driver_name": "Elena Driver",
    "driver_phone": "+1-555-4321",
    "status": "SCHEDULED",
    "scheduled_by_user_id": "user_elena",
    "scheduled_by_user_name": "Elena Driver",
    "rescheduled_count": 0,
    "rescheduled_reason": null,
    "cancellation_reason": null,
    "ready_at": null,
    "collected_at": null,
    "completed_at": null,
    "missed_at": null,
    "created_at": "2026-10-27T16:00:00Z",
    "updated_at": "2026-10-27T16:00:00Z"
  }
}
```

---

### 3.2 `POST /claims/{id}/reschedule`

**Request Body**:
```json
{
  "pickup_date": "2026-10-29",
  "pickup_start_time": "2026-10-29T14:00:00Z",
  "pickup_end_time": "2026-10-29T16:00:00Z",
  "rescheduled_reason": "Van alternator maintenance delay",
  "driver_name": "Marcus Logistics"
}
```

**Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "data": {
    "id": "sched_9876",
    "status": "RESCHEDULED",
    "rescheduled_count": 1,
    "rescheduled_reason": "Van alternator maintenance delay",
    "pickup_date": "2026-10-29",
    "pickup_start_time": "2026-10-29T14:00:00Z",
    "pickup_end_time": "2026-10-29T16:00:00Z"
  }
}
```

---

### 3.3 `POST /claims/{id}/ready`

**Request**: No body required. Authenticated by donor business.

**Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "data": {
    "id": "sched_9876",
    "status": "READY_FOR_COLLECTION",
    "ready_at": "2026-10-28T09:45:00Z"
  }
}
```

---

### 3.4 `POST /claims/{id}/collect`

**Request**: No body required. Authenticated by recipient NGO or donor business.

**Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "data": {
    "id": "sched_9876",
    "status": "COLLECTED",
    "collected_at": "2026-10-28T10:15:00Z"
  }
}
```

---

### 3.5 `POST /claims/{id}/complete`

**Request**: No body required. Authenticated by donor business.

**Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "data": {
    "id": "claim_1234",
    "status": "COMPLETED",
    "claimed_quantity": 20.0,
    "unit": "kg",
    "pickup_schedule": {
      "id": "sched_9876",
      "status": "COMPLETED",
      "completed_at": "2026-10-28T10:30:00Z"
    }
  }
}
```

---

### 3.6 `GET /pickups`

**Query Parameters**:
- `status`: Optional filter (e.g. `SCHEDULED`, `READY_FOR_COLLECTION`, `COLLECTED`)
- `date_from`: `YYYY-MM-DD`
- `date_to`: `YYYY-MM-DD`
- `page`: default 1
- `size`: default 50 (max 100)

**Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "data": [
    {
      "id": "sched_9876",
      "claim_id": "claim_1234",
      "listing_id": "listing_5678",
      "listing_title": "Surplus Honeycrisp Apples",
      "pickup_date": "2026-10-28",
      "pickup_start_time": "2026-10-28T10:00:00Z",
      "pickup_end_time": "2026-10-28T12:00:00Z",
      "status": "SCHEDULED"
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

### 3.7 `POST /notifications/read-all`

**Request**: No body required.

**Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "data": 4
}
```
