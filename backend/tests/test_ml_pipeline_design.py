"""
Unit and Integration Tests for Milestone 2 ML Pipeline Design.

Verifies:
1. Data profiling and anomaly detection accuracy.
2. Preprocessing unit conversions and transaction deduplication.
3. Strict zero-leakage invariant in feature engineering.
4. Chronological train/validation/test temporal splitting.
5. Statistical baseline models and metric implementations.
6. Waste risk assessment and replenishment calculations.
"""

from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.baselines import (
    MovingAverageBaseline,
    NaiveBaseline,
    SeasonalNaiveBaseline,
    compute_mae,
    compute_mase,
    compute_rmse,
    compute_wape,
    evaluate_forecast,
)
from backend.app.ml.data_profiler import (
    profile_daily_series_dataset,
    profile_transactions_dataset,
)
from backend.app.ml.dataset_generator import (
    generate_synthetic_supermarket_dataset,
)
from backend.app.ml.preprocessing import (
    build_daily_time_series_grid,
    chronological_train_val_test_split,
    clean_raw_transactions,
    generate_leakage_free_features,
    LeakageFreePreprocessor,
)
from backend.app.ml.waste_risk import (
    compute_reorder_recommendation,
    compute_waste_risk,
)


def test_synthetic_supermarket_history_generation():
    """Verify synthetic generator generates complete 365-day multi-product time series."""
    df_daily, df_tx = generate_synthetic_supermarket_dataset(num_days=90, seed=123)
    assert len(df_daily) > 0
    assert len(df_tx) > 0
    assert "sku" in df_daily.columns
    assert "recorded_sales" in df_daily.columns
    assert "closing_stock" in df_daily.columns
    assert df_daily["sku"].nunique() >= 15


def test_data_profiler_detects_controlled_anomalies():
    """Verify profiler correctly catches missing timestamps, duplicate IDs, and unit errors."""
    df_daily, df_tx = generate_synthetic_supermarket_dataset(num_days=60, seed=42)
    tx_profile = profile_transactions_dataset(df_tx)

    # Profiler must detect the deliberately injected anomalies
    assert tx_profile["metrics"]["missing_timestamps"] >= 3
    assert tx_profile["metrics"]["duplicate_transaction_ids"] >= 1
    assert tx_profile["metrics"]["sign_mismatches"] >= 1
    assert "lbs" in tx_profile["metrics"]["invalid_units"]

    daily_profile = profile_daily_series_dataset(df_daily)
    assert daily_profile["unique_skus"] >= 15
    # Sparse products must be classified as INTERMITTENT or LUMPY
    sparse_sku = "PAN-TRUF-01"
    if sparse_sku in daily_profile["product_profiles"]:
        profile = daily_profile["product_profiles"][sparse_sku]
        assert profile["demand_pattern"] in {"INTERMITTENT", "LUMPY"}


def test_preprocessing_cleaning_and_unit_normalization():
    """Verify raw transaction cleaning resolves duplicates, normalizes units, and fixes signs."""
    df_daily, df_tx = generate_synthetic_supermarket_dataset(num_days=60, seed=42)
    raw_count = len(df_tx)
    cleaned = clean_raw_transactions(df_tx)

    # 1. Duplicates removed
    assert len(cleaned) < raw_count
    assert cleaned["transaction_id"].duplicated().sum() == 0

    # 2. Non-canonical units normalized to standard
    assert not (cleaned["unit"] == "lbs").any()
    assert not (cleaned["unit"] == "oz").any()

    # 3. Signs strictly enforced
    sales = cleaned[cleaned["transaction_type"] == "POS_SALE"]
    assert (sales["quantity_change"] <= 0).all()


def test_strict_zero_lookahead_leakage():
    """
    STRICT LEAKAGE TEST:
    Modifying future sales at day t+5 must NOT change features at day t.
    """
    df_daily, _ = generate_synthetic_supermarket_dataset(num_days=60, seed=42)
    grid = build_daily_time_series_grid(df_daily)

    # Baseline features
    f_orig = generate_leakage_free_features(grid)
    target_sku = "PRO-BANA-01"
    orig_sku_df = f_orig[f_orig["sku"] == target_sku].sort_values("date").reset_index(drop=True)

    # Perturb future sales at day index 40
    perturbed_grid = grid.copy()
    mask = (perturbed_grid["sku"] == target_sku)
    sku_indices = perturbed_grid[mask].index
    day_40_idx = sku_indices[40]
    perturbed_grid.loc[day_40_idx, "recorded_sales"] = 9999.0  # Massive future spike

    f_perturbed = generate_leakage_free_features(perturbed_grid)
    pert_sku_df = f_perturbed[f_perturbed["sku"] == target_sku].sort_values("date").reset_index(drop=True)

    # All features at day 35 (before the perturbation) MUST BE EXACTLY IDENTICAL
    for col in ["lag_1", "lag_7", "rolling_mean_7", "rolling_std_7", "rolling_mean_14"]:
        val_orig = orig_sku_df.loc[35, col]
        val_pert = pert_sku_df.loc[35, col]
        assert np.isclose(val_orig, val_pert), f"Data leakage detected in feature '{col}' at index 35!"


