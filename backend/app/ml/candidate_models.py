"""
Milestone 2 — Phase 3: Forecasting Candidate Models and Baselines.

Implements:
1. BaselineForecaster:
   - Naive (lag 1 persistence)
   - Seasonal Naive (lag 7 weekly seasonal persistence)
   - Rolling 7-Day Moving Average
   - Historical Mean
2. RidgeForecaster:
   - L2 regularized linear model over scaled features
3. GBDTForecaster:
   - Gradient Boosted Decision Trees (HistGradientBoostingRegressor)
   - Native non-linear interactions, monotonic non-negative bounds
4. RandomForestForecaster:
   - Bagged decision tree ensemble with variance reduction

All models enforce physical non-negativity (clipping at 0.0) and provide
standardized fit, predict, save, and load interfaces.
"""

import os
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge


FEATURE_COLS_UNSCALED = [
    "lag_1",
    "lag_2",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_std_7",
    "rolling_mean_14",
    "rolling_mean_28",
    "rolling_max_7",
    "rolling_min_7",
    "rolling_waste_7",
    "prior_day_stock",
    "prior_day_stockout",
    "shelf_life_days",
    "unit_cost",
    "selling_price",
    "gross_margin",
    "gross_margin_ratio",
    "day_of_week",
    "is_weekend",
    "day_of_month",
    "month",
    "is_month_start",
    "is_month_end",
    "sin_dow",
    "cos_dow",
    "category_code",
]

FEATURE_COLS_SCALED = [
    "lag_1_scaled",
    "lag_2_scaled",
    "lag_7_scaled",
    "lag_14_scaled",
    "lag_28_scaled",
    "rolling_mean_7_scaled",
    "rolling_std_7_scaled",
    "rolling_mean_14_scaled",
    "rolling_mean_28_scaled",
    "rolling_max_7_scaled",
    "rolling_min_7_scaled",
    "rolling_waste_7_scaled",
    "prior_day_stock_scaled",
    "prior_day_stockout_scaled",
    "shelf_life_days_scaled",
    "unit_cost_scaled",
    "selling_price_scaled",
    "gross_margin_scaled",
    "gross_margin_ratio_scaled",
    "day_of_week_scaled",
    "is_weekend_scaled",
    "day_of_month_scaled",
    "month_scaled",
    "is_month_start_scaled",
    "is_month_end_scaled",
    "sin_dow_scaled",
    "cos_dow_scaled",
]


