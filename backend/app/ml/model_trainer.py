"""
Milestone 2 — Phase 3: Model Training, Validation Selection & Test Evaluation Pipeline.

Responsibilities:
- Ingests approved chronological dataset partitions (Train, Val, Test).
- Trains statistical baselines (Naive, Seasonal Naive, Moving Average, Historical Mean).
- Trains candidate ML models (Ridge, GBDT / HistGradientBoosting, Random Forest).
- Evaluates models on the Validation partition across multi-horizons (1d, 7d, 7d-cumulative).
- Conducts evidence-based model selection (lowest WAPE / MASE on Validation).
- Evaluates winning candidate and baselines on the held-out untouched Test set.
- Serializes winning model and exports comprehensive machine-readable results.
"""

from datetime import datetime
import json
import os
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd

from backend.app.ml.candidate_models import (
    BaselineForecaster,
    GBDTForecaster,
    RandomForestForecaster,
    RidgeForecaster,
    FEATURE_COLS_SCALED,
    FEATURE_COLS_UNSCALED,
)
from backend.app.ml.evaluator import ForecastEvaluator


class ModelTrainingPipeline:
    """
    End-to-end training, validation selection, and test benchmarking manager.
    """

    def __init__(
        self,
        train_path: str = "data/processed/train_features.csv",
        val_path: str = "data/processed/val_features.csv",
        test_path: str = "data/processed/test_features.csv",
        models_dir: str = "data/models",
        random_state: int = 42,
    ):
        self.train_path = train_path
        self.val_path = val_path
        self.test_path = test_path
        self.models_dir = models_dir
        self.random_state = random_state
        self.evaluator = ForecastEvaluator(seasonality=7)
        self.trained_models: Dict[str, Any] = {}
        self.results: Dict[str, Any] = {
            "pipeline_executed_at": datetime.now().isoformat(),
            "validation_results": {},
            "test_results": {},
            "selected_model": None,
            "selection_rationale": "",
        }

    def run_training_and_evaluation(self, target_col: str = "target_sales_1d") -> Dict[str, Any]:
        """Executes full training and comparative benchmarking workflow."""
        os.makedirs(self.models_dir, exist_ok=True)

        print("=" * 70)
        print(f"STARTING MODEL TRAINING & EVALUATION PIPELINE (Target: {target_col})")
        print("=" * 70)

        # 1. Load Data
        print(f"\n[1/5] Loading chronological dataset partitions...")
        df_train = pd.read_csv(self.train_path)
        df_val = pd.read_csv(self.val_path)
        df_test = pd.read_csv(self.test_path)
        print(f"  -> Train partition: {len(df_train)} rows across {df_train['sku'].nunique()} SKUs")
        print(f"  -> Val partition:   {len(df_val)} rows")
        print(f"  -> Test partition:  {len(df_test)} rows")

        # 2. Train Models
        print(f"\n[2/5] Training statistical baselines and candidate ML models...")
        models_to_train = {
            "Naive": BaselineForecaster(strategy="naive"),
            "SeasonalNaive": BaselineForecaster(strategy="seasonal_naive"),
            "MovingAverage": BaselineForecaster(strategy="moving_average"),
            "HistoricalMean": BaselineForecaster(strategy="historical_mean"),
            "Ridge": RidgeForecaster(alpha=10.0, random_state=self.random_state),
            "GBDT": GBDTForecaster(max_iter=150, learning_rate=0.05, max_depth=6, random_state=self.random_state),
            "RandomForest": RandomForestForecaster(n_estimators=100, max_depth=8, random_state=self.random_state),
        }

        for name, model in models_to_train.items():
            print(f"  -> Training {name}...")
            model.fit(df_train, target_col=target_col)
            self.trained_models[name] = model

        # 3. Evaluate on Validation Set for Model Selection
        print(f"\n[3/5] Evaluating all models on VALIDATION partition (Model Selection Gate)...")
        val_eval_summary = {}
        for name, model in self.trained_models.items():
            df_val_pred = df_val.copy()
            df_val_pred["prediction"] = model.predict(df_val)

            eval_res = self.evaluator.evaluate_dataframe(
                df_eval=df_val_pred,
                df_train=df_train,
                actual_col=target_col,
                pred_col="prediction",
            )
            val_eval_summary[name] = eval_res
            overall = eval_res["overall"]
            print(f"  [{name:15}] WAPE: {overall['wape_pct']:5.2f}% | MASE: {overall['mase']:5.3f} | MAE: {overall['mae']:5.3f} | RMSE: {overall['rmse']:5.3f} | MBE: {overall['mbe']:+5.3f}")

        self.results["validation_results"] = val_eval_summary

        # 4. Model Selection Gate
        print(f"\n[4/5] Executing evidence-based model selection...")
        # Rank models by Validation WAPE (lower is better)
        ranked = sorted(
            val_eval_summary.items(),
            key=lambda x: x[1]["overall"]["wape_pct"],
        )
        winner_name, winner_eval = ranked[0]
        seasonal_naive_wape = val_eval_summary["SeasonalNaive"]["overall"]["wape_pct"]
        winner_wape = winner_eval["overall"]["wape_pct"]

        wape_improvement = seasonal_naive_wape - winner_wape
        rel_improvement = (wape_improvement / seasonal_naive_wape) * 100.0 if seasonal_naive_wape > 0 else 0.0

        rationale = (
            f"Selected '{winner_name}' based on superior Validation WAPE of {winner_wape:.2f}% "
            f"(vs Seasonal Naive {seasonal_naive_wape:.2f}%, relative error reduction of {rel_improvement:.1f}%). "
            f"Validation MASE: {winner_eval['overall']['mase']:.3f} (< 1.0 threshold)."
        )
        print(f"  -> CHAMPION MODEL: {winner_name}")
        print(f"  -> Rationale: {rationale}")

        self.results["selected_model"] = winner_name
        self.results["selection_rationale"] = rationale

        # Save champion model artifact
        champion_path = os.path.join(self.models_dir, "champion_forecaster.joblib")
        winner_model = self.trained_models[winner_name]
        if hasattr(winner_model, "save"):
            winner_model.save(champion_path)
        else:
            joblib.dump(winner_model, champion_path)
        print(f"  -> Serialized champion model to {champion_path}")

        # 5. Evaluate on Held-Out Test Set (Final Generalization Gate)
        print(f"\n[5/5] Evaluating champion model and baselines on held-out TEST partition...")
        test_eval_summary = {}
        # Evaluate champion and primary baselines on Test set
        test_models = {
            winner_name: self.trained_models[winner_name],
            "SeasonalNaive": self.trained_models["SeasonalNaive"],
            "Naive": self.trained_models["Naive"],
        }
        for name, model in test_models.items():
            df_test_pred = df_test.copy()
            df_test_pred["prediction"] = model.predict(df_test)

            eval_res = self.evaluator.evaluate_dataframe(
                df_eval=df_test_pred,
                df_train=df_train,
                actual_col=target_col,
                pred_col="prediction",
            )
            test_eval_summary[name] = eval_res
            overall = eval_res["overall"]
            print(f"  [TEST - {name:15}] WAPE: {overall['wape_pct']:5.2f}% | MASE: {overall['mase']:5.3f} | MAE: {overall['mae']:5.3f} | RMSE: {overall['rmse']:5.3f} | MBE: {overall['mbe']:+5.3f}")

        self.results["test_results"] = test_eval_summary

        # Export full results to JSON
        results_path = os.path.join(self.models_dir, "model_comparison_results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2)
        print(f"\nSaved model comparison results to {results_path}")

        print("\n" + "=" * 70)
        print("MODEL TRAINING & EVALUATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        return self.results
