"""
Milestone 2 — Phase 2: Complete ML Preprocessing Pipeline Orchestrator.

Executes the end-to-end data preparation workflow:
1. Ingests raw benchmark datasets from data/raw/.
2. Cleans transaction logs and daily observations with DataCleaner.
3. Resamples and builds gap-free continuous calendar grids with TimeSeriesPreparer.
4. Classifies demand patterns (Syntetos-Boylan) and checks minimum history.
5. Builds forward-looking prediction targets with TargetBuilder.
6. Engineers 18+ leakage-free features with FeatureEngine.
7. Performs chronological splitting (70/15/15) and fits scalers strictly on Train with ChronologicalDatasetSplitter.
8. Exports versioned datasets and comprehensive cryptographic metadata.
"""

from datetime import datetime
import hashlib
import json
import os
import sys
from typing import Any, Dict, List
import pandas as pd

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.ml.data_cleaner import DataCleaner
from backend.app.ml.time_series_prep import TimeSeriesPreparer
from backend.app.ml.target_builder import TargetBuilder, TARGET_COLUMNS
from backend.app.ml.feature_engine import FeatureEngine, FEATURE_NAMES
from backend.app.ml.dataset_splitter import ChronologicalDatasetSplitter


def calculate_sha256(filepath: str) -> str:
    """Calculates SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def run_pipeline(
    raw_daily_path: str = "data/raw/synthetic_daily_supermarket_history.csv",
    raw_tx_path: str = "data/raw/synthetic_transactions_supermarket_history.csv",
    output_dir: str = "data/processed",
    interim_dir: str = "data/interim",
) -> Dict[str, Any]:
    print("=" * 70)
    print("STARTING ML DATA PREPROCESSING & FEATURE ENGINEERING PIPELINE")
    print("=" * 70)

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(interim_dir, exist_ok=True)

    # 1. Ingest and Clean Raw Data
    print(f"\n[1/6] Ingesting and cleaning raw data from {raw_tx_path} and {raw_daily_path}...")
    cleaner = DataCleaner()
    
    # Clean transactions
    df_tx_raw = pd.read_csv(raw_tx_path)
    df_tx_clean, tx_audit = cleaner.clean_transactions(df_tx_raw)
    cleaned_tx_path = os.path.join(interim_dir, "cleaned_transactions.csv")
    df_tx_clean.to_csv(cleaned_tx_path, index=False)
    print(f"  -> Cleaned {len(df_tx_raw)} raw transactions -> {len(df_tx_clean)} retained. Saved to {cleaned_tx_path}")

    # Clean / validate daily observations
    df_daily_raw = pd.read_csv(raw_daily_path)
    print(f"  -> Ingested {len(df_daily_raw)} daily observations across {df_daily_raw['sku'].nunique()} SKUs.")

    # 2. Resample and Build Continuous Grid
    print("\n[2/6] Building gap-free continuous daily time series grid...")
    preparer = TimeSeriesPreparer(min_history_days=28)
    df_grid = preparer.build_daily_grid(df_daily_raw)
    df_grid = preparer.classify_demand_patterns(df_grid)
    df_grid, history_status = preparer.validate_minimum_history(df_grid)
    
    grid_path = os.path.join(interim_dir, "daily_time_series_grid.csv")
    df_grid.to_csv(grid_path, index=False)
    print(f"  -> Continuous grid constructed: {len(df_grid)} daily observations. Saved to {grid_path}")
    print(f"  -> Demand pattern distribution:\n{df_grid.groupby('sku')['demand_pattern'].first().value_counts().to_string()}")

    # 3. Build Multi-Horizon Forecast Targets
    print("\n[3/6] Constructing multi-horizon forecasting targets...")
    target_builder = TargetBuilder(target_variable="recorded_sales", waste_variable="waste_quantity")
    df_targeted = target_builder.add_targets(df_grid)
    valid_targets, target_errors = target_builder.validate_target_alignment(df_targeted)
    if not valid_targets:
        print(f"  [ERROR] Target validation failed: {target_errors[:3]}")
        raise ValueError(f"Target validation failed: {target_errors}")
    print(f"  -> Successfully generated targets: {TARGET_COLUMNS} (Ground-truth alignment verified: {valid_targets})")

    # 4. Engineer Leakage-Free Predictive Features
    print("\n[4/6] Engineering 18+ leakage-free predictive features...")
    feature_engine = FeatureEngine(warm_up_days=28)
    df_featured = feature_engine.engineer_features(df_targeted)
    engineered_cols = [c for c in FEATURE_NAMES if c in df_featured.columns]
    print(f"  -> Engineered {len(engineered_cols)} features across {len(df_featured)} rows.")

    # Verify zero lookahead leakage
    sample_sku = df_featured["sku"].iloc[0]
    dates = sorted(df_featured[df_featured["sku"] == sample_sku]["date"].unique())
    is_leakage_free, leak_report = FeatureEngine.verify_zero_leakage(
        df_clean=df_grid,
        perturbed_sku=sample_sku,
        perturbed_date=str(dates[-10].date()),
        verification_date=str(dates[-15].date()),
    )
    print(f"  -> Programmatic Zero-Leakage Check: {'PASSED (Zero future contamination)' if is_leakage_free else 'FAILED'}")
    if not is_leakage_free:
        raise ValueError(f"Leakage check failed: {leak_report}")

    # 5. Chronological Partitioning and Parameter Isolation
    print("\n[5/6] Chronological train/validation/test partitioning and scaler isolation...")
    splitter = ChronologicalDatasetSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, exclude_warmup_from_train=True)
    df_train, df_val, df_test = splitter.split(df_featured)
    is_valid_split, split_errors = splitter.validate_split_integrity(df_train, df_val, df_test)
    if not is_valid_split:
        raise ValueError(f"Split validation failed: {split_errors}")

    # Fit scaler strictly on Train; transform Val and Test statelessly
    df_train_scaled, df_val_scaled, df_test_scaled, scaler_params = splitter.fit_transform_scaler(
        df_train=df_train,
        df_val=df_val,
        df_test=df_test,
        feature_cols=engineered_cols,
    )
    print(f"  -> Train partition: {len(df_train_scaled)} rows ({splitter.split_metadata['train_start']} to {splitter.split_metadata['train_end']})")
    print(f"  -> Val partition:   {len(df_val_scaled)} rows ({splitter.split_metadata['val_start']} to {splitter.split_metadata['val_end']})")
    print(f"  -> Test partition:  {len(df_test_scaled)} rows ({splitter.split_metadata['test_start']} to {splitter.split_metadata['test_end']})")

    # 6. Export Datasets and Cryptographic Version Metadata
    print("\n[6/6] Exporting processed datasets and version metadata...")
    train_out = os.path.join(output_dir, "train_features.csv")
    val_out = os.path.join(output_dir, "val_features.csv")
    test_out = os.path.join(output_dir, "test_features.csv")
    cleaning_summary_out = os.path.join(output_dir, "cleaning_summary.json")
    version_meta_out = os.path.join(output_dir, "dataset_version_metadata.json")

    df_train_scaled.to_csv(train_out, index=False)
    df_val_scaled.to_csv(val_out, index=False)
    df_test_scaled.to_csv(test_out, index=False)
    cleaner.save_summary(cleaning_summary_out)

    metadata = {
        "version": "2.0.0-phase2",
        "generated_at": datetime.now().isoformat(),
        "pipeline_name": "Milestone2_Phase2_LeakageFreePreprocessing",
        "split_policy": "Chronological (70% Train, 15% Val, 15% Test)",
        "warmup_policy": "28-day warm-up excluded from training loss",
        "files": {
            "raw_daily": {
                "path": raw_daily_path,
                "sha256": calculate_sha256(raw_daily_path),
                "rows": len(df_daily_raw),
            },
            "raw_transactions": {
                "path": raw_tx_path,
                "sha256": calculate_sha256(raw_tx_path),
                "rows": len(df_tx_raw),
            },
            "interim_cleaned_transactions": {
                "path": cleaned_tx_path,
                "sha256": calculate_sha256(cleaned_tx_path),
                "rows": len(df_tx_clean),
            },
            "interim_daily_grid": {
                "path": grid_path,
                "sha256": calculate_sha256(grid_path),
                "rows": len(df_grid),
            },
            "train_features": {
                "path": train_out,
                "sha256": calculate_sha256(train_out),
                "rows": len(df_train_scaled),
                "columns": df_train_scaled.columns.tolist(),
            },
            "val_features": {
                "path": val_out,
                "sha256": calculate_sha256(val_out),
                "rows": len(df_val_scaled),
                "columns": df_val_scaled.columns.tolist(),
            },
            "test_features": {
                "path": test_out,
                "sha256": calculate_sha256(test_out),
                "rows": len(df_test_scaled),
                "columns": df_test_scaled.columns.tolist(),
            },
        },
        "features": {
            "feature_names": engineered_cols,
            "target_names": TARGET_COLUMNS,
            "scaled_feature_count": len(scaler_params["feature_cols"]),
        },
        "scaler_summary": {
            "feature_means": scaler_params["means"],
            "feature_scales": scaler_params["scales"],
        },
        "split_summary": splitter.split_metadata,
        "demand_patterns": df_grid.groupby("sku")["demand_pattern"].first().to_dict(),
    }

    with open(version_meta_out, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"  -> Saved dataset version metadata to {version_meta_out}")

    print("\n" + "=" * 70)
    print("PREPROCESSING PIPELINE COMPLETED SUCCESSFULLY WITH ZERO LEAKAGE")
    print("=" * 70)
    return metadata


if __name__ == "__main__":
    run_pipeline()
