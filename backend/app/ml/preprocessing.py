"""
Leakage-Free Time-Series Preprocessing and Feature Engineering Pipeline.

CRITICAL INVARIANTS:
1. Strict Temporal Ordering: No future data may leak into features at time t.
   All lag features and rolling aggregations MUST use shift(1) or shift(k >= 1).
2. Chronological Splitting: Train, validation, and test sets are split along time boundaries,
   never randomly shuffled.
3. Preprocessing Parameter Isolation: Scalers and encoders fit exclusively on the Training set.
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


UNIT_CONVERSION_FACTORS = {
    "lbs": ("kg", 0.45359237),
    "oz": ("g", 28.3495231),
    "fluid_oz": ("liters", 0.0295735),
    "grams": ("g", 1.0),
}


def clean_raw_transactions(df_tx: pd.DataFrame) -> pd.DataFrame:
    """
    Clean raw transaction logs:
    - Deduplicates transaction IDs.
    - Resolves missing timestamps using record sequence.
    - Normalizes units to canonical platform units.
    - Normalizes transaction quantity signs.
    """
    df = df_tx.copy()

    # Deduplicate transaction IDs
    df = df.drop_duplicates(subset=["transaction_id"], keep="first")

    # Drop records without SKU
    df = df.dropna(subset=["sku"])

    # Unit Normalization
    for raw_unit, (target_unit, factor) in UNIT_CONVERSION_FACTORS.items():
        mask = df["unit"].str.lower() == raw_unit.lower()
        if mask.any():
            df.loc[mask, "quantity_change"] = df.loc[mask, "quantity_change"] * factor
            if "quantity_before" in df.columns:
                df.loc[mask, "quantity_before"] = df.loc[mask, "quantity_before"] * factor
            if "quantity_after" in df.columns:
                df.loc[mask, "quantity_after"] = df.loc[mask, "quantity_after"] * factor
            df.loc[mask, "unit"] = target_unit

    # Enforce standard signs
    sales_mask = df["transaction_type"] == "POS_SALE"
    df.loc[sales_mask, "quantity_change"] = -df.loc[sales_mask, "quantity_change"].abs()

    waste_mask = df["transaction_type"] == "WASTE_DISPOSAL"
    df.loc[waste_mask, "quantity_change"] = -df.loc[waste_mask, "quantity_change"].abs()

    purchase_mask = df["transaction_type"].isin(["PURCHASE", "RESTOCK"])
    df.loc[purchase_mask, "quantity_change"] = df.loc[purchase_mask, "quantity_change"].abs()

    return df


def build_daily_time_series_grid(
    df_daily: pd.DataFrame,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Construct continuous, gap-free daily time series grid for every product SKU.
    Fills unobserved days with recorded_sales = 0.0 and forward-fills closing_stock.
    """
    df = df_daily.copy()
    df["date"] = pd.to_datetime(df["date"])

    min_date = pd.to_datetime(start_date) if start_date else df["date"].min()
    max_date = pd.to_datetime(end_date) if end_date else df["date"].max()
    full_dates = pd.date_range(min_date, max_date, freq="D", name="date")

    grid_list = []
    for sku, group in df.groupby("sku"):
        group = group.drop_duplicates(subset=["date"]).set_index("date").reindex(full_dates)
        group["sku"] = sku
        group["tenant_id"] = group["tenant_id"].ffill().bfill()
        group["product_name"] = group["product_name"].ffill().bfill()
        group["category_id"] = group["category_id"].ffill().bfill()
        group["unit"] = group["unit"].ffill().bfill()
        group["recorded_sales"] = group["recorded_sales"].fillna(0.0)
        group["waste_quantity"] = group["waste_quantity"].fillna(0.0)
        group["closing_stock"] = group["closing_stock"].ffill().fillna(0.0)
        group["is_stockout"] = group["is_stockout"].fillna(False)
        group = group.reset_index()
        grid_list.append(group)

    full_grid = pd.concat(grid_list, ignore_index=True)
    return full_grid


