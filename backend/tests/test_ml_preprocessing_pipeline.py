"""
Milestone 2 — Phase 2: Automated Test Suite for ML Data Preprocessing & Feature Engineering.

Validates:
- DataCleaner: unit conversion, deduplication, sign enforcement, ledger reconciliation.
- TimeSeriesPreparer: unbroken calendar grids, zero sales imputation, minimum history thresholding, Syntetos-Boylan demand classification.
- TargetBuilder: multi-horizon target shift semantics, tail NaN preservation, ground truth alignment.
- FeatureEngine: 18+ predictive features, strict shift(1) rolling windows, zero future lookahead contamination.
- ChronologicalDatasetSplitter: strict temporal partitions, zero date overlap, train-only scaler fitting.
- Pipeline end-to-end reproducibility.
"""

from datetime import datetime, timedelta
import hashlib
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.data_cleaner import DataCleaner, CANONICAL_UNITS
from backend.app.ml.time_series_prep import TimeSeriesPreparer
from backend.app.ml.target_builder import TargetBuilder, TARGET_COLUMNS
from backend.app.ml.feature_engine import FeatureEngine, FEATURE_NAMES
from backend.app.ml.dataset_splitter import ChronologicalDatasetSplitter


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def sample_raw_tx_df():
    """Provides a synthetic transactional dataset with deliberate irregularities."""
    return pd.DataFrame([
        {
            "transaction_id": "TX-001",
            "timestamp": "2026-01-01 10:00:00",
            "tenant_id": "tenant-test",
            "sku": "SKU-APPLE",
            "product_name": "Organic Gala Apples",
            "category_id": "cat-produce",
            "transaction_type": "PURCHASE",
            "quantity_change": -50.0,  # Irregular negative sign for purchase
            "quantity_before": 0.0,
            "quantity_after": 50.0,
            "unit": "lbs",  # Non-canonical unit
            "unit_cost": -1.50,  # Irregular negative price
            "selling_price": 2.50,
        },
        {
            "transaction_id": "TX-001",  # Duplicate ID
            "timestamp": "2026-01-01 10:00:00",
            "tenant_id": "tenant-test",
            "sku": "SKU-APPLE",
            "product_name": "Organic Gala Apples",
            "category_id": "cat-produce",
            "transaction_type": "PURCHASE",
            "quantity_change": 50.0,
            "quantity_before": 0.0,
            "quantity_after": 50.0,
            "unit": "lbs",
            "unit_cost": 1.50,
            "selling_price": 2.50,
        },
        {
            "transaction_id": "TX-002",
            "timestamp": None,  # Missing timestamp
            "tenant_id": "tenant-test",
            "sku": "SKU-APPLE",
            "product_name": "Organic Gala Apples",
            "category_id": "cat-produce",
            "transaction_type": "POS_SALE",
            "quantity_change": 5.0,  # Positive sign for sale
            "quantity_before": 22.68,
            "quantity_after": 99.99,  # Corrupted ledger math
            "unit": "kg",
            "unit_cost": 1.50,
            "selling_price": 2.50,
        },
        {
            "transaction_id": "TX-003",
            "timestamp": "2026-01-02 11:00:00",
            "tenant_id": "tenant-test",
            "sku": None,  # Missing SKU
            "product_name": "Unknown",
            "category_id": "cat-produce",
            "transaction_type": "POS_SALE",
            "quantity_change": -2.0,
            "quantity_before": 10.0,
            "quantity_after": 8.0,
            "unit": "kg",
            "unit_cost": 1.0,
            "selling_price": 2.0,
        },
    ])


@pytest.fixture
def continuous_35day_grid():
    """Generates a continuous 35-day daily series for two SKUs."""
    dates = pd.date_range("2026-01-01", periods=35, freq="D")
    records = []
    for d_idx, d in enumerate(dates):
        # SKU-01: Steady daily sales of 10 units
        records.append({
            "date": d,
            "tenant_id": "tenant-test",
            "sku": "SKU-01",
            "product_name": "Test Product 1",
            "category_id": "cat-dairy",
            "category_name": "Dairy",
            "unit": "liters",
            "opening_stock": 50.0,
            "restock_quantity": 0.0,
            "recorded_sales": 10.0,
            "waste_quantity": 1.0,
            "closing_stock": 40.0,
            "is_stockout": False,
            "unit_cost": 2.0,
            "selling_price": 3.5,
            "shelf_life_days": 14,
        })
        # SKU-02: Intermittent sales (sales only every 3 days)
        sales_val = 15.0 if d_idx % 3 == 0 else 0.0
        records.append({
            "date": d,
            "tenant_id": "tenant-test",
            "sku": "SKU-02",
            "product_name": "Test Product 2",
            "category_id": "cat-bakery",
            "category_name": "Bakery",
            "unit": "packs",
            "opening_stock": 30.0,
            "restock_quantity": 0.0,
            "recorded_sales": sales_val,
            "waste_quantity": 0.5,
            "closing_stock": 30.0 - sales_val,
            "is_stockout": False,
            "unit_cost": 1.5,
            "selling_price": 2.5,
            "shelf_life_days": 7,
        })
    return pd.DataFrame(records)


