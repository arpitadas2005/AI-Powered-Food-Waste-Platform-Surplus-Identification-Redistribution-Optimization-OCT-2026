"""
Milestone 2 — Phase 3: Train and Evaluate Forecasting Models Script.

Orchestrator script that:
1. Executes model training and validation selection for 1-day ahead sales (target_sales_1d).
2. Executes model training and validation selection for 7-day cumulative sales (target_demand_7d_sum).
3. Compares all baselines and candidates across MAE, RMSE, WAPE, and MASE.
4. Serializes the champion models and writes summary metrics to disk.
"""

import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.ml.model_trainer import ModelTrainingPipeline


def main():
    pipeline_1d = ModelTrainingPipeline(
        train_path="data/processed/train_features.csv",
        val_path="data/processed/val_features.csv",
        test_path="data/processed/test_features.csv",
        models_dir="data/models",
        random_state=42,
    )
    results_1d = pipeline_1d.run_training_and_evaluation(target_col="target_sales_1d")
    # Save explicit 1d champion
    champ_1d = pipeline_1d.trained_models[results_1d["selected_model"]]
    if hasattr(champ_1d, "save"):
        champ_1d.save("data/models/champion_1d_forecaster.joblib")
    else:
        import joblib
        joblib.dump(champ_1d, "data/models/champion_1d_forecaster.joblib")

    # Also evaluate for 7-day cumulative demand (crucial for replenishment & expiration risk)
    pipeline_7d = ModelTrainingPipeline(
        train_path="data/processed/train_features.csv",
        val_path="data/processed/val_features.csv",
        test_path="data/processed/test_features.csv",
        models_dir="data/models",
        random_state=42,
    )
    results_7d = pipeline_7d.run_training_and_evaluation(target_col="target_demand_7d_sum")
    # Save explicit 7d champion
    champ_7d = pipeline_7d.trained_models[results_7d["selected_model"]]
    if hasattr(champ_7d, "save"):
        champ_7d.save("data/models/champion_7d_forecaster.joblib")
    else:
        import joblib
        joblib.dump(champ_7d, "data/models/champion_7d_forecaster.joblib")

    # Save comprehensive comparison json
    import json
    combined_summary = {
        "target_sales_1d": results_1d,
        "target_demand_7d_sum": results_7d,
    }
    with open("data/models/complete_forecasting_benchmarks.json", "w", encoding="utf-8") as f:
        json.dump(combined_summary, f, indent=2)
    print("\nSaved complete combined benchmarks to data/models/complete_forecasting_benchmarks.json")

    print("\nSUMMARY OF RESULTS:")
    print(f"1-Day Ahead Forecast Champion: {results_1d['selected_model']}")
    print(f"1-Day Validation WAPE: {results_1d['validation_results'][results_1d['selected_model']]['overall']['wape_pct']}%")
    print(f"1-Day Test WAPE:       {results_1d['test_results'][results_1d['selected_model']]['overall']['wape_pct']}%")
    print(f"7-Day Cumulative Champion:    {results_7d['selected_model']}")
    print(f"7-Day Validation WAPE: {results_7d['validation_results'][results_7d['selected_model']]['overall']['wape_pct']}%")
    print(f"7-Day Test WAPE:       {results_7d['test_results'][results_7d['selected_model']]['overall']['wape_pct']}%")


if __name__ == "__main__":
    main()
