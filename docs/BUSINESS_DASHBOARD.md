# Food Business Operations & Surplus Dashboard Specification

## Milestone 3 — Phase 3 Deliverable

---

## 1. Executive Summary

The **Business Operations & Surplus Dashboard** provides authenticated commercial food businesses (supermarkets, bakeries, restaurants, wholesalers, distribution centers) with an integrated, real-time command center. It bridges day-to-day commercial stock management, machine-learning waste-risk alerts, and surplus food redistribution workflows into a single interface.

All figures displayed on the business dashboard are calculated directly from persisted SQLite/Postgres database tables (`inventory_items`, `waste_risk_assessments`, `surplus_listings`, `surplus_claims`, `pickup_schedules`, `stock_transactions`), completely eliminating ungrounded mockups or fabricated metrics.

---

## 2. Key Target Personas & Role Permissions

| Role | Access Level | Description |
| :--- | :--- | :--- |
| **`BUSINESS_OWNER`** | Full Read/Write | Executive overview of stock valuation, loss prevention, surplus pipeline, and environmental social impact. |
| **`STORE_MANAGER`** | Operational Read/Write | Daily triage of lots expiring in $\le 3$ days, claim approvals, and logistics handover coordination. |
| **`INVENTORY_STAFF`** | Operational Read | Stock inspection, double-entry adjustment logging, and physical collection verification. |
| **`RECIPIENT_NGO`** | **Blocked (403 Forbidden)** | Recipient organizations are routed to their dedicated NGO portal (`/api/v1/analytics/ngo/summary`). |

---

## 3. Operational Metric Categories & Calculations

### 3.1 Commercial Stock & Financial Valuation
* **Total Stock in Ledger (`total_inventory_items`)**:
  $$\text{Count}(i) \quad \text{where } i.\text{tenant\_id} = T \text{ and } i.\text{is\_active} = \text{True}$$
* **Inventory Valuation (`total_stock_value`)**:
  $$\sum_{i \in \text{ActiveItems}} (i.\text{current\_quantity} \times i.\text{cost\_per\_unit})$$

### 3.2 Expiry & Waste-Risk Horizons
* **Expiring Soon Lots (`items_expiring_soon_count`)**:
  Lots where $i.\text{expiry\_date} \le \text{today} + 3\text{ days}$ or status is `EXPIRING_SOON` / `EXPIRED`.
* **At-Risk Value (`at_risk_value`)**:
  Total cost basis of items within the expiring-soon horizon ($ \le 3$ days).
* **ML Waste-Risk Tier Alert (`high_risk_items_count`)**:
  Count of distinct inventory items flagged `HIGH` or `CRITICAL` risk by the XGBoost/RandomForest demand forecasting engine where forecast demand before expiry is substantially lower than on-hand stock ($ \text{Surplus Ratio} > 0.40 $).

### 3.3 Surplus Donation Pipeline
* **Active Surplus Listings (`active_surplus_listings_count`)**:
  Listings owned by this tenant in `AVAILABLE`, `RESERVED`, or `CLAIMED` status.
* **Incoming Claim Requests (`pending_claims_count`)**:
  Claims submitted by recipient NGOs against this business's listings in `REQUESTED` or `PENDING` state awaiting manager review.
* **Upcoming Scheduled Pickups (`upcoming_pickups_count`)**:
  Logistics pickups scheduled for this business with status `SCHEDULED`, `RESCHEDULED`, or `READY_FOR_COLLECTION`.
* **Completed Redistributions (`completed_transfers_count`)**:
  Claims and pickup transfers marked `COMPLETED`.

### 3.4 Verified Donation Impact
* **Total Food Rescued (`total_food_rescued_kg`)**: Mass (kg) transferred across completed claims.
* **Avoided GHG Emissions (`co2e_avoided_kg`)**: $2.5\text{ kg CO}_2\text{e}$ per kg food (EPA WARM v15).
* **Meal Equivalents (`meals_provided`)**: $1\text{ meal} = 0.42\text{ kg}$ (Feeding America benchmark).
* **Financial Loss Rescued (`total_value_rescued`)**: $ \sum (\text{completed\_quantity} \times \text{cost\_per\_unit}) $.

---

## 4. UI Architecture & Integration

The frontend implementation is housed in [`frontend/src/components/DashboardView.tsx`](file:///D:/Waste%20management/frontend/src/components/DashboardView.tsx) and features:
1. **Critical Expiry Banner**: Alerts staff when lots are expired or within critical 24-hour windows.
2. **Top KPI Cards**: 4 commercial metrics (Stock count, Total valuation, Expiring soon, ML High risk).
3. **Surplus Pipeline Cards**: 4 operational donation metrics (Active listings, Pending requests, Upcoming pickups, Completed transfers).
4. **Quick Action Hub**: 1-click navigation to Barcode Scan, CSV Ingestion, Expiry Engine, and Surplus Hub.
5. **Double-Entry Ledger Log**: Real-time transactions table showing previous stock, adjustment quantity, delta, and audit reasons.
6. **Recent Surplus Activity**: Live feed of claims and pickup requests.

---

## 5. Security & Multi-Tenant Boundary

All metrics are strictly bound to `TenantContext.tenant_id`:
```sql
SELECT COUNT(*) FROM inventory_items WHERE tenant_id = :tenant_id AND is_active = TRUE;
```
A business user from Tenant A cannot observe, query, or infer any inventory or donation data belonging to Tenant B.