# -----------------------------------------------------------------------------
# 1. DataCleaner Tests
# -----------------------------------------------------------------------------

def test_data_cleaner_unit_conversion_and_deduplication(sample_raw_tx_df):
    cleaner = DataCleaner()
    cleaned_df, audit = cleaner.clean_transactions(sample_raw_tx_df)

    # Missing SKU TX-003 dropped
    assert len(cleaned_df) == 2
    assert "TX-003" not in cleaned_df["transaction_id"].values
    assert audit["missing_skus_dropped"] == 1

    # Duplicate TX-001 dropped
    assert (cleaned_df["transaction_id"] == "TX-001").sum() == 1
    assert audit["duplicates_removed"] == 1

    # Unit converted from lbs to kg (factor ~0.453592)
    row_tx1 = cleaned_df[cleaned_df["transaction_id"] == "TX-001"].iloc[0]
    assert row_tx1["unit"] == "kg"
    assert np.isclose(row_tx1["quantity_change"], 50.0 * 0.45359237)
    assert row_tx1["unit_cost"] > 0  # Negative price inverted to positive


def test_data_cleaner_sign_and_ledger_reconciliation(sample_raw_tx_df):
    cleaner = DataCleaner()
    cleaned_df, audit = cleaner.clean_transactions(sample_raw_tx_df)

    # TX-002 was positive sale, must be negative
    row_tx2 = cleaned_df[cleaned_df["transaction_id"] == "TX-002"].iloc[0]
    assert row_tx2["quantity_change"] < 0
    assert row_tx2["quantity_change"] == -5.0

    # Ledger math must reconcile: quantity_after = quantity_before + delta
    assert np.isclose(row_tx2["quantity_after"], row_tx2["quantity_before"] + row_tx2["quantity_change"])
    assert audit["math_reconciled"] == 1


# -----------------------------------------------------------------------------
# 2. TimeSeriesPreparer Tests
# -----------------------------------------------------------------------------

def test_time_series_preparer_gap_filling():
    # Provide a dataset with missing dates (e.g., skip Jan 2 and Jan 3)
    df_gappy = pd.DataFrame([
        {
            "date": "2026-01-01",
            "tenant_id": "tenant-test",
            "sku": "SKU-TEST",
            "product_name": "Apples",
            "category_id": "produce",
            "unit": "kg",
            "recorded_sales": 10.0,
            "closing_stock": 50.0,
            "waste_quantity": 0.0,
        },
        {
            "date": "2026-01-04",
            "tenant_id": "tenant-test",
            "sku": "SKU-TEST",
            "product_name": "Apples",
            "category_id": "produce",
            "unit": "kg",
            "recorded_sales": 8.0,
            "closing_stock": 42.0,
            "waste_quantity": 0.0,
        },
    ])

    preparer = TimeSeriesPreparer()
    grid = preparer.build_daily_grid(df_gappy)

    # Must contain 4 days: Jan 1, Jan 2, Jan 3, Jan 4
    assert len(grid) == 4
    dates = pd.to_datetime(grid["date"]).dt.strftime("%Y-%m-%d").tolist()
    assert dates == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]

    # Jan 2 and Jan 3 must have 0.0 sales and forward-filled closing_stock (50.0)
    jan2 = grid[grid["date"] == "2026-01-02"].iloc[0]
    assert jan2["recorded_sales"] == 0.0
    assert jan2["closing_stock"] == 50.0
    assert jan2["is_stockout"] is False or jan2["is_stockout"] == 0


def test_time_series_preparer_minimum_history_flag():
    # 10 days of data for SKU-SHORT
    short_dates = pd.date_range("2026-01-01", periods=10, freq="D")
    df_short = pd.DataFrame([{
        "date": d,
        "tenant_id": "tenant-test",
        "sku": "SKU-SHORT",
        "product_name": "Short History Item",
        "category_id": "dairy",
        "unit": "units",
        "recorded_sales": 2.0,
        "closing_stock": 20.0,
        "waste_quantity": 0.0,
    } for d in short_dates])

    preparer = TimeSeriesPreparer(min_history_days=28)
    grid = preparer.build_daily_grid(df_short)
    grid_validated, history_status = preparer.validate_minimum_history(grid)

    assert history_status["SKU-SHORT"] == "INSUFFICIENT_HISTORY_10_DAYS"
    assert "INSUFFICIENT_HISTORY" in grid_validated["history_status"].iloc[0]


