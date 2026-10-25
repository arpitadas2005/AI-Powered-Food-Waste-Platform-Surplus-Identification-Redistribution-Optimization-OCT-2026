# Milestone 2 — Machine Learning Implementation Status

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 2 — Machine Learning Demand Forecasting & Food Waste Prediction  
**Phase**: Phase 4 — Waste Risk Scoring, Smart Reorder Recommendations & Forecast API Integration  
**Date**: October 25, 2026  
**Status**: **PHASE 4 COMPLETE (Verified & Ready for Milestone Acceptance)**  

---

## 1. Milestone 2 Overview & Roadmap

Milestone 2 advances the platform from inventory tracking and expiry monitoring to proactive demand forecasting and predictive surplus prevention.

| Phase | Description | Status | Verification Summary |
| :---: | :--- | :---: | :--- |
| **Phase 1** | **Dataset Audit, Raw Data Profiling & ML Pipeline Design** | **COMPLETE** | Audited repository, generated 365-day benchmark dataset, built reproducible profiling pipeline, designed zero-leakage feature engineering, created baseline specs and risk formulas. All 8 tests passing. |
| **Phase 2** | **Data Cleaning, Preprocessing & Feature Engineering** | **COMPLETE** | Ingested and cleaned raw transactional and daily datasets, constructed unbroken calendar grids, engineered 27 leakage-free predictive features, generated multi-horizon targets, partitioned chronologically (70/15/15), isolated scalers on Train split, and verified zero lookahead leakage. 12 automated tests passing. |
| **Phase 3** | **Forecasting Model Development, Training & Evaluation** | **COMPLETE** | Implemented Baselines (Naive, Seasonal Naive, MA, Mean) and candidate ML models (Ridge, GBDT, Random Forest). Validated on 15% validation split: Random Forest champion for 1-day ahead (12.94% Val WAPE, 15.05% Test WAPE, 40% error reduction over baseline), Ridge champion for 7-day cumulative demand (5.53% Val WAPE, 7.03% Test WAPE). Authored 11 automated tests (31/31 ML tests passing, 98/98 total). |
| **Phase 4** | **Waste Risk Scoring, Smart Reorder Recommendations & Forecast API Integration** | **COMPLETE** | Built modular Waste-Risk Scoring Engine with 4 explainable risk tiers (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`); built Smart Replenishment Engine with safety stock ($Z=1.65$) and expiry-risk suppression guard; created persistence models and Alembic migration; exposed FastAPI REST endpoints under `/forecasts` and `/waste-risk` with strict multi-tenant isolation; built `BatchPredictionJob` and CLI runner. 12 new automated tests passing (43/43 ML tests passing, 121/121 total project tests passing, 100%). |
| **Phase 5** | **Surplus Marketplace & Food Bank Donation Dispatcher** | *NEXT MILESTONE* | Milestone 3 scope: Marketplace listings, NGO matching, and redistribution logistics. |

---

## 2. Phase 4 Verification Matrix

| Requirement | Description | Status | Evidence / Artifacts |
| :--- | :--- | :---: | :--- |
| **M2-P4-REQ-1** | Model Inference Service & Fallback | **PASS** | Implemented [`backend/app/ml/inference_service.py`](file:///D:/Waste%20management/backend/app/ml/inference_service.py). Caches champion models (`RandomForest` for 1-day, `Ridge` for 7-day). Features fallback to `SeasonalNaive` if models are offline. Zero-latency SKU feature lookup. Health probe endpoint. |
| **M2-P4-REQ-2** | Waste-Risk Assessment Engine | **PASS** | Implemented [`backend/app/ml/waste_risk_service.py`](file:///D:/Waste%20management/backend/app/ml/waste_risk_service.py). Subtracts active surplus reservations (`AVAILABLE`, `RESERVED`, `CLAIMED`), calculates expected surplus, surplus ratio, value-at-risk, and 4 explainable risk tiers (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`). Documented in [`docs/WASTE_RISK_SCORING.md`](file:///D:/Waste%20management/docs/WASTE_RISK_SCORING.md). |
| **M2-P4-REQ-3** | Smart Replenishment & Reorders | **PASS** | Implemented [`backend/app/ml/smart_reorder_service.py`](file:///D:/Waste%20management/backend/app/ml/smart_reorder_service.py). Calculates lead-time demand, dynamic safety stock ($Z=1.65$), storage caps, and **Expiry Risk Suppression Guard** (blocks replenishment orders when item has `HIGH` or `CRITICAL` risk). Documented in [`docs/SMART_REORDER_ENGINE.md`](file:///D:/Waste%20management/docs/SMART_REORDER_ENGINE.md). |
| **M2-P4-REQ-4** | Persistence Models & Alembic Migration | **PASS** | Created `WasteRiskAssessmentRecord` and `SmartReorderRecord` in [`backend/app/models/waste_risk.py`](file:///D:/Waste%20management/backend/app/models/waste_risk.py). Applied Alembic migration `671449d6bca3_create_waste_risk_and_smart_reorder_.py`. |
| **M2-P4-REQ-5** | Forecast & Waste-Risk REST Endpoints | **PASS** | Created [`backend/app/api/v1/forecasts.py`](file:///D:/Waste%20management/backend/app/api/v1/forecasts.py) and [`backend/app/api/v1/waste_risk.py`](file:///D:/Waste%20management/backend/app/api/v1/waste_risk.py). Mounted in [`backend/app/api/v1/api.py`](file:///D:/Waste%20management/backend/app/api/v1/api.py). Fully typed Pydantic schemas in [`backend/app/schemas/forecast.py`](file:///D:/Waste%20management/backend/app/schemas/forecast.py). Documented in [`docs/FORECAST_API_CONTRACT.md`](file:///D:/Waste%20management/docs/FORECAST_API_CONTRACT.md). |
| **M2-P4-REQ-6** | Strict Multi-Tenant Isolation | **PASS** | Verified via test suite: cross-tenant access to another tenant's SKU or inventory item returns `404 NOT FOUND`. |
| **M2-P4-REQ-7** | Scheduled Batch Prediction Runner | **PASS** | Implemented [`backend/app/ml/batch_job.py`](file:///D:/Waste%20management/backend/app/ml/batch_job.py) and CLI runner [`scripts/run_batch_waste_risk_eval.py`](file:///D:/Waste%20management/scripts/run_batch_waste_risk_eval.py). Documented deployment patterns in [`docs/BATCH_PREDICTION_OPERATIONS.md`](file:///D:/Waste%20management/docs/BATCH_PREDICTION_OPERATIONS.md). |
| **M2-P4-REQ-8** | Automated Testing & Full Regression | **PASS** | Authored 12 automated unit/integration tests in [`backend/tests/test_waste_risk_and_forecast_api.py`](file:///D:/Waste%20management/backend/tests/test_waste_risk_and_forecast_api.py). 100% passing (12/12 Phase 4 tests, 43/43 ML tests, **121/121 total project tests**). |

---

## 3. Phase 3 Verification Matrix

| Requirement | Description | Status | Evidence / Artifacts |
| :--- | :--- | :---: | :--- |
| **M2-P3-REQ-1** | Baseline Forecasting Engine | **PASS** | Implemented Naive ($y_{t-1}$), Seasonal Naive ($y_{t-7}$), 7-Day Moving Average, and Historical Mean in [`backend/app/ml/candidate_models.py`](file:///D:/Waste%20management/backend/app/ml/candidate_models.py). Baseline evaluation report in [`docs/BASELINE_EVALUATION_REPORT.md`](file:///D:/Waste%20management/docs/BASELINE_EVALUATION_REPORT.md). |
| **M2-P3-REQ-2** | Candidate ML Models Development | **PASS** | Implemented Ridge Regression, GBDT (`HistGradientBoostingRegressor`), and Random Forest with non-negative constraints ($\hat{y} \ge 0.0$) and serialization interfaces. Documented rationale in [`docs/FORECASTING_MODEL_COMPARISON.md`](file:///D:/Waste%20management/docs/FORECASTING_MODEL_COMPARISON.md). |
| **M2-P3-REQ-3** | Sparsity-Aware Evaluation Engine | **PASS** | Implemented [`backend/app/ml/evaluator.py`](file:///D:/Waste%20management/backend/app/ml/evaluator.py). Calculates MAE, RMSE, WAPE (%), MASE, MBE with division-by-zero protection. Evaluates overall, per-SKU, and per-demand-pattern. |
| **M2-P3-REQ-4** | Validation-Based Model Selection Gate | **PASS** | Built [`backend/app/ml/model_trainer.py`](file:///D:/Waste%20management/backend/app/ml/model_trainer.py). Selected Random Forest for 1-day ahead demand (Val WAPE 12.94%, MASE 0.696) and Ridge for 7-day cumulative demand (Val WAPE 5.53%, MASE 0.712). |
| **M2-P3-REQ-5** | Held-Out Test Set Generalization | **PASS** | Evaluated champion models on untouched Test set (2026-08-30 to 2026-10-23): Random Forest achieved **15.05% Test WAPE** and **MASE 0.698** (40% relative error reduction vs Seasonal Naive 25.09% WAPE). Ridge achieved **7.03% Test WAPE**. |
| **M2-P3-REQ-6** | Model Serialization & Persistence | **PASS** | Saved `data/models/champion_1d_forecaster.joblib` and `data/models/champion_7d_forecaster.joblib`. Verified save/load roundtrip bit-for-bit prediction identity. |
| **M2-P3-REQ-7** | Downstream Waste-Risk Contract | **PASS** | Defined Pydantic schemas in [`backend/app/ml/forecast_contract.py`](file:///D:/Waste%20management/backend/app/ml/forecast_contract.py) and documented contract in [`docs/FORECAST_OUTPUT_CONTRACT.md`](file:///D:/Waste%20management/docs/FORECAST_OUTPUT_CONTRACT.md). |
| **M2-P3-REQ-8** | Automated Testing & Regression Verification | **PASS** | Authored 11 unit/integration tests in [`backend/tests/test_ml_forecasting_models.py`](file:///D:/Waste%20management/backend/tests/test_ml_forecasting_models.py). All 31 ML tests passing (100%), full project test suite passing (98/98 tests, 100%). |

---

## 4. Phase 2 Verification Matrix

| Requirement | Description | Status | Evidence / Artifacts |
| :--- | :--- | :---: | :--- |
| **M2-P2-REQ-1** | Immutable Benchmark Data Ingestion | **PASS** | Stored immutable source datasets in `data/raw/` with verified SHA-256 hashes in [`docs/DATASET_VERSIONING.md`](file:///D:/Waste%20management/docs/DATASET_VERSIONING.md). |
| **M2-P2-REQ-2** | Automated Data Cleaning Engine | **PASS** | Implemented [`backend/app/ml/data_cleaner.py`](file:///D:/Waste%20management/backend/app/ml/data_cleaner.py). Resolved duplicates, imputed timestamps, normalized units (`lbs` $\to$ `kg`), reconciled ledger math, enforced negative outflow signs. Machine audit in `data/processed/cleaning_summary.json`. |
| **M2-P2-REQ-3** | Gap-Free Time Series Resampling | **PASS** | Implemented [`backend/app/ml/time_series_prep.py`](file:///D:/Waste%20management/backend/app/ml/time_series_prep.py). Reindexed all 19 SKUs to continuous 365-day calendar grid, imputed zero sales on unobserved days, forward-filled stock balance, tagged stockouts, classified demand patterns (17 Smooth, 2 Intermittent). |
| **M2-P2-REQ-4** | Multi-Horizon Target Builder | **PASS** | Implemented [`backend/app/ml/target_builder.py`](file:///D:/Waste%20management/backend/app/ml/target_builder.py). Built 1-day ahead, 7-day ahead, and 7-day cumulative sales/waste targets with verified lookahead shift semantics and tail NaN preservation. |
| **M2-P2-REQ-5** | Leakage-Free Feature Engineering | **PASS** | Implemented [`backend/app/ml/feature_engine.py`](file:///D:/Waste%20management/backend/app/ml/feature_engine.py). Engineered 27 predictive features across lags, shift(1) rolling statistics, inventory/economic context, and calendar seasonality. Automated zero-leakage perturbation test PASS. |
| **M2-P2-REQ-6** | Chronological Partitioning & Scaler Isolation | **PASS** | Implemented [`backend/app/ml/dataset_splitter.py`](file:///D:/Waste%20management/backend/app/ml/dataset_splitter.py). Partitioned chronologically into Train (4,313 rows, 70%), Val (1,045 rows, 15%), Test (1,045 rows, 15%). Excluded 28-day warm-up from training loss. Fitted StandardScaler strictly on Train partition. |
| **M2-P2-REQ-7** | End-to-End Orchestrator & Metadata Export | **PASS** | Executed [`scripts/run_ml_preprocessing_pipeline.py`](file:///D:/Waste%20management/scripts/run_ml_preprocessing_pipeline.py). Exported processed datasets and complete cryptographic metadata in `data/processed/dataset_version_metadata.json`. |
| **M2-P2-REQ-8** | Automated Testing & Zero Regression | **PASS** | Authored 12 automated unit/integration tests in `backend/tests/test_ml_preprocessing_pipeline.py`. 100% passing (20/20 ML tests, 98/98 total tests). |

---

## 5. Phase 1 Verification Matrix

| Requirement | Description | Status | Evidence / Artifacts |
| :--- | :--- | :---: | :--- |
| **M2-P1-REQ-1** | Repository & Schema Audit | **PASS** | Audited `waste_management.db`, verified schemas, confirmed 0 live retail transactions, documented provenance in [`docs/ML_DATASET_INVENTORY.md`](file:///D:/Waste%20management/docs/ML_DATASET_INVENTORY.md). |
| **M2-P1-REQ-2** | Reproducible Benchmark Dataset | **PASS** | Generated 365-day 19-SKU supermarket history in `data/synthetic_daily_supermarket_history.csv` (6,935 rows) and `data/synthetic_transactions_supermarket_history.csv` (8,617 rows). |
| **M2-P1-REQ-3** | Data Profiling Pipeline | **PASS** | Built `data_profiler.py`, detected missing timestamps, duplicates, sign errors, invalid units, and classified demand patterns in [`docs/DATA_QUALITY_REPORT.md`](file:///D:/Waste%20management/docs/DATA_QUALITY_REPORT.md). |
| **M2-P1-REQ-4** | Forecasting Target & Problem Definition | **PASS** | Defined daily SKU/Category grains, 1–7 day and 14–28 day horizons, and censored demand mitigation in [`docs/FORECASTING_PROBLEM_DEFINITION.md`](file:///D:/Waste%20management/docs/FORECASTING_PROBLEM_DEFINITION.md). |
| **M2-P1-REQ-5** | Zero-Leakage Preprocessing Design | **PASS** | Built `preprocessing.py` with strict `shift(1)` on all lags/rolling stats and parameter isolation in [`docs/ML_PREPROCESSING_DESIGN.md`](file:///D:/Waste%20management/docs/ML_PREPROCESSING_DESIGN.md). Verified via programmatic leakage test. |
| **M2-P1-REQ-6** | Baseline Specs & Robust Metrics | **PASS** | Implemented Naive, Seasonal Naive, Moving Average, and metrics (MAE, RMSE, WAPE, MASE) in `baselines.py` and [`docs/ML_EVALUATION_PLAN.md`](file:///D:/Waste%20management/docs/ML_EVALUATION_PLAN.md). |
| **M2-P1-REQ-7** | Waste Risk & Reorder Formulation | **PASS** | Implemented explainable expected surplus, surplus ratio, value-at-risk, and statistical reorder point formulas in `waste_risk.py`. |
| **M2-P1-REQ-8** | Automated Testing | **PASS** | Authored 8 automated tests in `backend/tests/test_ml_pipeline_design.py`. Full test suite: **86 / 86 tests passing (100%)**. |
