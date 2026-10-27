# Explainable NGO Matching Engine & Ranking Specification

**Document Version:** 1.0.0  
**Phase:** Milestone 3 — Phase 1  
**Target Roles:** Backend Architects, Optimization Engineers, Data Scientists

---

## 1. Executive Summary

The **Explainable NGO Matching Engine** evaluates active recipient organizations (food banks, soup kitchens, community pantries, homeless shelters) against surplus food listings to recommend optimal redistribution partners.

### Core Objectives
1. **Explainability First:** Every match score ($0.0 - 100.0$) provides explicit, transparent rationale bullet points explaining why the NGO was recommended.
2. **Cold-Chain Safety Gate:** High-risk perishable food (refrigerated, frozen) is never recommended to organizations lacking verified cold-chain storage facilities.
3. **No Geographic Fabrication:** When GPS coordinates are missing on either side, distances are **never fabricated or assumed to be zero**. A neutral proximity baseline is assigned with the explicit note `"Distance unverified (coordinates not configured)"`.

---

## 2. Multi-Factor Scoring Weight Distribution

| Component | Max Points | Weight | Criteria & Evaluation |
| :--- | :---: | :---: | :--- |
| **Category Compatibility** | 30.0 pts | 30% | Direct or wildcard match in NGO's `accepted_categories`. |
| **Capacity Fit** | 25.0 pts | 25% | Ratio of listing quantity to NGO's `max_capacity_units`. Optimal at $\le 75\%$. |
| **Storage & Cold Chain** | 20.0 pts | 20% | Capability match between `storage_requirement` and `storage_facilities`. |
| **Proximity (Haversine)** | 15.0 pts | 15% | Inverse distance decay within `service_radius_km` ($15 \times (1 - d/R)$). |
| **Shelf-Life Urgency** | 10.0 pts | 10% | Escalates as expiry approaches ($\le 24\text{h}: 10\text{ pts}, \le 48\text{h}: 8\text{ pts}$). |
| **Verification Bonus** | +5.0 pts | +5% | Applied if NGO is verified (`is_verified = True`). |
| **Total Score Ceiling** | **100.0 pts** | **100%** | $\min\left(100.0, \sum \text{factors}\right)$ |

---

## 3. Detailed Component Algorithms

### A. Cold-Chain & Storage Safety Gate (20 pts)
```python
if req in ("CHILLED", "REFRIGERATED", "COLD"):
    if any(f in facilities for f in ("REFRIGERATED", "CHILLED", "COLD_ROOM", "FROZEN")):
        score = 20.0, safe = True
    else:
        score = 0.0, safe = False  # ELIMINATED FROM RECOMMENDATIONS
```
Perishable food requiring cold storage is hard-filtered if the recipient NGO only supports ambient storage.

### B. Category Compatibility (30 pts)
- If `accepted_categories` is empty, `"ALL"`, or contains `*`: Award 30.0 pts.
- If category matches directly or as case-insensitive substring: Award 30.0 pts.
- If NGO explicitly maintains a list of accepted categories and the item's category is absent: Award 0.0 pts (and filtered out if strict).

### C. Capacity Fit (25 pts)
Let $r = \frac{Q_{\text{listing}}}{\text{max\_capacity}}$:
- $r \le 0.25$: 25.0 pts (easily absorbed).
- $0.25 < r \le 0.75$: 22.0 pts (optimal batch utilization).
- $0.75 < r \le 1.00$: 18.0 pts (near capacity ceiling).
- $1.00 < r \le 1.50$: 10.0 pts (exceeds typical single drop).
- $r > 1.50$: 2.0 pts (excessive batch size).

### D. Proximity & Missing Coordinates Rule (15 pts)
#### Great-Circle Haversine Formula
Given $(lat_1, lon_1)$ and $(lat_2, lon_2)$ with Earth radius $R = 6371.0\text{ km}$:

$$\Delta \phi = \text{radians}(lat_2 - lat_1), \quad \Delta \lambda = \text{radians}(lon_2 - lon_1)$$

$$a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\text{radians}(lat_1))\cos(\text{radians}(lat_2))\sin^2\left(\frac{\Delta \lambda}{2}\right)$$

$$d = 2 R \cdot \text{atan2}\left(\sqrt{a}, \sqrt{1 - a}\right)$$

#### Coordinates Handling
- **When coordinates exist and $d \le \text{service\_radius\_km}$:**
  $$\text{Score} = 15.0 \times \max\left(0.1, 1.0 - \frac{d}{\text{service\_radius}}\right)$$
  $$\text{Reason: "Within service range (4.2 km <= 25.0 km radius)"}$$
- **When coordinates exist and $d > \text{service\_radius\_km}$:**
  $$\text{Score} = 0.0, \quad \text{Reason: "Outside service radius (32.1 km > 25.0 km radius)"}$$
- **When coordinates are missing:**
  $$\text{Score} = 7.5\text{ (Neutral)}, \quad \text{distance\_km} = \text{null}$$
  $$\text{Reason: "Distance unverified (coordinates not configured)"}$$

### E. Shelf-Life Urgency (10 pts)
$$\text{Days to Expiry } \tau = (\text{expiry\_date} - \text{today})_{\text{days}}$$
- $\tau \le 1.0$: 10.0 pts (`Critical rescue urgency (≤24 hours to expiry)`)
- $1.0 < \tau \le 2.0$: 8.0 pts (`High urgency (≤48 hours to expiry)`)
- $2.0 < \tau \le 4.0$: 6.0 pts (`Moderate rescue window (≤4 days to expiry)`)
- $\tau > 4.0$: 4.0 pts (`Stable shelf life (X days remaining)`)

---

## 4. Verification & Explainability Sample

```json
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
```
