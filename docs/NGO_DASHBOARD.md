# NGO Recipient Portal & Allocation Dashboard Specification

## Milestone 3 — Phase 3 Deliverable

---

## 1. Executive Summary

The **NGO Recipient Portal & Allocation Dashboard** provides authorized food relief organizations (food banks, community pantries, soup kitchens, homeless shelters, and charity recipients) with real-time operational visibility into available food donations, pending claim allocations, upcoming logistics collection windows, and community meal impacts.

---

## 2. Organization Profile Integration

Each recipient organization possesses an operational profile record in `ngo_profiles`:
* **Organization Type**: `FOOD_BANK`, `SOUP_KITCHEN`, `COMMUNITY_PANTRY`, `HOMELESS_SHELTER`, or `CHARITY_RECIPIENT`.
* **Verification Gate**: `is_verified` boolean ensures food safety compliance before donations can be collected.
* **Service Radius**: Geographic bounding circle (in kilometers) for logistical pickup feasibility.
* **Accepted Categories**: JSON array of allowable food categories (e.g. `["Dairy & Eggs", "Bakery", "Produce"]`).
* **Cold-Chain Facilities**: Storage capabilities (`AMBIENT`, `REFRIGERATED`, `FROZEN`) preventing cold-chain spoilage.
* **Intake Capacity**: Maximum storage volume in discrete units (`max_capacity_units`).

---

## 3. Core Operational Metrics & Community Impact

| Metric | API Field | Methodology / Calculation |
| :--- | :--- | :--- |
| **Available Surplus Feed** | `eligible_surplus_listings_count` | Active listings in `AVAILABLE` status within the valid donation time window matching accepted categories and cold-chain capacity. |
| **Pending Claims** | `pending_claims_count` | Claims submitted by this NGO in `REQUESTED` or `PENDING` state awaiting donor business review. |
| **Accepted / Ready** | `accepted_claims_count` | Claims approved by businesses (`ACCEPTED`, `APPROVED`, `READY_FOR_PICKUP`) ready for logistics scheduling. |
| **Scheduled Pickups** | `upcoming_pickups_count` | Pickups confirmed in `SCHEDULED`, `RESCHEDULED`, or `READY_FOR_COLLECTION` state. |
| **Completed Collections** | `completed_collections_count` | Successful physical collections confirmed via `COMPLETED` or `COLLECTED` status. |
| **Total Food Rescued** | `total_food_rescued_kg` | Verified food mass received in kilograms across completed claims. |
| **Community Meals Served** | `meals_provided` | Standard meal equivalents calculated via $\text{kg} \div 0.42\text{ kg/meal}$ (USDA & Feeding America standard). |
| **Grocery Budget Value** | `value_received` | Total commercial value of rescued food: $\sum (\text{received\_quantity} \times \text{cost\_per\_unit})$. |

---

## 4. UI Architecture & Workflow

Housed in [`frontend/src/components/DashboardView.tsx`](file:///D:/Waste%20management/frontend/src/components/DashboardView.tsx) under the **NGO Portal** section:
1. **Organization Header Banner**: Visual badge displaying organization name, verification checkmark, service radius, and cold-chain facilities.
2. **Intake Pipeline Cards**: 4 operational cards (Available surplus, Pending claims, Accepted ready, Scheduled pickups).
3. **Mission Impact Metrics**: 4 community impact cards (Total mass rescued, Meals served, Budget value received, Completed transfers).
4. **Recent Claims Table**: Interactive ledger of recent claims showing item description, requested quantity, current workflow status badge, and scheduled pickup timestamps.
5. **Direct Navigation**: 1-click button to browse live surplus feed or schedule collections.

---

## 5. Security & Isolation

NGO dashboards strictly isolate data to the authenticated organization's tenant context:
```sql
SELECT * FROM surplus_claims WHERE ngo_tenant_id = :ngo_tenant_id;
```
An NGO cannot view claims, contact persons, or operational logs belonging to other recipient organizations.