def test_time_series_preparer_syntetos_boylan_classification(continuous_35day_grid):
    preparer = TimeSeriesPreparer()
    grid = preparer.classify_demand_patterns(continuous_35day_grid)

    sku1_pattern = grid[grid["sku"] == "SKU-01"]["demand_pattern"].iloc[0]
    sku2_pattern = grid[grid["sku"] == "SKU-02"]["demand_pattern"].iloc[0]

    # SKU-01 has non-zero demand every day (ADI = 1.0 < 1.32, CV^2 = 0 < 0.49) -> SMOOTH
    assert sku1_pattern == "SMOOTH"

    # SKU-02 has demand every 3 days (ADI = 35 / 12 = 2.91 >= 1.32) -> INTERMITTENT or LUMPY
    assert sku2_pattern in ["INTERMITTENT", "LUMPY"]


# -----------------------------------------------------------------------------
# 3. TargetBuilder Tests
# -----------------------------------------------------------------------------

def test_target_builder_lookahead_alignment_and_tail_nan(continuous_35day_grid):
    builder = TargetBuilder()
    df_targeted = builder.add_targets(continuous_35day_grid)

    is_valid, errors = builder.validate_target_alignment(df_targeted)
    assert is_valid, f"Target alignment failed: {errors}"

    for sku, group in df_targeted.groupby("sku"):
        g = group.sort_values("date").reset_index(drop=True)
        n = len(g)

        # Last row must have NaN for 1d target
        assert pd.isna(g.loc[n - 1, "target_sales_1d"])
        # Row n-2 target_sales_1d must equal row n-1 recorded_sales
        assert g.loc[n - 2, "target_sales_1d"] == g.loc[n - 1, "recorded_sales"]

        # Last 7 rows must have NaN for 7d target
        for i in range(n - 7, n):
            assert pd.isna(g.loc[i, "target_sales_7d"])

        # Row 0 target_demand_7d_sum must equal sum of sales from index 1 to 7
        expected_7d_sum = g.loc[1:7, "recorded_sales"].sum()
        assert np.isclose(g.loc[0, "target_demand_7d_sum"], expected_7d_sum)


# -----------------------------------------------------------------------------
# 4. FeatureEngine Tests
# -----------------------------------------------------------------------------

def test_feature_engine_generates_all_features(continuous_35day_grid):
    builder = TargetBuilder()
    df_targeted = builder.add_targets(continuous_35day_grid)

    engine = FeatureEngine(warm_up_days=28)
    df_featured = engine.engineer_features(df_targeted)

    for feat in FEATURE_NAMES:
        assert feat in df_featured.columns, f"Missing expected feature {feat}"

    # Verify warmup tagging: first 28 observations per SKU are warmup
    sku1_df = df_featured[df_featured["sku"] == "SKU-01"].sort_values("date").reset_index(drop=True)
    assert sku1_df.loc[0:27, "is_warmup"].all()
    assert not sku1_df.loc[28:, "is_warmup"].any()


def test_feature_engine_strict_zero_lookahead_leakage(continuous_35day_grid):
    """
    CRITICAL TEST:
    Modifying future sales at day 30 MUST NOT alter feature representations at day 25.
    """
    dates = sorted(continuous_35day_grid["date"].unique())
    day_25 = str(dates[24].date())
    day_30 = str(dates[29].date())

    is_leakage_free, discrepancies = FeatureEngine.verify_zero_leakage(
        df_clean=continuous_35day_grid,
        perturbed_sku="SKU-01",
        perturbed_date=day_30,
        verification_date=day_25,
    )

    assert is_leakage_free, f"Leakage detected! Discrepancies: {discrepancies}"


# -----------------------------------------------------------------------------
# 5. ChronologicalDatasetSplitter Tests
# -----------------------------------------------------------------------------

