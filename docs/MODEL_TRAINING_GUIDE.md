# Machine Learning Model Training & Operations Guide

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 2 — Machine Learning Demand Forecasting & Food Waste Prediction  
**Phase**: Phase 3 — Forecasting Model Development, Training & Evaluation  
**Date**: October 24, 2026  
**Auditor**: Senior Machine Learning Engineer, MLOps Engineer  

---

## 1. Prerequisites & Environment Setup

All modeling and evaluation components are fully integrated into the project's Python virtual environment.

```bash
# 1. Activate virtual environment (PowerShell)
.\.venv\Scripts\Activate.ps1

# 2. Verify installed scientific packages
python -c "import sklearn, pandas, numpy, joblib; print('Dependencies OK')"
```

### Required Input Datasets (Verified in Milestone 2 Phase 2)
The training pipeline requires the standardized, chronologically partitioned feature tables:
- `data/processed/train_features.csv` (4,313 rows, clean training partition, 2025-10-24 to 2026-07-05)
- `data/processed/val_features.csv` (1,045 rows, validation partition, 2026-07-06 to 2026-08-29)
- `data/processed/test_features.csv` (1,045 rows, held-out test partition, 2026-08-30 to 2026-10-23)
- `data/processed/dataset_version_metadata.json` (Cryptographic checksums and scaling parameters)

---

## 2. Model Retraining Commands

To retrain all baselines and candidate models, execute validation-based selection, and evaluate generalization on the test set:

```bash
# Execute full training and comparative evaluation
python scripts/train_and_evaluate_models.py
```

### Automated Output Artifacts
The training pipeline automatically outputs:
- `data/models/champion_1d_forecaster.joblib`: Serialized Random Forest model for 1-day ahead forecasting.
- `data/models/champion_7d_forecaster.joblib`: Serialized Ridge regression model for 7-day cumulative demand.
- `data/models/complete_forecasting_benchmarks.json`: Detailed machine-readable performance metrics across all models, horizons, SKUs, and demand patterns.

---

## 3. Model Hyperparameters & Configurations

### 3.1 Random Forest Forecaster (1-Day Ahead Champion)
```python
RandomForestRegressor(
    n_estimators=100,        # 100 decision trees
    max_depth=8,             # Constrains tree depth to prevent memorizing daily noise
    min_samples_leaf=5,      # Requires at least 5 observations per terminal leaf
    random_state=42,         # Fixed seed for bit-for-bit reproducibility
    n_jobs=-1,               # Multi-threaded parallelization across CPU cores
)
```

### 3.2 Ridge Regression Forecaster (7-Day Cumulative Champion)
```python
Ridge(
    alpha=10.0,              # L2 regularization strength penalizing extreme feature weights
    random_state=42,         # Fixed seed for deterministic solver convergence
)
```

### 3.3 Gradient Boosted Decision Trees (GBDT)
```python
HistGradientBoostingRegressor(
    max_iter=150,            # Maximum boosting iterations
    learning_rate=0.05,      # Conservative step size
    max_depth=6,             # Tree depth limit
    min_samples_leaf=15,     # Terminal leaf sample count
    random_state=42,         # Fixed seed
    early_stopping=True,     # Halts boosting when validation loss plateaus for 10 rounds
    n_iter_no_change=10,
)
```

---

## 4. How to Load and Serve Model Artifacts

Inference services in Phase 4 can reload the trained champions statelessly:

```python
import joblib
import pandas as pd
from backend.app.ml.candidate_models import RandomForestForecaster, RidgeForecaster

# Load 1-day ahead champion (Random Forest)
forecaster_1d = RandomForestForecaster.load("data/models/champion_1d_forecaster.joblib")

# Load 7-day cumulative champion (Ridge)
forecaster_7d = RidgeForecaster.load("data/models/champion_7d_forecaster.joblib")

# Generate predictions on new feature DataFrame
next_day_predictions = forecaster_1d.predict(new_features_df)
weekly_demand_predictions = forecaster_7d.predict(new_features_df)
```

---

## 5. Automated Unit & Integration Testing

To independently verify model training, prediction boundaries, metric math, and schema contracts:

```bash
# Run Phase 3 forecasting test suite (11 tests)
pytest -v backend/tests/test_ml_forecasting_models.py

# Run complete project regression suite (98 tests)
pytest -q --no-cov
```
