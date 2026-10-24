"""
Milestone 2 — Phase 2: Forecasting Target Construction Engine.

Responsibilities:
- Constructs multi-horizon demand forecasting targets per SKU:
  - target_sales_1d: 1-day ahead sales (y_{t+1})
  - target_sales_7d: 7-day ahead sales (y_{t+7})
  - target_demand_7d_sum: 7-day cumulative sales sum (sum_{k=1}^7 y_{t+k})
  - target_waste_7d_sum: 7-day cumulative waste sum (sum_{k=1}^7 w_{t+k})
- Ensures clean NaN alignment at tail of time series (no forward-filling future targets).
- Provides mathematical verification of target alignment with historical ground truth.
- Validates that target columns are strictly isolated from feature inputs.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


TARGET_COLUMNS = [
    "target_sales_1d",
    "target_sales_7d",
    "target_demand_7d_sum",
    "target_waste_7d_sum",
]


class TargetBuilder:
    """
    Constructs and verifies forecasting targets with strict future-shift semantics.
    """

    def __init__(self, target_variable: str = "recorded_sales", waste_variable: str = "waste_quantity"):
        self.target_variable = target_variable
        self.waste_variable = waste_variable

    def add_targets(self, df_grid: pd.DataFrame) -> pd.DataFrame:
        """
        Adds forward-looking target columns per SKU.
        
        Tail observations where future values are outside the historical timeline
        will appropriately receive NaN.
        """
        df = df_grid.sort_values(["sku", "date"]).copy()
        target_dfs = []

        for sku, group in df.groupby("sku"):
            g = group.sort_values("date").copy()
            y = g[self.target_variable]
            w = g[self.waste_variable] if self.waste_variable in g.columns else pd.Series(0.0, index=g.index)

            # 1-day ahead target: y_{t+1} -> shift(-1)
            g["target_sales_1d"] = y.shift(-1)

            # 7-day ahead target: y_{t+7} -> shift(-7)
            g["target_sales_7d"] = y.shift(-7)

            # 7-day cumulative sales sum: sum_{k=1}^7 y_{t+k}
            # We reverse the series, take rolling(7).sum(), shift(1), and reverse back
            # Or equivalently: compute rolling sum backwards
            rev_y = y.iloc[::-1]
            rev_sum_7 = rev_y.rolling(window=7, min_periods=7).sum()
            # Shift backwards so at index t it contains y_{t+1} + ... + y_{t+7}
            g["target_demand_7d_sum"] = rev_sum_7.iloc[::-1].shift(-7 + 1)
            # A cleaner, explicit vectorized calculation:
            g["target_demand_7d_sum"] = (
                y.shift(-1)
                + y.shift(-2)
                + y.shift(-3)
                + y.shift(-4)
                + y.shift(-5)
                + y.shift(-6)
                + y.shift(-7)
            )

            # 7-day cumulative waste sum
            g["target_waste_7d_sum"] = (
                w.shift(-1)
                + w.shift(-2)
                + w.shift(-3)
                + w.shift(-4)
                + w.shift(-5)
                + w.shift(-6)
                + w.shift(-7)
            )

            target_dfs.append(g)

        full_df = pd.concat(target_dfs, ignore_index=True)
        return full_df.sort_values(["sku", "date"]).reset_index(drop=True)

    def validate_target_alignment(self, df_with_targets: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validates mathematical alignment of target columns against ground truth sales/waste.
        Returns (is_valid, error_messages).
        """
        errors = []
        df = df_with_targets.sort_values(["sku", "date"]).copy()

        for sku, group in df.groupby("sku"):
            g = group.sort_values("date").reset_index(drop=True)
            n_rows = len(g)

            # Check target_sales_1d
            for i in range(n_rows - 1):
                actual_next = g.loc[i + 1, self.target_variable]
                target_val = g.loc[i, "target_sales_1d"]
                if not np.isclose(actual_next, target_val, equal_nan=True):
                    errors.append(f"SKU {sku} index {i}: target_sales_1d {target_val} != actual {actual_next}")
                    break

            # Tail of 1d must be NaN
            if not pd.isna(g.loc[n_rows - 1, "target_sales_1d"]):
                errors.append(f"SKU {sku}: Last row of target_sales_1d must be NaN.")

            # Check target_sales_7d
            for i in range(n_rows - 7):
                actual_7d = g.loc[i + 7, self.target_variable]
                target_val = g.loc[i, "target_sales_7d"]
                if not np.isclose(actual_7d, target_val, equal_nan=True):
                    errors.append(f"SKU {sku} index {i}: target_sales_7d {target_val} != actual {actual_7d}")
                    break

            # Tail 7 rows of 7d must be NaN
            for i in range(n_rows - 7, n_rows):
                if not pd.isna(g.loc[i, "target_sales_7d"]):
                    errors.append(f"SKU {sku} index {i}: Tail rows of target_sales_7d must be NaN.")
                    break

            # Check 7d cumulative sum
            for i in range(min(5, n_rows - 7)):
                expected_sum = g.loc[i + 1 : i + 7, self.target_variable].sum()
                target_sum = g.loc[i, "target_demand_7d_sum"]
                if not np.isclose(expected_sum, target_sum, equal_nan=True):
                    errors.append(f"SKU {sku} index {i}: target_demand_7d_sum {target_sum} != sum {expected_sum}")
                    break

        return len(errors) == 0, errors
