# Food Taxonomy & Expiry Classification Specification

**Document Version**: 1.0  
**Phase**: Milestone 1 — Phase 5  
**Reference Standards**: USDA FoodKeeper Guide (2024), FDA Food Code (2022 §3-501.17), Codex Alimentarius (CXC 1-1969)

---

## 1. Overview & Architectural Principles

The AI-Powered Food Waste Management Platform manages diverse food categories across supermarkets, restaurants, bakeries, and wholesale facilities. Because perishability, food safety hazards, and shelf-life dynamics differ drastically between food types, the platform explicitly avoids uniform or naive expiration assumptions.

### Key Tenets
1. **Differentiated Shelf-Life Rules**: Every category defines explicit temperature, humidity, and default shelf-life parameters grounded in regulatory standards.
2. **Tenant Extensibility**: Global baseline categories are provided out-of-the-box (`tenant_id = NULL`), while tenants can configure custom categories or override thresholds.
3. **Food Safety vs. Waste Risk Distinction**:
   - **Quality Date / Best By**: Indicates optimal flavor and texture (USDA FoodKeeper). Items approaching this date remain safe but are at high risk of commercial write-off.
   - **Safety / Use By / Expiry Date**: Mandatory safety cutoff for perishable TCS (Time/Temperature Control for Safety) foods.
   - **Mandatory Safety Rule**: Expired items (`days_remaining <= 0`) are legally and ethically ineligible for redistribution or food bank donation. They are flagged exclusively for disposal, compost, or anaerobic digestion.

---

## 2. Food Perishability Tiers

| Tier | Category Scope | Risk Profile | Standard Action Window | Regulatory Reference |
|:---|:---|:---|:---|:---|
| **CRITICAL** | Raw poultry, seafood, ground meats, leafy greens, unpasteurized dairy, prepared cooked foods | Extreme pathogen risk (*Listeria*, *Salmonella*). Rapid spoilage. | 24 - 48 hours | FDA Food Code 2022 §3-501.17 (7-day max for ready-to-eat TCS food held at $\le 41^\circ\text{F}$) |
| **HIGH** | Dairy products, artisan bread, fresh pastries, cut fruit, processed deli meats | Moderate pathogen and mold risk. Sensory degradation within days. | 2 - 5 days | USDA FoodKeeper - Dairy & Bakery |
| **MEDIUM** | Hard fruits, root vegetables, citrus, hard cheeses, whole eggs | Slow spoilage, moisture loss, texture softening. Non-hazardous degradation. | 7 - 14 days | USDA FoodKeeper - Produce |
| **LOW** | Dry goods, pasta, rice, pulses, canned goods, frozen food | Shelf-stable. Extremely low microbiological risk; sensory/nutritional loss over months/years. | 30 - 365+ days | USDA FoodKeeper - Shelf Stable |

---

## 3. Storage Requirements & Environmental Constraints

| Storage Regime | Temp Range ($^\circ\text{C}$) | Humidity Range (%) | Target Categories | Critical Control Points (CCP) |
|:---|:---:|:---:|:---|:---|
| **REFRIGERATED** | $0.0^\circ\text{C} - 4.0^\circ\text{C}$ | Uncontrolled / $85-95\%$ for produce | Meat, Poultry, Seafood, Dairy, Prepared Meals, Leafy Greens | Temp must never exceed $4.0^\circ\text{C}$ ($40^\circ\text{F}$). Pathogen multiplication threshold. |
| **FROZEN** | $\le -18.0^\circ\text{C}$ | Uncontrolled | Frozen Meat, Frozen Vegetables, Ice Cream | Continuous deep freeze; defrost cycles must be monitored. |
| **AMBIENT** | $18.0^\circ\text{C} - 22.0^\circ\text{C}$ | Ambient | Fresh Bakery, Bread, Selected Fruits | Protect from direct sunlight and pest vectors. |
| **DRY_PANTRY** | $15.0^\circ\text{C} - 24.0^\circ\text{C}$ | $< 60\%$ Relative Humidity | Flour, Grains, Canned Goods, Spices | Humidity control prevents moisture absorption and mold growth. |
| **CLIMATE_CONTROLLED** | $10.0^\circ\text{C} - 15.0^\circ\text{C}$ | $70 - 85\%$ Relative Humidity | Potatoes, Onions, Hard Squash, Apples | Prevents early sprouting while retarding fungal rot. |

---

## 4. Standard Global Taxonomy

