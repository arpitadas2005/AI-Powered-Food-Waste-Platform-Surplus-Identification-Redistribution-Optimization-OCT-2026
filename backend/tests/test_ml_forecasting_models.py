"""
Milestone 2 — Phase 3: Comprehensive Automated Test Suite for ML Forecasting Models.

Tests:
1. BaselineForecaster: Naive, Seasonal Naive, Moving Average, Historical Mean.
2. Candidate ML Models: Ridge, GBDT (HistGradientBoosting), Random Forest.
3. Metric Evaluator: Sparsity robustness, zero actuals, exact mathematical formulas.
4. Model Output Guarantees: Non-negativity, finite values (no NaNs, no Infs), correct output shapes.
5. Chronological Parameter Isolation: Train-only model fitting.
6. Model Serialization: Save/load joblib roundtrip with bit-for-bit identical predictions.
7. Forecast Output & Waste-Risk Contract: Pydantic schema validation.
"""

import os
import tempfile
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.candidate_models import (
    BaselineForecaster,
    GBDTForecaster,
    RandomForestForecaster,
    RidgeForecaster,
    FEATURE_COLS_SCALED,
    FEATURE_COLS_UNSCALED,
)
from backend.app.ml.evaluator import (
    ForecastEvaluator,
    compute_mae,
    compute_rmse,
    compute_wape,
    compute_mase,
    compute_mbe,
)
from backend.app.ml.forecast_contract import (
    DailyForecastPoint,
    SKUForecastResult,
    WasteRiskInputContract,
    WasteRiskOutputContract,
)
from backend.app.ml.model_trainer import ModelTrainingPipeline


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def synthetic_train_val_dfs():
    """Generates synthetic train and validation datasets with continuous features."""
    np.random.seed(42)
    n_train = 100
    n_val = 30

    def make_df(n, start_date="2026-01-01"):
        dates = pd.date_range(start_date, periods=n, freq="D")
        records = []
        for d in dates:
            for sku in ["SKU-01", "SKU-02"]:
                base = 15.0 if sku == "SKU-01" else 5.0
                dow = d.day_of_week
                seasonal = 5.0 if dow in [5, 6] else 0.0
                sales = max(0.0, base + seasonal + np.random.normal(0, 1.0))
                
                row = {
                    "date": d,
                    "sku": sku,
                    "tenant_id": "tenant-test",
                    "product_name": f"Product {sku}",
                    "demand_pattern": "SMOOTH" if sku == "SKU-01" else "INTERMITTENT",
                    "recorded_sales": sales,
                    "target_sales_1d": sales + np.random.normal(0, 0.5),
                    "target_demand_7d_sum": sales * 7.0 + np.random.normal(0, 2.0),
                    "lag_1": sales - 0.2,
                    "lag_2": sales - 0.1,
                    "lag_7": sales + seasonal,
                    "lag_14": sales + seasonal,
                    "lag_28": sales + seasonal,
                    "rolling_mean_7": sales,
                    "rolling_std_7": 1.2,
                    "rolling_mean_14": sales,
                    "rolling_mean_28": sales,
                    "rolling_max_7": sales + 2.0,
                    "rolling_min_7": max(0.0, sales - 2.0),
                    "rolling_waste_7": 0.5,
                    "prior_day_stock": 40.0,
                    "prior_day_stockout": 0.0,
                    "shelf_life_days": 14.0,
                    "unit_cost": 2.0,
                    "selling_price": 3.5,
                    "gross_margin": 1.5,
                    "gross_margin_ratio": 0.428,
                    "day_of_week": dow,
                    "is_weekend": 1 if dow in [5, 6] else 0,
                    "day_of_month": d.day,
                    "month": d.month,
                    "is_month_start": 1 if d.day == 1 else 0,
                    "is_month_end": 0,
                    "sin_dow": np.sin(2 * np.pi * dow / 7.0),
                    "cos_dow": np.cos(2 * np.pi * dow / 7.0),
                    "category_code": 0 if sku == "SKU-01" else 1,
                }
                # Add scaled versions
                for col in ["lag_1", "lag_2", "lag_7", "lag_14", "lag_28", "rolling_mean_7", "rolling_std_7",
                            "rolling_mean_14", "rolling_mean_28", "rolling_max_7", "rolling_min_7", "rolling_waste_7",
                            "prior_day_stock", "prior_day_stockout", "shelf_life_days", "unit_cost", "selling_price",
                            "gross_margin", "gross_margin_ratio", "day_of_week", "is_weekend", "day_of_month",
                            "month", "is_month_start", "is_month_end", "sin_dow", "cos_dow"]:
                    row[f"{col}_scaled"] = (row[col] - base) / 2.0
                records.append(row)
        return pd.DataFrame(records)

    df_tr = make_df(n_train, "2026-01-01")
    df_va = make_df(n_val, "2026-04-12")
    return df_tr, df_va


# -----------------------------------------------------------------------------
# 1. Baseline Forecaster Tests
# -----------------------------------------------------------------------------