class BaselineForecaster:
    """Statistical forecasting baselines operating on feature representation."""

    def __init__(self, strategy: str = "seasonal_naive"):
        valid_strategies = ["naive", "seasonal_naive", "moving_average", "historical_mean"]
        if strategy not in valid_strategies:
            raise ValueError(f"Invalid strategy '{strategy}'. Choose from {valid_strategies}")
        self.strategy = strategy
        self.sku_means: Dict[str, float] = {}

    def fit(self, df_train: pd.DataFrame, target_col: str = "target_sales_1d") -> "BaselineForecaster":
        """Record historical statistics for baselines requiring in-sample history."""
        if self.strategy == "historical_mean":
            for sku, group in df_train.groupby("sku"):
                self.sku_means[sku] = float(group[target_col].mean())
            self.sku_means["__global__"] = float(df_train[target_col].mean())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Generate baseline predictions using the precomputed features."""
        if self.strategy == "naive":
            # Yesterday's value (lag_1)
            preds = df["lag_1"].fillna(0.0).to_numpy()
        elif self.strategy == "seasonal_naive":
            # Same day last week (lag_7); fallback to lag_1 if NaN
            preds = df["lag_7"].fillna(df["lag_1"]).fillna(0.0).to_numpy()
        elif self.strategy == "moving_average":
            # 7-day rolling mean
            preds = df["rolling_mean_7"].fillna(df["lag_1"]).fillna(0.0).to_numpy()
        elif self.strategy == "historical_mean":
            preds = np.array([
                self.sku_means.get(row.get("sku"), self.sku_means.get("__global__", 0.0))
                for _, row in df.iterrows()
            ])
        else:
            preds = np.zeros(len(df))

        # Enforce non-negativity
        return np.clip(preds, 0.0, None)


class RidgeForecaster:
    """L2 Regularized Linear Regression Forecaster."""

    def __init__(self, alpha: float = 10.0, feature_cols: Optional[List[str]] = None, random_state: int = 42):
        self.alpha = alpha
        self.feature_cols = feature_cols or FEATURE_COLS_SCALED
        self.random_state = random_state
        self.model = Ridge(alpha=self.alpha, random_state=self.random_state)
        self.is_fitted = False

    def fit(self, df_train: pd.DataFrame, target_col: str = "target_sales_1d") -> "RidgeForecaster":
        valid_cols = [c for c in self.feature_cols if c in df_train.columns]
        X = df_train[valid_cols].fillna(0.0).to_numpy()
        y = df_train[target_col].to_numpy()
        self.model.fit(X, y)
        self.is_fitted = True
        self.feature_cols = valid_cols
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise ValueError("RidgeForecaster must be fitted before predict.")
        X = df[self.feature_cols].fillna(0.0).to_numpy()
        preds = self.model.predict(X)
        return np.clip(preds, 0.0, None)

    def save(self, filepath: str):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        joblib.dump({"model": self.model, "feature_cols": self.feature_cols, "type": "RidgeForecaster"}, filepath)

    @classmethod
    def load(cls, filepath: str) -> "RidgeForecaster":
        data = joblib.load(filepath)
        forecaster = cls(feature_cols=data["feature_cols"])
        forecaster.model = data["model"]
        forecaster.is_fitted = True
        return forecaster


class GBDTForecaster:
    """Gradient Boosted Decision Trees Forecaster (LightGBM-style HistGradientBoostingRegressor)."""

    def __init__(
        self,
        max_iter: int = 150,
        learning_rate: float = 0.05,
        max_depth: int = 6,
        min_samples_leaf: int = 15,
        feature_cols: Optional[List[str]] = None,
        random_state: int = 42,
    ):
        self.max_iter = max_iter
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.feature_cols = feature_cols or FEATURE_COLS_UNSCALED
        self.random_state = random_state
        self.model = HistGradientBoostingRegressor(
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.random_state,
            early_stopping=True,
            n_iter_no_change=10,
        )
        self.is_fitted = False

    def fit(self, df_train: pd.DataFrame, target_col: str = "target_sales_1d") -> "GBDTForecaster":
        valid_cols = [c for c in self.feature_cols if c in df_train.columns]
        X = df_train[valid_cols].fillna(0.0).to_numpy()
        y = df_train[target_col].to_numpy()
        self.model.fit(X, y)
        self.is_fitted = True
        self.feature_cols = valid_cols
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise ValueError("GBDTForecaster must be fitted before predict.")
        X = df[self.feature_cols].fillna(0.0).to_numpy()
        preds = self.model.predict(X)
        return np.clip(preds, 0.0, None)

    def save(self, filepath: str):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        joblib.dump({"model": self.model, "feature_cols": self.feature_cols, "type": "GBDTForecaster"}, filepath)

    @classmethod
    def load(cls, filepath: str) -> "GBDTForecaster":
        data = joblib.load(filepath)
        forecaster = cls(feature_cols=data["feature_cols"])
        forecaster.model = data["model"]
        forecaster.is_fitted = True
        return forecaster


class RandomForestForecaster:
    """Random Forest Ensemble Forecaster."""

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 8,
        min_samples_leaf: int = 5,
        feature_cols: Optional[List[str]] = None,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.feature_cols = feature_cols or FEATURE_COLS_UNSCALED
        self.random_state = random_state
        self.model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.is_fitted = False

    def fit(self, df_train: pd.DataFrame, target_col: str = "target_sales_1d") -> "RandomForestForecaster":
        valid_cols = [c for c in self.feature_cols if c in df_train.columns]
        X = df_train[valid_cols].fillna(0.0).to_numpy()
        y = df_train[target_col].to_numpy()
        self.model.fit(X, y)
        self.is_fitted = True
        self.feature_cols = valid_cols
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise ValueError("RandomForestForecaster must be fitted before predict.")
        X = df[self.feature_cols].fillna(0.0).to_numpy()
        preds = self.model.predict(X)
        return np.clip(preds, 0.0, None)

    def save(self, filepath: str):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        joblib.dump({"model": self.model, "feature_cols": self.feature_cols, "type": "RandomForestForecaster"}, filepath)

    @classmethod
    def load(cls, filepath: str) -> "RandomForestForecaster":
        data = joblib.load(filepath)
        forecaster = cls(feature_cols=data["feature_cols"])
        forecaster.model = data["model"]
        forecaster.is_fitted = True
        return forecaster