def test_chronological_dataset_splitter_boundaries_and_isolation(continuous_35day_grid):
    builder = TargetBuilder()
    df_targeted = builder.add_targets(continuous_35day_grid)

    engine = FeatureEngine(warm_up_days=5)  # Use 5 days warmup for 35-day synthetic test
    df_featured = engine.engineer_features(df_targeted)

    splitter = ChronologicalDatasetSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, exclude_warmup_from_train=True)
    df_train, df_val, df_test = splitter.split(df_featured)

    # Check temporal ordering
    is_valid, errors = splitter.validate_split_integrity(df_train, df_val, df_test)
    assert is_valid, f"Split validation failed: {errors}"

    # Scaling isolation: scaler fit exclusively on Train
    df_tr_s, df_va_s, df_te_s, scaler_params = splitter.fit_transform_scaler(
        df_train=df_train,
        df_val=df_val,
        df_test=df_test,
        feature_cols=["lag_1", "rolling_mean_7", "prior_day_stock"],
    )

    # Scaled columns present
    for col in ["lag_1_scaled", "rolling_mean_7_scaled", "prior_day_stock_scaled"]:
        assert col in df_tr_s.columns
        assert col in df_va_s.columns
        assert col in df_te_s.columns

    # Train mean should be close to 0.0
    assert np.isclose(df_tr_s["lag_1_scaled"].mean(), 0.0, atol=1e-5)


# -----------------------------------------------------------------------------
# 6. Pipeline Reproducibility Test
# -----------------------------------------------------------------------------

def test_pipeline_version_metadata_and_hashes():
    """Verify that processed dataset metadata is valid and hashes match file contents."""
    import json
    import os

    meta_path = "data/processed/dataset_version_metadata.json"
    if not os.path.exists(meta_path):
        pytest.skip("Metadata not yet generated. Run scripts/run_ml_preprocessing_pipeline.py first.")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["version"] == "2.0.0-phase2"
    assert "train_features" in meta["files"]
    assert "val_features" in meta["files"]
    assert "test_features" in meta["files"]

    train_info = meta["files"]["train_features"]
    assert os.path.exists(train_info["path"])

    # Re-verify SHA256 matches actual file on disk
    hasher = hashlib.sha256()
    with open(train_info["path"], "rb") as f:
        hasher.update(f.read())
    assert hasher.hexdigest() == train_info["sha256"]


def test_data_cleaner_negative_price_and_timestamp_imputation():
    raw_df = pd.DataFrame([
        {
            "transaction_id": "TX-T1",
            "timestamp": "2026-02-01 09:00:00",
            "sku": "SKU-BREAD",
            "transaction_type": "PURCHASE",
            "quantity_change": 20.0,
            "unit": "packs",
            "unit_cost": -2.50,
            "selling_price": -3.75,
        },
        {
            "transaction_id": "TX-T2",
            "timestamp": None,  # Missing timestamp
            "sku": "SKU-BREAD",
            "transaction_type": "POS_SALE",
            "quantity_change": 5.0,
            "unit": "packs",
            "unit_cost": 2.50,
            "selling_price": 3.75,
        },
        {
            "transaction_id": "TX-T3",
            "timestamp": "2026-02-01 18:00:00",
            "sku": "SKU-BREAD",
            "transaction_type": "POS_SALE",
            "quantity_change": 3.0,
            "unit": "packs",
            "unit_cost": 2.50,
            "selling_price": 3.75,
        },
    ])

    cleaner = DataCleaner()
    cleaned_df, audit = cleaner.clean_transactions(raw_df)

    # Negative prices must be converted to non-negative
    assert (cleaned_df["unit_cost"] >= 0).all()
    assert (cleaned_df["selling_price"] >= 0).all()
    assert audit["negative_prices_flagged"] == 2

    # Missing timestamp must be forward-filled/imputed
    assert cleaned_df["timestamp"].isna().sum() == 0
    assert audit["missing_timestamps_resolved"] == 1


def test_scaler_parameter_persistence_and_stateless_application(continuous_35day_grid):
    builder = TargetBuilder()
    df_targeted = builder.add_targets(continuous_35day_grid)
    engine = FeatureEngine(warm_up_days=5)
    df_featured = engine.engineer_features(df_targeted)

    splitter = ChronologicalDatasetSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15)
    df_tr, df_va, df_te = splitter.split(df_featured)

    cols = ["lag_1", "rolling_mean_7"]
    df_tr_s, df_va_s, df_te_s, scaler_params = splitter.fit_transform_scaler(
        df_train=df_tr,
        df_val=df_va,
        df_test=df_te,
        feature_cols=cols,
    )

    # Check that scaler parameters were recorded
    assert "means" in scaler_params
    assert "scales" in scaler_params
    assert cols[0] in scaler_params["means"]

    # Verify manual stateless transformation equals df_va_s
    for c in cols:
        m = scaler_params["means"][c]
        s = scaler_params["scales"][c]
        expected_val_scaled = (df_va[c].fillna(0.0) - m) / s
        assert np.allclose(df_va_s[f"{c}_scaled"], expected_val_scaled, atol=1e-5)

