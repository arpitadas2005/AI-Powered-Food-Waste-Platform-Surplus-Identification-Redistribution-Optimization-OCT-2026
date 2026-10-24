# Reproducible Data Profiling and Quality Analysis Report

**Generated**: 2026-10-23 07:56:42
**Date Range**: 2025-10-24 to 2026-10-23 (365 days)
**Total Transaction Events**: 8,617
**Total Daily Item Observations**: 6,935
**Active Products Cataloged**: 19

---

## 1. Transaction Log Data Quality Audit

| Quality Metric | Count / Status | Severity | Remediation Strategy |
| :--- | :---: | :---: | :--- |
| **Missing Timestamps** | 3 | HIGH | Impute from chronological transaction ordering or drop incomplete logs |
| **Duplicate Transaction IDs** | 1 | CRITICAL | Deduplicate records preserving first valid UUID occurrence |
| **Quantity Sign Inconsistencies** | 1 | HIGH | Force absolute value signed according to transaction_type contract |
| **Ledger Math Mismatches** | 1 | CRITICAL | Recompute quantity_after = quantity_before + delta |
| **Non-Canonical Units** | 2 | MEDIUM | Map vendor units (`lbs` -> `kg`, `oz` -> `g`) |
| **Missing Product SKUs** | 0 | CRITICAL | Unlinkable records rejected from training set |

---

## 2. Product Demand Profiling & Sparsity Classification

| SKU | Product Name | Category | Mean (Sales/Day) | Zero % | ADI | CV² | Classification | Stockouts |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `BAK-CROI-01` | Butter Croissants 4pk | Bakery & Bread | 23.47 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `BAK-SOUR-01` | Artisan Sourdough Loaf | Bakery & Bread | 23.52 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `BEV-COLA-01` | Sparkling Mineral Water 750ml | Beverages | 27.16 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `BEV-OJ-01` | Fresh Squeezed Orange Juice 1L | Beverages | 26.94 | 0.0% | 1.0 | 0.07 | **SMOOTH** | 0 |
| `DAI-EGGS-01` | Large Grade A Eggs 12pk | Dairy & Eggs | 19.5 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `DAI-MILK-01` | Whole Milk 1L | Dairy & Eggs | 19.69 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `DEL-SAND-01` | Roast Turkey Club Sandwich | Prepared Foods & Deli | 17.36 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `FRO-PEAS-01` | Frozen Sweet Peas 1kg | Frozen Foods | 15.7 | 0.0% | 1.0 | 0.07 | **SMOOTH** | 0 |
| `FRO-PIZZ-01` | Four Cheese Thin Crust Pizza | Frozen Foods | 15.67 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `MEA-BEEF-01` | Ground Beef 80/20 | Fresh Meat & Poultry | 14.42 | 0.0% | 1.0 | 0.07 | **SMOOTH** | 0 |
| `MEA-CHIC-01` | Chicken Breast Boneless | Fresh Meat & Poultry | 14.32 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `PAN-PAST-01` | Organic Penne Rigate 500g | Pantry & Dry Goods | 11.67 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `PAN-RICE-01` | Basmati Rice 2kg | Pantry & Dry Goods | 11.61 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `PAN-TRUF-01` | White Truffle Infused Olive Oil | Pantry & Dry Goods | 0.06 | 94.0% | 16.43 | 0.0 | **INTERMITTENT** | 0 |
| `PRO-BANA-01` | Cavendish Bananas | Fresh Produce | 30.66 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `PRO-SPIN-01` | Baby Spinach 250g | Fresh Produce | 30.81 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `SEA-CAVI-01` | Sturgeon Caviar Tin 50g | Fresh Seafood | 0.09 | 91.2% | 9.77 | 0.0 | **INTERMITTENT** | 0 |
| `SEA-SALM-01` | Atlantic Salmon Fillet | Fresh Seafood | 9.37 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |
| `SNA-CHIP-01` | Sea Salt Kettle Chips 150g | Snacks & Confectionery | 21.78 | 0.0% | 1.0 | 0.08 | **SMOOTH** | 0 |

---

## 3. Key Statistical Findings & Pipeline Requirements

1. **Censored Demand (Stockouts)**: Recorded sales drop to zero when stock is zero. Using recorded sales alone without an indicator feature `is_stockout` will cause models to systematically under-forecast true customer demand.
2. **Intermittent / Sparse Items**: Luxury and specialty items (`PAN-TRUF-01`, `SEA-CAVI-01`) show >90% zero-demand days and ADI > 5.0. Standard ARIMA or linear models fail on these; they must be modeled with Croston's method, zero-inflated models, or aggregated at category level.
3. **Day-of-Week Seasonality**: Fresh food categories exhibit strong demand peaks on Friday and Saturday (1.35x - 1.50x of weekday volume). Calendar and lag features ($t-7, t-14$) are mandatory.
4. **Strict Featurization Leakage Invariant**: All rolling windows must use `shift(1)` to avoid lookahead contamination. Preprocessing scalers must be fitted exclusively on the chronological training partition.