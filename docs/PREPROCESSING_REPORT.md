# ML Data Preprocessing & Cleaning Audit Report

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 2 — Machine Learning Demand Forecasting & Food Waste Prediction  
**Phase**: Phase 2 — Data Cleaning, Preprocessing, Feature Engineering & ML-Ready Dataset Generation  
**Date**: October 24, 2026  
**Auditor**: Senior Machine Learning Engineer, Data Engineer, QA Engineer  

---

## 1. Executive Summary

Milestone 2, Phase 2 implements a production-grade, zero-leakage time series cleaning, resampling, and preprocessing pipeline. The pipeline transforms raw transactional ledger events and historical daily observations into gap-free, leakage-free, standardized datasets ready for statistical and machine-learning demand forecasting.

All 6 controlled irregularities introduced in benchmark datasets were successfully detected and remediated according to deterministic audit rules.

### Pipeline Execution Summary

| Metric | Raw Value | Processed / Interim Value | Net Change / Action |
| :--- | :---: | :---: | :--- |
| **Raw Transaction Records** | 8,617 | 8,616 | 1 exact duplicate dropped |
| **Missing Product SKUs** | 0 | 0 | 0 dropped |
| **Missing Timestamps** | 3 | 3 | Sequence-based chronological imputation |
| **Non-Canonical Measurement Units** | 2 | 2 | Standardized `lbs` $\to$ `kg` (factor: 0.453592) |
| **Inverted Delta Signs** | 1 | 1 | Standardized positive `POS_SALE` to negative |
| **Ledger Math Mismatches** | 1 | 1 | Reconciled: $Q_{\text{after}} = Q_{\text{before}} + \Delta$ |
| **Negative Prices / Costs** | 0 | 0 | Enforced non-negative invariant |
| **Raw Daily Observations** | 6,935 | 6,935 | Full 365-day continuous grid across 19 SKUs |
| **Missing Calendar Dates Imputed** | 0 unobserved | 6,935 complete | Filled zero sales/waste, forward-filled stock |
| **Minimum History Validation** | 19 SKUs | 19 SKUs | 19/19 satisfy $\ge 28$ day threshold |

---

## 2. Granular Data Cleaning & Standardization Rules

The cleaning engine ([`backend/app/ml/data_cleaner.py`](file:///D:/Waste%20management/backend/app/ml/data_cleaner.py)) enforces 7 deterministic cleaning rules:

### Rule 1: Mandatory SKU Association
- **Condition**: Transaction rows where `sku` is null, empty string, or whitespace.
- **Action**: Immediate record rejection.
- **Rationale**: An inventory movement without a product identifier cannot update inventory balances or inform SKU-level demand forecasts.

### Rule 2: Transaction ID Deduplication
- **Condition**: Multiple rows sharing the identical `transaction_id`.
- **Action**: Retain earliest occurrence in sequence order; drop duplicates.
- **Audit**: Logged in `data/processed/cleaning_summary.json`. 1 duplicate removed from benchmark history.

### Rule 3: Sequence-Based Timestamp Imputation
- **Condition**: Transaction record with valid `transaction_id` and `sku` but missing `timestamp`.
- **Action**: Forward-fill timestamp from the preceding transaction in sequential log order; fallback to backward-fill.
- **Audit**: 3 missing timestamps imputed cleanly.

### Rule 4: Unit Normalization
- **Condition**: Inbound vendor or legacy POS systems reporting in non-metric units (`lbs`, `oz`, `fluid_oz`).
- **Action**: Convert quantities to canonical platform units using exact conversion factors:
  - $Q_{\text{kg}} = Q_{\text{lbs}} \times 0.45359237$
  - $Q_{\text{g}} = Q_{\text{oz}} \times 28.3495231$
  - $V_{\text{liters}} = V_{\text{fluid\_oz}} \times 0.0295735$
- **Audit**: 2 non-canonical unit transactions converted to canonical units.

### Rule 5: Directional Sign Enforcement
- **Condition**: Outflows (`POS_SALE`, `WASTE_DISPOSAL`) recorded with positive quantity change, or inflows (`PURCHASE`, `RESTOCK`) recorded with negative quantity change.
- **Action**: Force negative sign for outflows: $\Delta = -|\Delta|$. Force positive sign for inflows: $\Delta = |\Delta|$.
- **Audit**: 1 corrupted POS sale delta inverted to negative.

### Rule 6: Double-Entry Ledger Balance Reconciliation
- **Condition**: $|Q_{\text{after}} - (Q_{\text{before}} + \Delta)| > 0.01$.
- **Action**: Overwrite $Q_{\text{after}}$ with ground-truth mathematical sum $Q_{\text{before}} + \Delta$.
- **Audit**: 1 ledger arithmetic corruption corrected.

### Rule 7: Non-Negative Financial Guardrails
- **Condition**: `unit_cost < 0` or `selling_price < 0`.
- **Action**: Convert to absolute non-negative value.

---

## 3. Time Series Resampling & Continuous Calendar Grid

The time series engine ([`backend/app/ml/time_series_prep.py`](file:///D:/Waste%20management/backend/app/ml/time_series_prep.py)) constructs unbroken daily observation series:

1. **Gap-Free Reindexing**: Every SKU's timeline is reindexed against `pd.date_range(min_date, max_date, freq="D")`.
2. **Sales Imputation**: Days without recorded store transactions are filled with `recorded_sales = 0.0` and `waste_quantity = 0.0` (zero customer activity).
3. **Inventory Forward-Fill**: Closing inventory balance is forward-filled from the most recent prior day ($I_t = I_{t-1}$).
4. **Stockout Censoring**: If $I_t \le 0$, the day is flagged with `is_stockout = True`. In Phase 3, this prevents model training on suppressed demand periods.

---

## 4. Syntetos-Boylan Demand Classification

Each SKU's demand series is analyzed along two orthogonal dimensions:
- **Average Demand Interval (ADI)**: $\frac{N}{\sum_{t=1}^N \mathbb{I}(y_t > 0)}$
- **Squared Coefficient of Variation ($CV^2$)**: $\left(\frac{\sigma_{\text{non-zero}}}{\mu_{\text{non-zero}}}\right)^2$

### Classification Distribution (19 SKUs):
- **Smooth** ($ADI < 1.32, CV^2 < 0.49$): **17 SKUs (89.5%)** — High-velocity staple items (milk, bananas, bread, chicken breast, tomatoes, etc.) with regular daily purchasing patterns.
- **Intermittent** ($ADI \ge 1.32, CV^2 < 0.49$): **2 SKUs (10.5%)** — Gourmet/specialty items (e.g. Specialty Gluten-Free Flour, Organic Saffron Rice) purchased every 2–4 days in consistent quantities.
- **Erratic** ($ADI < 1.32, CV^2 \ge 0.49$): **0 SKUs (0.0%)**.
- **Lumpy** ($ADI \ge 1.32, CV^2 \ge 0.49$): **0 SKUs (0.0%)**.

---

## 5. Data Provenance & Realism Notice

The 365-day historical dataset used in this phase (`data/raw/synthetic_daily_supermarket_history.csv`) is a mathematically rigorous synthetic benchmark dataset mirroring an operational suburban supermarket. The live SQLite database (`waste_management.db`) was initialized in Milestone 1 and contains master catalog data and seeded categories, but does not yet contain 365 days of live retail checkout transactions.

All claims in this report are grounded strictly in the verified benchmark datasets in `data/raw/` and `data/processed/`. No false claims of operational deployment are made.
