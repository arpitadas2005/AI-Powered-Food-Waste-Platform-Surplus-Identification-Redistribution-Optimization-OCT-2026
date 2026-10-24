"""
Milestone 2 — Phase 2: Leakage-Free Feature Engineering Engine.

Responsibilities:
- Engineers 18+ predictive features across 4 families:
  1. Autoregressive Lags (lag_1, lag_2, lag_7, lag_14, lag_28)
  2. Rolling Window Aggregations (rolling_mean_7, rolling_std_7, rolling_mean_14,
     rolling_mean_28, rolling_max_7, rolling_min_7, rolling_waste_7)
  3. Inventory & Financial Context (prior_day_stock, prior_day_stockout, shelf_life_days,
     unit_cost, selling_price, gross_margin, gross_margin_ratio)
  4. Calendar & Seasonal Indicators (day_of_week, is_weekend, day_of_month, month,
     is_month_start, is_month_end, sin_dow, cos_dow)
- Strictly enforces shift(1) or shift(k >= 1) on all historical series before computing rolling windows.
- Tags initial 28-day warm-up window per series (is_warmup).
- Supports category encoding.
- Verifies mathematical invariance against future data contamination.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


FEATURE_NAMES = [
    # Lags
    "lag_1",
    "lag_2",
    "lag_7",
    "lag_14",
    "lag_28",
    # Rolling stats
    "rolling_mean_7",
    "rolling_std_7",
    "rolling_mean_14",
    "rolling_mean_28",
    "rolling_max_7",
    "rolling_min_7",
    "rolling_waste_7",
    # Inventory & Economics
    "prior_day_stock",
    "prior_day_stockout",
    "shelf_life_days",
    "unit_cost",
    "selling_price",
    "gross_margin",
    "gross_margin_ratio",
    # Calendar & Seasonality
    "day_of_week",
    "is_weekend",
    "day_of_month",
    "month",
    "is_month_start",
    "is_month_end",
    "sin_dow",
    "cos_dow",
]


class FeatureEngine:
    """
    Transforms continuous time series into leakage-free feature vectors.
    """

    def __init__(self, warm_up_days: int = 28):
        self.warm_up_days = warm_up_days
        self.category_map: Dict[str, int] = {}

    def get_feature_names(self) -> List[str]:
        """Returns the complete list of standard engineered feature names."""
        return list(FEATURE_NAMES)

    def engineer_features(self, df_grid: pd.DataFrame) -> pd.DataFrame:
        """
        Generates leakage-free features for all SKUs in df_grid.
        
        Guarantees:
        - For every feature at index t, only information from <= t-1 is accessed
          for sales/waste/stock.
        - Calendar features at time t represent known calendar context.
        """
        df = df_grid.sort_values(["sku", "date"]).copy()
        df["date"] = pd.to_datetime(df["date"])

        # Populate or reuse category encoding map
        if "category_id" in df.columns:
            unique_cats = sorted(df["category_id"].dropna().unique())
            self.category_map = {cat: idx for idx, cat in enumerate(unique_cats)}

        feature_dfs = []
        for sku, group in df.groupby("sku"):
            g = group.sort_values("date").copy()
            sales = g["recorded_sales"]
            waste = g["waste_quantity"] if "waste_quantity" in g.columns else pd.Series(0.0, index=g.index)
            closing_stock = g["closing_stock"] if "closing_stock" in g.columns else pd.Series(0.0, index=g.index)
            stockout = g["is_stockout"] if "is_stockout" in g.columns else (closing_stock <= 0.0)

            # 1. Autoregressive Lag Features (strictly shift >= 1)
            g["lag_1"] = sales.shift(1)
            g["lag_2"] = sales.shift(2)
            g["lag_7"] = sales.shift(7)
            g["lag_14"] = sales.shift(14)
            g["lag_28"] = sales.shift(28)

            # 2. Rolling Window Aggregations (STRICT shift(1) applied FIRST)
            past_sales = sales.shift(1)
            g["rolling_mean_7"] = past_sales.rolling(window=7, min_periods=1).mean()
            g["rolling_std_7"] = past_sales.rolling(window=7, min_periods=1).std().fillna(0.0)
            g["rolling_mean_14"] = past_sales.rolling(window=14, min_periods=1).mean()
            g["rolling_mean_28"] = past_sales.rolling(window=28, min_periods=1).mean()
            g["rolling_max_7"] = past_sales.rolling(window=7, min_periods=1).max()
            g["rolling_min_7"] = past_sales.rolling(window=7, min_periods=1).min()

            past_waste = waste.shift(1)
            g["rolling_waste_7"] = past_waste.rolling(window=7, min_periods=1).mean()

            # 3. Inventory & Economic Context (prior day state at t-1)
            g["prior_day_stock"] = closing_stock.shift(1)
            g["prior_day_stockout"] = stockout.shift(1).astype(float)

            cost = g["unit_cost"] if "unit_cost" in g.columns else pd.Series(0.0, index=g.index)
            price = g["selling_price"] if "selling_price" in g.columns else pd.Series(0.0, index=g.index)
            margin = (price - cost).clip(lower=0.0)
            margin_ratio = np.where(price > 0, margin / price, 0.0)

            g["gross_margin"] = margin
            g["gross_margin_ratio"] = margin_ratio
            if "shelf_life_days" not in g.columns:
                g["shelf_life_days"] = 14.0

            # 4. Calendar Features (Known deterministic time context at day t)
            dow = g["date"].dt.day_of_week
            g["day_of_week"] = dow
            g["is_weekend"] = dow.isin([5, 6]).astype(int)
            g["day_of_month"] = g["date"].dt.day
            g["month"] = g["date"].dt.month
            g["is_month_start"] = g["date"].dt.is_month_start.astype(int)
            g["is_month_end"] = g["date"].dt.is_month_end.astype(int)

            # Cyclical encoding for day of week
            g["sin_dow"] = np.sin(2 * np.pi * dow / 7.0).round(4)
            g["cos_dow"] = np.cos(2 * np.pi * dow / 7.0).round(4)

            # Category code
            if "category_id" in g.columns:
                g["category_code"] = g["category_id"].map(self.category_map).fillna(-1).astype(int)

            # 5. Warm-up sequence flag
            day_indices = np.arange(len(g))
            g["is_warmup"] = day_indices < self.warm_up_days

            feature_dfs.append(g)

        result_df = pd.concat(feature_dfs, ignore_index=True)
        return result_df.sort_values(["sku", "date"]).reset_index(drop=True)

    @staticmethod
    def verify_zero_leakage(
        df_clean: pd.DataFrame,
        perturbed_sku: str,
        perturbed_date: str,
        verification_date: str,
        feature_cols: Optional[List[str]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Perturbs future sales at (perturbed_sku, perturbed_date) and verifies that
        features at verification_date (where verification_date < perturbed_date)
        remain exactly unchanged.
        """
        engine = FeatureEngine()
        orig_features = engine.engineer_features(df_clean)

        perturbed_df = df_clean.copy()
        mask = (perturbed_df["sku"] == perturbed_sku) & (pd.to_datetime(perturbed_df["date"]) == pd.to_datetime(perturbed_date))
        perturbed_df.loc[mask, "recorded_sales"] = 99999.0

        new_features = engine.engineer_features(perturbed_df)

        cols_to_check = feature_cols or [c for c in FEATURE_NAMES if c in orig_features.columns]
        
        orig_row = orig_features[
            (orig_features["sku"] == perturbed_sku) & (pd.to_datetime(orig_features["date"]) == pd.to_datetime(verification_date))
        ].iloc[0]
        new_row = new_features[
            (new_features["sku"] == perturbed_sku) & (pd.to_datetime(new_features["date"]) == pd.to_datetime(verification_date))
        ].iloc[0]

        discrepancies = {}
        for col in cols_to_check:
            val_orig = orig_row[col]
            val_new = new_row[col]
            if not np.isclose(val_orig, val_new, equal_nan=True):
                discrepancies[col] = {"original": float(val_orig), "perturbed": float(val_new)}

        is_leakage_free = len(discrepancies) == 0
        return is_leakage_free, discrepancies