def test_baseline_forecaster_naive_prediction(synthetic_train_val_dfs):
    df_train, df_val = synthetic_train_val_dfs
    forecaster = BaselineForecaster(strategy="naive")
    forecaster.fit(df_train)
    preds = forecaster.predict(df_val)

    assert len(preds) == len(df_val)
    # Naive uses lag_1
    assert np.allclose(preds, np.clip(df_val["lag_1"].to_numpy(), 0.0, None))


def test_baseline_forecaster_seasonal_naive_prediction(synthetic_train_val_dfs):
    df_train, df_val = synthetic_train_val_dfs
    forecaster = BaselineForecaster(strategy="seasonal_naive")
    forecaster.fit(df_train)
    preds = forecaster.predict(df_val)

    assert len(preds) == len(df_val)
    # Seasonal Naive uses lag_7
    assert np.allclose(preds, np.clip(df_val["lag_7"].to_numpy(), 0.0, None))


def test_baseline_forecaster_moving_average_prediction(synthetic_train_val_dfs):
    df_train, df_val = synthetic_train_val_dfs
    forecaster = BaselineForecaster(strategy="moving_average")
    forecaster.fit(df_train)
    preds = forecaster.predict(df_val)

    assert len(preds) == len(df_val)
    assert np.allclose(preds, np.clip(df_val["rolling_mean_7"].to_numpy(), 0.0, None))


def test_baseline_forecaster_historical_mean(synthetic_train_val_dfs):
    df_train, df_val = synthetic_train_val_dfs
    forecaster = BaselineForecaster(strategy="historical_mean")
    forecaster.fit(df_train, target_col="target_sales_1d")
    preds = forecaster.predict(df_val)

    assert len(preds) == len(df_val)
    for sku in ["SKU-01", "SKU-02"]:
        sku_mask = df_val["sku"] == sku
        expected_mean = df_train[df_train["sku"] == sku]["target_sales_1d"].mean()
        assert np.allclose(preds[sku_mask], expected_mean)


# -----------------------------------------------------------------------------
# 2. Candidate ML Models Tests (Ridge, GBDT, Random Forest)
# -----------------------------------------------------------------------------

def test_candidate_models_training_and_non_negative_finite_output(synthetic_train_val_dfs):
    df_train, df_val = synthetic_train_val_dfs

    models = [
        RidgeForecaster(alpha=1.0, random_state=42),
        GBDTForecaster(max_iter=30, max_depth=3, random_state=42),
        RandomForestForecaster(n_estimators=20, max_depth=4, random_state=42),
    ]

    for model in models:
        model.fit(df_train, target_col="target_sales_1d")
        preds = model.predict(df_val)

        # Output shape matches test samples
        assert len(preds) == len(df_val)
        # Guarantees non-negative physical demand
        assert (preds >= 0.0).all()
        # Guarantees finite numbers (no NaN, no Inf)
        assert np.isfinite(preds).all()


def test_model_serialization_and_deserialization_roundtrip(synthetic_train_val_dfs):
    df_train, df_val = synthetic_train_val_dfs

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Ridge Serialization
        ridge = RidgeForecaster(alpha=5.0)
        ridge.fit(df_train, target_col="target_sales_1d")
        orig_preds_ridge = ridge.predict(df_val)

        ridge_path = os.path.join(tmp_dir, "test_ridge.joblib")
        ridge.save(ridge_path)
        loaded_ridge = RidgeForecaster.load(ridge_path)
        loaded_preds_ridge = loaded_ridge.predict(df_val)
        assert np.array_equal(orig_preds_ridge, loaded_preds_ridge)

        # 2. GBDT Serialization
        gbdt = GBDTForecaster(max_iter=20)
        gbdt.fit(df_train, target_col="target_sales_1d")
        orig_preds_gbdt = gbdt.predict(df_val)

        gbdt_path = os.path.join(tmp_dir, "test_gbdt.joblib")
        gbdt.save(gbdt_path)
        loaded_gbdt = GBDTForecaster.load(gbdt_path)
        loaded_preds_gbdt = loaded_gbdt.predict(df_val)
        assert np.array_equal(orig_preds_gbdt, loaded_preds_gbdt)


# -----------------------------------------------------------------------------
# 3. Forecast Evaluator & Metric Tests
# -----------------------------------------------------------------------------

def test_evaluator_exact_metrics():
    y_true = np.array([10.0, 20.0, 30.0, 40.0])
    y_pred = np.array([12.0, 18.0, 33.0, 35.0])
    # Absolute errors: [2, 2, 3, 5] -> sum = 12
    # MAE = 12 / 4 = 3.0
    assert np.isclose(compute_mae(y_true, y_pred), 3.0)

    # Squared errors: [4, 4, 9, 25] -> sum = 42 -> mean = 10.5 -> sqrt(10.5) ~ 3.24037
    assert np.isclose(compute_rmse(y_true, y_pred), np.sqrt(10.5))

    # WAPE = sum(|err|) / sum(actual) * 100 = (12 / 100) * 100 = 12.0%
    assert np.isclose(compute_wape(y_true, y_pred), 12.0)

    # MBE = mean(pred - true) = (2 - 2 + 3 - 5) / 4 = -2 / 4 = -0.5
    assert np.isclose(compute_mbe(y_true, y_pred), -0.5)


