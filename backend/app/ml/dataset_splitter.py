"""
Milestone 2 — Phase 2: Chronological Dataset Splitter & Parameter Isolation Engine.

Responsibilities:
- Partitions continuous time series chronologically into Train (70%), Val (15%), Test (15%).
- Enforces strict chronological boundaries with zero temporal overlap.
- Excludes 28-day warm-up window from training evaluation to prevent NaN propagation.
- Fits feature scalers strictly on the Training split.
- Applies transformations statelessly to Validation and Test splits.
- Preserves exportable scaling metadata for auditing and deployment.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


class ChronologicalDatasetSplitter:
    """
    Partitions datasets chronologically and isolates feature transformation parameters.
    """

    def __init__(
        self,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        exclude_warmup_from_train: bool = True,
    ):
        if not np.isclose(train_ratio + val_ratio + test_ratio, 1.0):
            raise ValueError(f"Split ratios must sum to 1.0. Got {train_ratio + val_ratio + test_ratio}")
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.exclude_warmup_from_train = exclude_warmup_from_train
        self.scaler: Optional[StandardScaler] = None
        self.scaled_feature_cols: List[str] = []
        self.split_metadata: Dict[str, Any] = {}

    def split(
        self,
        df: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Splits df into Train, Validation, and Test sets based on unique chronological dates.
        """
        df_copy = df.copy()
        df_copy["date"] = pd.to_datetime(df_copy["date"])
        unique_dates = sorted(df_copy["date"].unique())
        n_dates = len(unique_dates)

        train_cutoff_idx = int(n_dates * self.train_ratio)
        val_cutoff_idx = int(n_dates * (self.train_ratio + self.val_ratio))

        train_dates = set(unique_dates[:train_cutoff_idx])
        val_dates = set(unique_dates[train_cutoff_idx:val_cutoff_idx])
        test_dates = set(unique_dates[val_cutoff_idx:])

        df_train = df_copy[df_copy["date"].isin(train_dates)].copy()
        df_val = df_copy[df_copy["date"].isin(val_dates)].copy()
        df_test = df_copy[df_copy["date"].isin(test_dates)].copy()

        # Optionally drop warm-up observations from training set to avoid NaN loss during training
        if self.exclude_warmup_from_train and "is_warmup" in df_train.columns:
            df_train = df_train[~df_train["is_warmup"]].copy()

        self.split_metadata = {
            "total_dates": n_dates,
            "train_days": len(train_dates),
            "val_days": len(val_dates),
            "test_days": len(test_dates),
            "train_start": str(min(train_dates).date()),
            "train_end": str(max(train_dates).date()),
            "val_start": str(min(val_dates).date()),
            "val_end": str(max(val_dates).date()),
            "test_start": str(min(test_dates).date()),
            "test_end": str(max(test_dates).date()),
            "train_records": len(df_train),
            "val_records": len(df_val),
            "test_records": len(df_test),
        }

        return df_train, df_val, df_test

    def fit_transform_scaler(
        self,
        df_train: pd.DataFrame,
        df_val: pd.DataFrame,
        df_test: pd.DataFrame,
        feature_cols: List[str],
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """
        Fits StandardScaler strictly on df_train features.
        Transforms df_train, df_val, and df_test statelessly.
        """
        self.scaled_feature_cols = [c for c in feature_cols if c in df_train.columns]
        self.scaler = StandardScaler()

        # Extract training features and impute any remaining NaNs with 0
        X_train = df_train[self.scaled_feature_cols].fillna(0.0).to_numpy()
        self.scaler.fit(X_train)

        # Record scaler parameters for reproducibility
        scaler_params = {
            "feature_cols": self.scaled_feature_cols,
            "means": {col: float(m) for col, m in zip(self.scaled_feature_cols, self.scaler.mean_)},
            "scales": {col: float(s) for col, s in zip(self.scaled_feature_cols, self.scaler.scale_)},
        }

        def apply_transform(df_split: pd.DataFrame) -> pd.DataFrame:
            out = df_split.copy()
            X = out[self.scaled_feature_cols].fillna(0.0).to_numpy()
            scaled = self.scaler.transform(X)
            for i, col in enumerate(self.scaled_feature_cols):
                out[f"{col}_scaled"] = scaled[:, i]
            return out

        df_train_scaled = apply_transform(df_train)
        df_val_scaled = apply_transform(df_val)
        df_test_scaled = apply_transform(df_test)

        return df_train_scaled, df_val_scaled, df_test_scaled, scaler_params

    def validate_split_integrity(
        self,
        df_train: pd.DataFrame,
        df_val: pd.DataFrame,
        df_test: pd.DataFrame,
    ) -> Tuple[bool, List[str]]:
        """
        Checks that train, validation, and test datasets satisfy all temporal boundary invariants.
        """
        errors = []
        train_max = pd.to_datetime(df_train["date"]).max()
        val_min = pd.to_datetime(df_val["date"]).min()
        val_max = pd.to_datetime(df_val["date"]).max()
        test_min = pd.to_datetime(df_test["date"]).min()

        if train_max >= val_min:
            errors.append(f"Train max date ({train_max}) overlaps with Val min date ({val_min}).")

        if val_max >= test_min:
            errors.append(f"Val max date ({val_max}) overlaps with Test min date ({test_min}).")

        train_dates = set(pd.to_datetime(df_train["date"]).unique())
        val_dates = set(pd.to_datetime(df_val["date"]).unique())
        test_dates = set(pd.to_datetime(df_test["date"]).unique())

        if train_dates.intersection(val_dates):
            errors.append("Train and Val share overlapping calendar dates.")
        if val_dates.intersection(test_dates):
            errors.append("Val and Test share overlapping calendar dates.")
        if train_dates.intersection(test_dates):
            errors.append("Train and Test share overlapping calendar dates.")

        return len(errors) == 0, errors