| Category Slug | Display Name | Perishability Tier | Storage Requirement | Default Shelf Life | Temp Range ($^\circ\text{C}$) |
|:---|:---|:---:|:---:|:---:|:---:|
| `dairy-and-eggs` | Dairy & Eggs | `HIGH` | `REFRIGERATED` | 14 days | $2.0^\circ\text{C} - 4.0^\circ\text{C}$ |
| `fresh-meat-and-poultry` | Fresh Meat & Poultry | `CRITICAL` | `REFRIGERATED` | 3 days | $0.0^\circ\text{C} - 2.0^\circ\text{C}$ |
| `seafood-and-fish` | Seafood & Fish | `CRITICAL` | `REFRIGERATED` | 2 days | $0.0^\circ\text{C} - 2.0^\circ\text{C}$ |
| `leafy-greens-and-soft-produce` | Leafy Greens & Soft Produce | `CRITICAL` | `REFRIGERATED` | 5 days | $4.0^\circ\text{C} - 7.0^\circ\text{C}$ |
| `root-vegetables-and-hard-fruits`| Root Vegetables & Hard Fruits| `MEDIUM` | `AMBIENT` / `CLIMATE`| 14 days | $10.0^\circ\text{C} - 15.0^\circ\text{C}$ |
| `fresh-bakery-and-pastries` | Fresh Bakery & Pastries | `HIGH` | `AMBIENT` | 3 days | $18.0^\circ\text{C} - 22.0^\circ\text{C}$ |
| `prepared-and-cooked-meals` | Prepared & Cooked Meals | `CRITICAL` | `REFRIGERATED` | 2 days | $2.0^\circ\text{C} - 4.0^\circ\text{C}$ |
| `pantry-and-dry-goods` | Pantry & Dry Goods | `LOW` | `DRY_PANTRY` | 180 days | $15.0^\circ\text{C} - 24.0^\circ\text{C}$ |
| `canned-and-preserved-goods` | Canned & Preserved Goods | `LOW` | `DRY_PANTRY` | 365 days | $15.0^\circ\text{C} - 24.0^\circ\text{C}$ |

---

## 5. Expiry Risk Classification Engine

### Threshold Definitions & Evaluation Intervals
Tenant alert profiles are stored in `tenant_alert_configs` and define three configurable evaluation horizons:

$$\text{Time Remaining } (\Delta t) = \text{Expiry Timestamp}_{\text{local}} - \text{Current Timestamp}_{\text{local}}$$

| Classification State | Mathematical Condition | Inventory Status | Automated Action | Donation Eligibility |
|:---|:---|:---|:---|:---:|
| **`EXPIRED`** | $\Delta t \le 0$ hours | `EXPIRED` | Flag for Spoilage Write-Off / Compost | **STRICTLY INELIGIBLE** |
| **`CRITICAL`** | $0 < \Delta t \le T_{\text{crit}}$ (Default: 24h) | `EXPIRING_SOON` | Priority Donation Dispatch / Flash Sale | **ELIGIBLE** |
| **`WARNING`** | $T_{\text{crit}} < \Delta t \le T_{\text{warn}}$ (Default: 3 days) | `EXPIRING_SOON` | Dynamic Mark-Down (25-50% off) | **ELIGIBLE** |
| **`NOTICE`** | $T_{\text{warn}} < \Delta t \le T_{\text{notice}}$ (Default: 7 days) | `EXPIRING_SOON` | Early Notification to Floor Staff | **ELIGIBLE** |
| **`FRESH`** | $\Delta t > T_{\text{notice}}$ | `ACTIVE` | Normal Rotation (FIFO) | Ineligible (Standard Stock) |

### Timezone Strategy & Boundary Normalization
1. **Storage Format**: `expiry_date` is stored as an ISO `Date` (`YYYY-MM-DD`).
2. **Local End-of-Day Anchor**: In retail food distribution, an item labeled "Best before 2026-10-25" is legally salable until the end of business on that calendar date in the store's physical timezone.
3. **Calculation Rule**:
   $$\text{Expiry Moment} = \text{datetime.combine}(expiry\_date, \text{time}(23, 59, 59, 999999), \text{tz}=\text{Tenant.timezone})$$
4. **Current Comparison**:
   $$\text{Current Moment} = \text{datetime.now}(\text{tz}=\text{Tenant.timezone})$$
5. **Exact Days Remaining**:
   $$\text{days\_remaining} = \frac{(\text{Expiry Moment} - \text{Current Moment}).\text{total\_seconds}()}{86,400.0}$$
   - If $\text{Current Moment} > \text{Expiry Moment}$, $\text{days\_remaining} \le 0$.
   - A date expiring today has $0.0 < \text{days\_remaining} < 1.0$ until the local clock strikes midnight.

---

## 6. Alert Deduplication Architecture

To avoid alert fatigue and duplicate notifications:
1. When the evaluation service runs (on-demand or via cron), it evaluates each active item.
2. An alert record in `expiry_alert_history` is created **only if**:
   - No alert has ever been recorded for this `(tenant_id, item_id, alert_level)`.
   - OR the item's previous alert was at a lower severity (e.g. state transitioned from `NOTICE` $\rightarrow$ `WARNING` $\rightarrow$ `CRITICAL`).
   - OR at least 24 hours have elapsed since an identical unacknowledged alert was logged.
3. If an item has already generated a `CRITICAL` alert and remains unacknowledged within the same threshold period, repeated runs skip duplicate notification logging.