def generate_leakage_free_features(df_grid: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer predictive features with strictly zero lookahead leakage.
    
    All lag and rolling features operate on past values (shift >= 1).
    """
    df = df_grid.sort_values(["sku", "date"]).copy()
    df["date"] = pd.to_datetime(df["date"])

    feature_dfs = []
    for sku, group in df.groupby("sku"):
        g = group.sort_values("date").copy()
        target = g["recorded_sales"]

        # Lag features: sales at t-1, t-2, t-7, t-14, t-28
        g["lag_1"] = target.shift(1)
        g["lag_2"] = target.shift(2)
        g["lag_7"] = target.shift(7)
        g["lag_14"] = target.shift(14)
        g["lag_28"] = target.shift(28)

        # Rolling statistics (STRICT shift(1) before rolling)
        past_sales = target.shift(1)
        g["rolling_mean_7"] = past_sales.rolling(window=7, min_periods=1).mean()
        g["rolling_std_7"] = past_sales.rolling(window=7, min_periods=1).std().fillna(0.0)
        g["rolling_mean_14"] = past_sales.rolling(window=14, min_periods=1).mean()
        g["rolling_mean_28"] = past_sales.rolling(window=28, min_periods=1).mean()
        g["rolling_max_7"] = past_sales.rolling(window=7, min_periods=1).max()
        g["rolling_min_7"] = past_sales.rolling(window=7, min_periods=1).min()

        # Prior day stock and stockout indicator (t-1)
        g["prior_day_stock"] = g["closing_stock"].shift(1)
        g["prior_day_stockout"] = g["is_stockout"].shift(1).astype(float)

        # Calendar features
        g["day_of_week"] = g["date"].dt.day_of_week
        g["is_weekend"] = g["day_of_week"].isin([5, 6]).astype(int)
        g["day_of_month"] = g["date"].dt.day
        g["month"] = g["date"].dt.month

        # Waste history lag (t-7 rolling waste)
        past_waste = g["waste_quantity"].shift(1)
        g["rolling_waste_7"] = past_waste.rolling(window=7, min_periods=1).mean()

        feature_dfs.append(g)

    featured = pd.concat(feature_dfs, ignore_index=True)
    return featured


def chronological_train_val_test_split(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Partition time-series data chronologically without random shuffling.
    
    Default:
    - Train: First 70% of calendar dates.
    - Validation: Next 15% of calendar dates.
    - Test: Final 15% of calendar dates.
    """
    unique_dates = sorted(df["date"].unique())
    n_dates = len(unique_dates)

    train_end_idx = int(n_dates * train_ratio)
    val_end_idx = int(n_dates * (train_ratio + val_ratio))

    train_dates = set(unique_dates[:train_end_idx])
    val_dates = set(unique_dates[train_end_idx:val_end_idx])
    test_dates = set(unique_dates[val_end_idx:])

    df_train = df[df["date"].isin(train_dates)].copy()
    df_val = df[df["date"].isin(val_dates)].copy()
    df_test = df[df["date"].isin(test_dates)].copy()

    return df_train, df_val, df_test


class LeakageFreePreprocessor:
    """
    Scikit-learn style preprocessor that strictly fits on the training set
    and applies identical transformations to validation and test sets.
    """

    def __init__(self, feature_cols: List[str]):
        self.feature_cols = feature_cols
        self.scaler = StandardScaler()
        self.is_fitted = False

    def fit(self, df_train: pd.DataFrame) -> "LeakageFreePreprocessor":
        X = df_train[self.feature_cols].dropna()
        self.scaler.fit(X)
        self.is_fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.is_fitted:
            raise ValueError("Preprocessor must be fitted on training data before transforming.")
        df_out = df.copy()
        X = df_out[self.feature_cols].copy()
        # Impute remaining initial NaNs from lag lookback with 0
        X_clean = X.fillna(0.0)
        scaled_vals = self.scaler.transform(X_clean)
        for idx, col in enumerate(self.feature_cols):
            df_out[f"{col}_scaled"] = scaled_vals[:, idx]
        return df_out
