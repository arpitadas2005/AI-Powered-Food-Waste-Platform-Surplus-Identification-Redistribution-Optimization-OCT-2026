# In-App Notification System
## Milestone 3 — Phase 2 Architecture & Specification

---

## 1. Overview

The surplus food redistribution platform features an event-driven, database-backed in-app notification infrastructure. It keeps commercial food businesses and partner NGOs synchronized in real time across matching, reservation requests, approvals, logistics windows, and handover completion.

> [!NOTE]
> All notifications are persisted directly in the application database (`surplus_notifications`), enabling reliable delivery without relying on third-party email or SMS gateway configurations.

---

## 2. Database Schema: `surplus_notifications`

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | VARCHAR(36) | No | Primary Key (UUIDv4) |
| `tenant_id` | VARCHAR(36) | No | Foreign Key to `tenants.id` (ON DELETE CASCADE, Indexed) |
| `user_id` | VARCHAR(36) | Yes | Foreign Key to `users.id` (Target specific user or null for org-wide) |
| `title` | VARCHAR(255) | No | Short headline of the event |
| `message` | TEXT | No | Full human-readable context and instructions |
| `notification_type` | VARCHAR(50) | No | Event taxonomy classifier (Indexed) |
| `reference_id` | VARCHAR(36) | Yes | ID of linked entity (e.g., `claim_id` or `listing_id`) |
| `is_read` | BOOLEAN | No | Read status flag (Default: `FALSE`, Indexed) |
| `created_at` | DATETIME (TZ) | No | Creation timestamp (Indexed) |

---

## 3. Notification Event Catalog

| Notification Type | Trigger Event | Target Recipient | Content Summary |
| :--- | :--- | :--- | :--- |
| `CLAIM_REQUESTED` | NGO submits a new claim against an active listing. | Food Donor Business | "New Surplus Food Claim Request: <NGO Name> requested X units of <Item>." |
| `CLAIM_APPROVED` | Donor approves the NGO's reservation request. | Recipient NGO | "Claim Request Approved! Please coordinate pickup window." |
| `CLAIM_REJECTED` | Donor declines an incoming claim. | Recipient NGO | "Claim Request Declined: <Reason>." |
| `CLAIM_CANCELLED` | Claim cancelled by either counterpart. | Counterpart Tenant | "Surplus Claim Cancelled: <Reason>." |
| `PICKUP_SCHEDULED` | Pickup window established by counterpart. | Counterpart Tenant | "Pickup Scheduled for <Date> between <Start> and <End>." |
| `PICKUP_RESCHEDULED` | Pickup window modified. | Counterpart Tenant | "Pickup Window Rescheduled to <Date> (<Reason>)." |
| `PICKUP_READY` | Donor marks food packaged at the dock. | Recipient NGO | "Donation Ready for Collection at <Address>." |
| `PICKUP_COLLECTED` | Volunteer driver confirms items in transit. | Counterpart Tenant | "Donation Collected: Items in transit to recipient facility." |
| `PICKUP_MISSED` | Donor flags volunteer no-show. | Recipient NGO | "Pickup Window Missed: Please reschedule immediately." |
| `DONATION_DISPATCHED` | Final physical handover complete; stock deducted. | Recipient NGO | "Donation Handover Complete: Thank you for rescuing surplus food!" |

---

## 4. API Endpoints

### 1. List Notifications
`GET /api/v1/surplus/notifications?unread_only={true|false}&limit={50}`
- Returns paginated list of notifications for the authenticated tenant.
- Ordered by `created_at DESC`.

### 2. Mark Single Notification as Read
`POST /api/v1/surplus/notifications/{id}/read`
- Sets `is_read = TRUE` for the specific notification ID.
- Enforces tenant isolation (returns 404 if notification belongs to another organization).

### 3. Bulk Mark All Read
`POST /api/v1/surplus/notifications/read-all`
- Sets `is_read = TRUE` across all unread notifications for the caller's tenant.
- Returns the total count of updated records: `{ "success": true, "data": 5 }`.

---

## 5. UI Integration & Accessibility

The React frontend surfaces notifications through:
1. **Header Badge Counter**: Displays an alert badge with the real-time unread count.
2. **Notification Popover**:
   - Distinct background highlights for unread (`#F0FDF4`) vs read items (`#FFFFFF`).
   - One-click "Mark all read" trigger.
   - Individual click-to-read interaction.
   - Deep-linking reference to the related claim or surplus listing.