def test_evaluator_handles_zero_actuals_and_sparse_demand():
    """Asserts that division-by-zero does not raise ZeroDivisionError or return NaN/Inf."""
    # All zeros actual and predicted
    y_zero = np.array([0.0, 0.0, 0.0])
    y_pred_zero = np.array([0.0, 0.0, 0.0])
    assert compute_wape(y_zero, y_pred_zero) == 0.0

    # Zero actuals with non-zero predictions
    y_pred_nonzero = np.array([1.0, 2.0, 3.0])
    wape = compute_wape(y_zero, y_pred_nonzero)
    assert np.isfinite(wape)
    assert wape == 100.0

    # MASE with zero in-sample variation
    y_train_flat = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
    mase = compute_mase(y_train_flat, np.array([5.0]), np.array([5.0]))
    assert np.isfinite(mase)
    assert mase == 0.0


def test_evaluator_dataframe_breakdown(synthetic_train_val_dfs):
    df_train, df_val = synthetic_train_val_dfs
    evaluator = ForecastEvaluator(seasonality=7)
    df_val_eval = df_val.copy()
    df_val_eval["pred"] = df_val_eval["target_sales_1d"] * 0.95

    res = evaluator.evaluate_dataframe(
        df_eval=df_val_eval,
        df_train=df_train,
        actual_col="target_sales_1d",
        pred_col="pred",
    )

    assert "overall" in res
    assert "by_sku" in res
    assert "by_pattern" in res
    assert "SKU-01" in res["by_sku"]
    assert "SKU-02" in res["by_sku"]
    assert "SMOOTH" in res["by_pattern"]
    assert "INTERMITTENT" in res["by_pattern"]
    assert res["overall"]["wape_pct"] > 0.0


# -----------------------------------------------------------------------------
# 4. Forecast Output Contract & Downstream Schema Tests
# -----------------------------------------------------------------------------

def test_forecast_contract_pydantic_validation():
    point = DailyForecastPoint(
        date="2026-10-25",
        predicted_sales=14.5,
        lower_bound_80=11.2,
        upper_bound_80=17.8,
    )
    assert point.predicted_sales == 14.5

    result = SKUForecastResult(
        sku="SKU-APPLES-01",
        tenant_id="tenant-test",
        product_name="Honeycrisp Apples",
        unit="kg",
        horizon_days=7,
        daily_forecasts=[point],
        predicted_7d_demand=101.5,
        model_name="RandomForestForecaster",
        model_version="2.0.0-phase3",
    )
    assert result.horizon_days == 7
    assert result.predicted_7d_demand == 101.5

    risk_input = WasteRiskInputContract(
        sku="SKU-APPLES-01",
        tenant_id="tenant-test",
        current_stock=120.0,
        shelf_life_days=14.0,
        days_to_expiry=5.0,
        unit_cost=1.80,
        selling_price=3.20,
        predicted_demand_to_expiry=65.0,
        predicted_7d_demand=101.5,
    )
    assert risk_input.current_stock == 120.0
    assert risk_input.predicted_demand_to_expiry == 65.0

    risk_output = WasteRiskOutputContract(
        sku="SKU-APPLES-01",
        tenant_id="tenant-test",
        risk_level="HIGH",
        expected_surplus_quantity=55.0,
        surplus_ratio=55.0 / 120.0,
        value_at_risk=55.0 * 1.80,
        reorder_point=45.0,
        recommended_action="DISCOUNT_MARKDOWN",
    )
    assert risk_output.risk_level == "HIGH"
    assert risk_output.expected_surplus_quantity == 55.0


# -----------------------------------------------------------------------------
# 5. Pipeline & Chronological Isolation Tests
# -----------------------------------------------------------------------------

def test_training_pipeline_chronological_isolation(synthetic_train_val_dfs):
    df_train, df_val = synthetic_train_val_dfs

    with tempfile.TemporaryDirectory() as tmp_dir:
        tr_path = os.path.join(tmp_dir, "train.csv")
        va_path = os.path.join(tmp_dir, "val.csv")
        te_path = os.path.join(tmp_dir, "test.csv")

        df_train.to_csv(tr_path, index=False)
        df_val.to_csv(va_path, index=False)
        # Create a test set whose target has extreme values
        df_test = df_val.copy()
        df_test["target_sales_1d"] = 9999.0
        df_test.to_csv(te_path, index=False)

        pipeline = ModelTrainingPipeline(
            train_path=tr_path,
            val_path=va_path,
            test_path=te_path,
            models_dir=os.path.join(tmp_dir, "models"),
            random_state=42,
        )
        res = pipeline.run_training_and_evaluation(target_col="target_sales_1d")

        # Verify model selection was based strictly on Validation set
        selected = res["selected_model"]
        assert selected is not None
        assert selected in res["validation_results"]
        # Champion model predictions on training data must be unaffected by test set values
        model = pipeline.trained_models[selected]
        train_preds = model.predict(df_train)
        assert (train_preds < 5000.0).all()  # Verifies model did not fit to test spike of 9999.0

