"""
Forecasting Baselines and Statistical Evaluation Metrics.

Implements:
- Naive Forecast (t-1 persistence)
- Seasonal Naive Forecast (t-7 weekly seasonal persistence)
- 7-Day Moving Average Baseline
- Robust metrics: MAE, RMSE, WAPE, and MASE (Mean Absolute Scaled Error)
"""

from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


def compute_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error: (1/n) * sum(|y - y_hat|)"""
    return float(np.mean(np.abs(y_true - y_pred)))


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error: sqrt((1/n) * sum((y - y_hat)^2))"""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def compute_wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Weighted Absolute Percentage Error (WAPE): sum(|y - y_hat|) / sum(y).
    
    Robust against zero values where traditional MAPE explodes.
    Returns 0.0 if total actual demand is 0.
    """
    total_actual = float(np.sum(y_true))
    if total_actual == 0.0:
        return 0.0 if np.sum(np.abs(y_pred)) == 0 else 1.0
    return float(np.sum(np.abs(y_true - y_pred)) / total_actual)


def compute_mase(
    y_train: np.ndarray,
    y_test: np.ndarray,
    y_pred: np.ndarray,
    seasonality: int = 1,
) -> float:
    """
    Mean Absolute Scaled Error (MASE).
    
    Scales the forecast error relative to in-sample one-step naive error.
    MASE < 1.0 indicates model outperforms the baseline naive forecast.
    """
    # In-sample naive benchmark error
    if len(y_train) <= seasonality:
        return 1.0
    d_denom = np.mean(np.abs(y_train[seasonality:] - y_train[:-seasonality]))
    if d_denom == 0.0:
        return 1.0
    mae_test = np.mean(np.abs(y_test - y_pred))
    return float(mae_test / d_denom)


def evaluate_forecast(
    y_train: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    seasonality: int = 7,
) -> Dict[str, float]:
    """Calculate standard forecast evaluation metrics."""
    return {
        "mae": round(compute_mae(y_true, y_pred), 3),
        "rmse": round(compute_rmse(y_true, y_pred), 3),
        "wape_pct": round(compute_wape(y_true, y_pred) * 100.0, 2),
        "mase": round(compute_mase(y_train, y_true, y_pred, seasonality=seasonality), 3),
    }


class NaiveBaseline:
    """
    Naive Forecast: Predicts the immediate prior observation (y_{t+h} = y_t).
    """

    def predict(self, series: pd.Series, horizon: int = 1) -> np.ndarray:
        if len(series) == 0:
            return np.zeros(horizon)
        last_val = series.iloc[-1]
        return np.full(horizon, last_val)


class SeasonalNaiveBaseline:
    """
    Seasonal Naive Forecast: Predicts the observation from one seasonal cycle ago.
    For daily data with weekly seasonality, period = 7 (y_{t+h} = y_{t+h-7}).
    """

    def __init__(self, period: int = 7):
        self.period = period

    def predict(self, series: pd.Series, horizon: int = 7) -> np.ndarray:
        n = len(series)
        if n < self.period:
            return np.full(horizon, series.iloc[-1] if n > 0 else 0.0)
        # Take the last 'period' observations and tile them over horizon
        cycle = series.iloc[-self.period:].values
        reps = (horizon // self.period) + 1
        return np.tile(cycle, reps)[:horizon]


class MovingAverageBaseline:
    """
    Rolling Moving Average Baseline: Predicts the mean of the past K observations.
    """

    def __init__(self, window: int = 7):
        self.window = window

    def predict(self, series: pd.Series, horizon: int = 1) -> np.ndarray:
        if len(series) == 0:
            return np.zeros(horizon)
        val = series.iloc[-self.window:].mean()
        return np.full(horizon, val)
