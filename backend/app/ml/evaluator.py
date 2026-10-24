"""
Milestone 2 — Phase 3: Time Series Forecast Evaluation Engine.

Provides robust, sparsity-aware evaluation metrics:
- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- Weighted Absolute Percentage Error (WAPE %)
- Mean Absolute Scaled Error (MASE)
- Mean Bias Error (MBE / Signed Error)
- Forecast Accuracy (%)

Includes mathematical guards against zero denominators, zero actual sales,
and evaluates performance across demand patterns (Smooth vs Intermittent).
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


def compute_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error in physical units."""
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(np.abs(y_true - y_pred)))


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error in physical units."""
    if len(y_true) == 0:
        return 0.0
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def compute_wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Weighted Absolute Percentage Error (WAPE %): sum(|y - y_hat|) / sum(y) * 100.
    
    Robust against zero values where traditional MAPE explodes.
    Returns 0.0 if both actual and predicted sums are zero.
    """
    if len(y_true) == 0:
        return 0.0
    actual_sum = float(np.sum(y_true))
    abs_err_sum = float(np.sum(np.abs(y_true - y_pred)))
    if actual_sum == 0.0:
        return 0.0 if abs_err_sum == 0.0 else 100.0
    return float((abs_err_sum / actual_sum) * 100.0)


def compute_mase(
    y_train: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    seasonality: int = 7,
) -> float:
    """
    Mean Absolute Scaled Error (MASE).
    
    Scales the out-of-sample forecast error relative to in-sample seasonal naive benchmark error.
    MASE < 1.0 indicates model beats seasonal persistence.
    """
    if len(y_true) == 0:
        return 0.0
    mae = float(np.mean(np.abs(y_true - y_pred)))
    if len(y_train) <= seasonality:
        # Fall back to lag-1 naive if series is shorter than seasonality
        seasonality = 1
    if len(y_train) <= 1:
        return 1.0

    # In-sample naive difference
    diffs = np.abs(y_train[seasonality:] - y_train[:-seasonality])
    denom = float(np.mean(diffs)) if len(diffs) > 0 else 0.0

    if denom == 0.0:
        return 0.0 if mae == 0.0 else 1.0
    return float(mae / denom)


def compute_mbe(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Mean Bias Error: (1/n) * sum(y_hat - y).
    Positive = over-forecasting (surplus risk); Negative = under-forecasting (stockout risk).
    """
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(y_pred - y_true))


class ForecastEvaluator:
    """
    Evaluates forecast series against ground truth across overall, per-SKU,
    and demand pattern groupings.
    """

    def __init__(self, seasonality: int = 7):
        self.seasonality = seasonality

    def evaluate(
        self,
        y_train: np.ndarray,
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> Dict[str, float]:
        """Calculates standard dictionary of forecast metrics."""
        y_t = np.asarray(y_true, dtype=float)
        y_p = np.asarray(y_pred, dtype=float)
        y_tr = np.asarray(y_train, dtype=float)

        mae = compute_mae(y_t, y_p)
        rmse = compute_rmse(y_t, y_p)
        wape = compute_wape(y_t, y_p)
        mase = compute_mase(y_tr, y_t, y_p, seasonality=self.seasonality)
        mbe = compute_mbe(y_t, y_p)
        accuracy = max(0.0, 100.0 - wape)

        return {
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "wape_pct": round(wape, 2),
            "mase": round(mase, 3),
            "mbe": round(mbe, 3),
            "accuracy_pct": round(accuracy, 2),
            "sample_count": int(len(y_t)),
        }

    def evaluate_dataframe(
        self,
        df_eval: pd.DataFrame,
        df_train: pd.DataFrame,
        actual_col: str,
        pred_col: str,
        group_col: str = "sku",
        pattern_col: Optional[str] = "demand_pattern",
    ) -> Dict[str, Any]:
        """
        Evaluates a dataframe containing predictions and actuals:
        - Overall aggregate metrics
        - Per-SKU breakdown
        - Per-demand-pattern breakdown (Smooth vs Intermittent)
        """
        # Drop rows where target is NaN (e.g. tail horizon rows)
        valid_mask = df_eval[actual_col].notna() & df_eval[pred_col].notna()
        clean_eval = df_eval[valid_mask].copy()

        y_true_all = clean_eval[actual_col].to_numpy()
        y_pred_all = clean_eval[pred_col].to_numpy()
        y_train_all = df_train[actual_col].dropna().to_numpy() if actual_col in df_train.columns else df_train["recorded_sales"].dropna().to_numpy()

        overall_metrics = self.evaluate(y_train_all, y_true_all, y_pred_all)

        # Per-SKU metrics
        sku_metrics: Dict[str, Dict[str, float]] = {}
        for sku, group in clean_eval.groupby(group_col):
            g_true = group[actual_col].to_numpy()
            g_pred = group[pred_col].to_numpy()
            tr_sku = df_train[df_train[group_col] == sku]
            tr_vals = tr_sku[actual_col].dropna().to_numpy() if actual_col in tr_sku.columns else tr_sku["recorded_sales"].dropna().to_numpy()
            sku_metrics[sku] = self.evaluate(tr_vals, g_true, g_pred)

        # Per-demand-pattern metrics
        pattern_metrics: Dict[str, Dict[str, float]] = {}
        if pattern_col and pattern_col in clean_eval.columns:
            for pat, group in clean_eval.groupby(pattern_col):
                p_true = group[actual_col].to_numpy()
                p_pred = group[pred_col].to_numpy()
                tr_pat = df_train[df_train[pattern_col] == pat] if pattern_col in df_train.columns else df_train
                tr_vals = tr_pat[actual_col].dropna().to_numpy() if actual_col in tr_pat.columns else tr_pat["recorded_sales"].dropna().to_numpy()
                pattern_metrics[pat] = self.evaluate(tr_vals, p_true, p_pred)

        return {
            "overall": overall_metrics,
            "by_sku": sku_metrics,
            "by_pattern": pattern_metrics,
        }