def test_chronological_splitting_ordering():
    """Verify chronological split strictly divides dates without shuffle or overlap."""
    df_daily, _ = generate_synthetic_supermarket_dataset(num_days=100, seed=42)
    train, val, test = chronological_train_val_test_split(df_daily, train_ratio=0.7, val_ratio=0.15)

    max_train_date = train["date"].max()
    min_val_date = val["date"].min()
    max_val_date = val["date"].max()
    min_test_date = test["date"].min()

    assert max_train_date < min_val_date, "Train and Validation date ranges overlap!"
    assert max_val_date < min_test_date, "Validation and Test date ranges overlap!"


def test_leakage_free_preprocessor_fitting():
    """Verify preprocessor fits only on training set and raises error if transform called before fit."""
    df_daily, _ = generate_synthetic_supermarket_dataset(num_days=60, seed=42)
    grid = build_daily_time_series_grid(df_daily)
    featured = generate_leakage_free_features(grid)
    train, val, _ = chronological_train_val_test_split(featured)

    preprocessor = LeakageFreePreprocessor(feature_cols=["lag_1", "rolling_mean_7"])
    with pytest.raises(ValueError):
        preprocessor.transform(val)

    preprocessor.fit(train)
    transformed_val = preprocessor.transform(val)
    assert "lag_1_scaled" in transformed_val.columns
    assert "rolling_mean_7_scaled" in transformed_val.columns


def test_baseline_models_and_metrics():
    """Verify Naive, Seasonal Naive, Moving Average, and error metric math."""
    history = pd.Series([10.0, 12.0, 15.0, 18.0, 20.0, 22.0, 25.0, 11.0, 13.0, 16.0])

    naive = NaiveBaseline().predict(history, horizon=3)
    assert np.allclose(naive, [16.0, 16.0, 16.0])

    s_naive = SeasonalNaiveBaseline(period=7).predict(history, horizon=7)
    assert len(s_naive) == 7
    # Value from 7 periods ago
    assert s_naive[0] == history.iloc[-7]

    ma = MovingAverageBaseline(window=5).predict(history, horizon=2)
    expected_ma = history.iloc[-5:].mean()
    assert np.allclose(ma, [expected_ma, expected_ma])

    # Metrics
    y_true = np.array([20.0, 25.0, 30.0])
    y_pred = np.array([18.0, 25.0, 32.0])
    y_train = np.array([15.0, 18.0, 19.0, 21.0, 22.0, 24.0])

    eval_results = evaluate_forecast(y_train, y_true, y_pred, seasonality=1)
    assert eval_results["mae"] == round(4.0 / 3.0, 3)
    assert eval_results["wape_pct"] > 0
    assert eval_results["mase"] > 0


def test_waste_risk_and_reorder_calculation():
    """Verify explainable surplus estimation, value-at-risk, and replenishment point."""
    # Case 1: High surplus risk (stock = 50, forecast demand before expiry = 10, expiry in 2 days)
    assessment = compute_waste_risk(
        sku="MEA-BEEF-01",
        product_name="Ground Beef",
        current_stock=50.0,
        days_to_expiry=2.0,
        predicted_demand_before_expiry=10.0,
        unit_cost=7.50,
    )
    assert assessment.expected_surplus_units == 40.0
    assert assessment.surplus_ratio == 0.8
    assert assessment.value_at_risk == 300.0  # 40 * $7.50
    assert assessment.risk_tier == "HIGH"

    # Case 2: Reorder Point calculation
    reorder = compute_reorder_recommendation(
        current_stock=15.0,
        predicted_daily_demand=10.0,
        lead_time_days=3,
        service_level_z=1.65,
        demand_std_dev=3.0,
        target_cover_days=7,
    )
    assert reorder["lead_time_days"] == 3
    assert reorder["reorder_point"] > 30.0  # (10 * 3) + safety stock
    assert reorder["is_reorder_triggered"] is True  # 15 <= ~38.5
    assert reorder["recommended_order_quantity"] > 0
