# Milestone 2 — Machine Learning Dataset Inventory & Provenance Catalog

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 2 — Machine Learning Demand Forecasting & Food Waste Prediction  
**Phase**: Phase 1 — Dataset Audit, Raw Data Profiling and ML Pipeline Design  
**Date**: October 23, 2026  
**Auditor**: Senior Machine Learning Engineer, Data Scientist, Data Engineer  

---

## 1. Executive Summary & Inventory Overview

This catalog inventories all data assets, database entities, and benchmark datasets available in the platform for machine learning demand forecasting and food-waste prediction.

In accordance with strict QA and data integrity rules:
- Real operational database state vs synthetic benchmark datasets are strictly distinguished.
- Zero live operational checkout streams are fabricated.
- The repository has complete, verified relational schemas for inventory, transactions, alerts, and categories from Milestone 1, but has 0 live production supermarket transactions in `waste_management.db` as the platform has not yet been deployed to commercial retail checkout lanes.
- A fully reproducible 365-day synthetic operational supermarket dataset was generated to develop and test data quality profiling, leakage-free feature engineering, and baseline forecasting models.

---

## 2. Dataset Catalog & Schema Specifications

### Asset 1: Operational Database (`waste_management.db`)
- **Location**: `D:\Waste management\waste_management.db`
- **Format**: SQLite 3 (WAL mode, Foreign Keys Enabled)
- **Provenance**: **Real Software Platform Database** (Seeded taxonomy; 0 live retail sales)
- **Entities & Current Row Counts**:
  - `categories`: 9 rows (Standardized perishable and shelf-stable food taxonomy).
  - `tenants`: 0 rows (Populated dynamically during merchant onboarding).
  - `users`: 0 rows.
  - `inventory_items`: 0 rows.
  - `stock_transactions`: 0 rows (Ledger schema ready for `PURCHASE`, `POS_SALE`, `WASTE_DISPOSAL`).
  - `tenant_alert_configs`: 0 rows.
  - `expiry_alert_history`: 0 rows.
  - `pos_integrations`: 0 rows.
  - `surplus_listings`: 0 rows.
- **Collection Frequency**: Real-time event-driven (POS webhooks, CSV uploads, staff manual adjustments).
- **Target Variables Available in Schema**:
  - `stock_transactions.quantity_change` where `transaction_type == 'POS_SALE'` (Sales Demand).
  - `stock_transactions.quantity_change` where `transaction_type == 'WASTE_DISPOSAL'` (Waste Volume).
  - `inventory_items.current_quantity` (Stock on Hand).
  - `inventory_items.expiry_date` (Expiration Timestamp).

---

### Asset 2: Benchmark Daily Supermarket Observations
- **Location**: `data/synthetic_daily_supermarket_history.csv`
- **Format**: RFC 4180 CSV (UTF-8)
- **Provenance**: **Synthetic Simulation for Pipeline Development & Testing** (Generated via `backend/app/ml/dataset_generator.py`, Seed: 42)
- **Record Volume**: **6,935 rows, 17 columns**
- **Date Range**: `2025-10-24` to `2026-10-23` (365 continuous days)
- **Product Coverage**: 19 distinct SKUs across 10 standard food categories (Produce, Dairy, Meat, Bakery, Seafood, Deli, Pantry, Frozen, Beverages, Snacks).
- **Sampling Frequency**: Daily aggregated observation per SKU.
- **Data Dictionary**:
  | Column Name | Data Type | Description | Potential Target / Feature |
  | :--- | :---: | :--- | :--- |
  | `date` | `date` (ISO) | Calendar observation date | Primary time index |
  | `tenant_id` | `string` | Business identifier (`tenant-greengrocer-01`) | Multi-tenant partition key |
  | `sku` | `string` | Unique product identifier (e.g. `PRO-BANA-01`) | Primary entity key |
  | `product_name` | `string` | Item display name | Informational |
  | `category_id` | `string` | Standardized category identifier | Hierarchical grouping feature |
  | `unit` | `string` | Measurement unit (`kg`, `liters`, `units`, `packs`)| Normalization key |
  | `opening_stock`| `float` | Morning inventory balance before sales | Exogenous feature |
  | `restock_quantity`| `float` | Inbound delivery quantity | Supply event |
  | `recorded_sales`| `float` | Actual units sold at POS register | **PRIMARY FORECAST TARGET ($y_t$)** |
  | `latent_demand`| `float` | True customer demand (unconstrained by stock) | Ground-truth benchmarking |
  | `waste_quantity`| `float` | Units discarded/composted due to expiry | **SECONDARY WASTE TARGET ($w_t$)** |
  | `closing_stock`| `float` | Evening inventory balance after sales/waste | State variable ($I_t$) |
  | `is_stockout` | `boolean` | Flag indicating stock dropped to zero | Demand censoring indicator |
  | `unit_cost` | `float` | Wholesale purchase cost per unit | Value-at-risk multiplier |
  | `selling_price`| `float` | Retail sales price per unit | Revenue multiplier |
  | `shelf_life_days`| `integer`| Nominal product shelf life | Perishability constraint |

---

### Asset 3: Benchmark Granular Transaction Logs
- **Location**: `data/synthetic_transactions_supermarket_history.csv`
- **Format**: RFC 4180 CSV (UTF-8)
- **Provenance**: **Synthetic Simulation for Pipeline Development & Testing** (Generated via `backend/app/ml/dataset_generator.py`)
- **Record Volume**: **8,617 rows, 14 columns**
- **Date Range**: `2025-10-24` to `2026-10-23` (365 days)
- **Event Types**:
  - `PURCHASE`: Scheduled replenishment orders (positive quantity delta).
  - `POS_SALE`: Customer register checkout transactions (negative quantity delta).
  - `WASTE_DISPOSAL`: Shelf cull / expired food discard events (negative quantity delta).
- **Injected Controlled Quality Imperfections**:
  - 3 missing/null timestamps (testing chronology imputation).
  - 1 duplicate transaction ID (testing deduplication).
  - 1 positive delta on `POS_SALE` (testing sign enforcement).
  - Non-canonical unit values (`lbs`, `oz`) (testing unit normalization).

---

## 3. Data Acquisition Strategy for Live Commercial Supermarket Data

To transition from synthetic pipeline testing to real operational ML model deployment, the platform defines the following multi-channel data acquisition strategy:

1. **POS Webhook Streaming (Phase 6 Integration)**:
   - Ingest live receipts via Square/Clover webhook endpoints (`POST /api/v1/pos/webhook/{provider}`).
   - Every register barcode scan creates an immutable `POS_SALE` record with exact microsecond timestamp, quantity, and unit.
2. **ERP / Inventory CSV Bulk Sync**:
   - Ingest weekly historical sales registers and spoilage logs using `POST /api/v1/inventory/bulk-import/csv`.
3. **Cold-Start Pre-Training on Public Benchmark Datasets**:
   - Where a new business tenant has $<60$ days of recorded sales, pre-train baseline embeddings and seasonal priors on public supermarket benchmarks (e.g., Favorita Grocery Sales Forecasting / Dunnhumby The Complete Journey) before fine-tuning on the merchant's local data stream.
