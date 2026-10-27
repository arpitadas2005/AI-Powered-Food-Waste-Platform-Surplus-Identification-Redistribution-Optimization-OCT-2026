# Pickup Scheduling & Logistics Engine
## Milestone 3 — Phase 2 Architecture & Specification

---

## 1. Overview

The Pickup Scheduling Engine coordinates logistics, vehicle dispatch, and operational time windows between commercial food donors and recipient NGOs.

It provides:
- **Food Safety Deadline Enforcement**: Guarantees that food items cannot be scheduled for pickup past their expiration date.
- **Bi-Directional Scheduling & Rescheduling**: Allows either donor or recipient to coordinate time windows with documented rationales.
- **Physical Checkpoint Tracking**: Tracks staged milestones (`SCHEDULED`, `RESCHEDULED`, `READY_FOR_COLLECTION`, `COLLECTED`, `COMPLETED`, `MISSED`, `CANCELLED`).
- **Cold-Chain & Vehicle Specifications**: Captures required transport equipment (e.g. refrigerated truck, insulated containers, van) and driver contact details.

---

## 2. Database Schema: `pickup_schedules`

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | VARCHAR(36) | No | Primary Key (UUIDv4) |
| `claim_id` | VARCHAR(36) | No | Unique Foreign Key to `surplus_claims.id` (ON DELETE CASCADE) |
| `listing_id` | VARCHAR(36) | No | Foreign Key to `surplus_listings.id` (ON DELETE CASCADE) |
| `donor_tenant_id` | VARCHAR(36) | No | Foreign Key to donor `tenants.id` |
| `ngo_tenant_id` | VARCHAR(36) | No | Foreign Key to recipient `tenants.id` |
| `pickup_date` | DATE | No | Target pickup calendar date (Indexed) |
| `pickup_start_time` | DATETIME (TZ) | No | Pickup window opening timestamp |
| `pickup_end_time` | DATETIME (TZ) | No | Pickup window closing deadline (Check: end > start) |
| `pickup_location` | TEXT | No | Physical address, loading dock, or facility location |
| `pickup_instructions` | TEXT | Yes | Gate code, buzzer, refrigeration requirements |
| `vehicle_type` | VARCHAR(50) | Yes | `VAN`, `REFRIGERATED_TRUCK`, `CAR`, `CARGO_BIKE`, `OTHER` |
| `driver_name` | VARCHAR(100) | Yes | Assigned driver or volunteer name |
| `driver_phone` | VARCHAR(50) | Yes | Direct contact number for dispatch coordination |
| `status` | VARCHAR(50) | No | Current logistics state (Default: `SCHEDULED`, Indexed) |
| `scheduled_by_user_id` | VARCHAR(36) | No | User ID who established the schedule |
| `rescheduled_count` | INTEGER | No | Number of times window was rescheduled (Default: 0) |
| `rescheduled_reason` | TEXT | Yes | Documented rationale for the most recent reschedule |
| `cancellation_reason` | TEXT | Yes | Documented reason if cancelled or missed |
| `ready_at` | DATETIME (TZ) | Yes | Timestamp when donor marked food ready for collection |
| `collected_at` | DATETIME (TZ) | Yes | Timestamp when volunteer collected items from donor dock |
| `completed_at` | DATETIME (TZ) | Yes | Timestamp of final handover and stock deduction |
| `missed_at` | DATETIME (TZ) | Yes | Timestamp when donor flagged a no-show / missed window |
| `created_at` | DATETIME (TZ) | No | Creation timestamp |
| `updated_at` | DATETIME (TZ) | No | Last update timestamp |

### Check Constraints & Indexes
- Check Constraint: `chk_pickup_time_window (pickup_end_time > pickup_start_time)`
- Index: `idx_pickup_donor_status (donor_tenant_id, status)`
- Index: `idx_pickup_ngo_status (ngo_tenant_id, status)`
- Index: `idx_pickup_date_status (pickup_date, status)`

---

## 3. Pickup Window Validation Rules

The backend executes `validate_pickup_window(pickup_start_time, pickup_end_time, listing)` before accepting any schedule creation or update:

1. **Logical Progression**: `pickup_start_time < pickup_end_time`. Start time must precede end time.
2. **No Historical Scheduling**: `pickup_start_time >= now() - 15 minutes` (15-minute grace period for immediate coordination).
3. **Food Safety Deadline Gate**:
   $$\text{pickup\_end\_time} \le \text{datetime}(\text{listing.expiry\_date}, 23:59:59\text{ UTC})$$
   Food safety regulations mandate that surplus food cannot be picked up or distributed after its expiry date. If the proposed window exceeds the item's expiration date, the request is rejected with `InvalidPickupWindowError` (HTTP 400).
4. **Listing Availability Boundary**: If `listing.available_until` is defined, `pickup_start_time <= listing.available_until`.

---

## 4. Rescheduling Engine

When logistical delays or vehicle breakdowns occur:
1. Either the NGO or the donor business calls `POST /api/v1/surplus/claims/{id}/reschedule`.
2. A non-empty `rescheduled_reason` (min 3 characters) is strictly mandatory.
3. The proposed window is validated against the food shelf-life.
4. The system:
   - Updates `pickup_date`, `pickup_start_time`, `pickup_end_time`.
   - Increments `rescheduled_count += 1`.
   - Stores `rescheduled_reason`.
   - Transitions `status` to `RESCHEDULED`.
   - Dispatches a `PICKUP_RESCHEDULED` in-app notification to the counterpart.
   - Logs `SURPLUS_PICKUP_RESCHEDULE` in the operational audit trail.

---

## 5. Milestone Progression & Handover

```
SCHEDULED / RESCHEDULED
         │
         ▼  (Donor: mark_pickup_ready)
READY_FOR_COLLECTION   ───> Claim: READY_FOR_PICKUP
         │
         ▼  (NGO: confirm_pickup_collection)
     COLLECTED         ───> Claim: PICKED_UP
         │
         ▼  (Donor: complete_surplus_transfer)
     COMPLETED         ───> Claim: COMPLETED & Stock Deducted
```

### Missed Pickup Handling
If the volunteer or vehicle fails to arrive within the scheduled window:
1. Donor calls `POST /api/v1/surplus/claims/{id}/missed`.
2. Schedule moves to `MISSED` with timestamp `missed_at`.
3. In-app notification `PICKUP_MISSED` alerts the NGO coordinator to contact the donor and reschedule immediately.

---

## 6. Cascade Cancellation Rules

- **Claim Cancellation**: When an NGO or donor cancels an active claim, any linked `PickupSchedule` in a non-terminal state (`SCHEDULED`, `RESCHEDULED`, `READY_FOR_COLLECTION`) is automatically transitioned to `CANCELLED` with `cancellation_reason = "Claim cancelled: <reason>"`.
- **Listing Cancellation**: When a donor cancels a surplus listing, all active claims and all active pickup schedules across all recipient NGOs are automatically transitioned to `CANCELLED` with notifications dispatched.
