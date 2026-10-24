"""
Milestone 2 — Phase 2: Time Series Resampling & Continuous Grid Engine.

Responsibilities:
- Builds continuous, gap-free calendar date grids for each SKU.
- Aggregates cleaned transactional events into daily totals.
- Imputes unobserved calendar dates (zero sales/waste, forward-filled stock).
- Tracks stockout censoring indicators.
- Validates minimum observation history thresholds (minimum 28 days).
- Implements Syntetos-Boylan demand pattern classification (Smooth, Erratic, Intermittent, Lumpy).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class TimeSeriesPreparer:
    """
    Constructs unbroken chronological daily series and evaluates demand structure.
    """

    def __init__(self, min_history_days: int = 28):
        self.min_history_days = min_history_days

    def aggregate_transactions_to_daily(
        self,
        df_tx: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Aggregate cleaned transactions to (tenant_id, sku, date) daily observation level.
        """
        df = df_tx.copy()
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date

        # Group by tenant_id, sku, date
        records = []
        for (tenant_id, sku), group in df.groupby(["tenant_id", "sku"]):
            for d, d_group in group.groupby("date"):
                # Sales: POS_SALE (quantity_change is negative, convert to positive volume)
                sales_mask = d_group["transaction_type"] == "POS_SALE"
                sales_qty = float(d_group.loc[sales_mask, "quantity_change"].abs().sum())

                # Restock: PURCHASE or RESTOCK (positive volume)
                restock_mask = d_group["transaction_type"].isin(["PURCHASE", "RESTOCK"])
                restock_qty = float(d_group.loc[restock_mask, "quantity_change"].sum())

                # Waste: WASTE_DISPOSAL (quantity_change is negative, convert to positive volume)
                waste_mask = d_group["transaction_type"] == "WASTE_DISPOSAL"
                waste_qty = float(d_group.loc[waste_mask, "quantity_change"].abs().sum())

                # Last known stock of the day
                latest_tx = d_group.sort_values("timestamp").iloc[-1]
                closing_stock = float(latest_tx.get("quantity_after", 0.0))
                opening_stock = float(d_group.sort_values("timestamp").iloc[0].get("quantity_before", 0.0))

                records.append({
                    "date": pd.to_datetime(d),
                    "tenant_id": tenant_id,
                    "sku": sku,
                    "product_name": latest_tx.get("product_name", sku),
                    "category_id": latest_tx.get("category_id", "unknown"),
                    "unit": latest_tx.get("unit", "units"),
                    "opening_stock": opening_stock,
                    "restock_quantity": restock_qty,
                    "recorded_sales": sales_qty,
                    "waste_quantity": waste_qty,
                    "closing_stock": closing_stock,
                    "is_stockout": bool(closing_stock <= 0.0),
                    "unit_cost": float(latest_tx.get("unit_cost", 0.0)),
                    "selling_price": float(latest_tx.get("selling_price", 0.0)),
                })

        return pd.DataFrame(records)

    def build_daily_grid(
        self,
        df_daily: pd.DataFrame,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Constructs an unbroken calendar grid from min_date to max_date for every SKU.
        Unobserved dates are imputed with:
        - recorded_sales = 0.0
        - restock_quantity = 0.0
        - waste_quantity = 0.0
        - closing_stock = forward-filled from prior day
        - is_stockout = True if forward-filled closing_stock <= 0
        """
        df = df_daily.copy()
        df["date"] = pd.to_datetime(df["date"])

        min_d = pd.to_datetime(start_date) if start_date else df["date"].min()
        max_d = pd.to_datetime(end_date) if end_date else df["date"].max()
        full_dates = pd.date_range(min_d, max_d, freq="D", name="date")

        grid_list = []
        for sku, group in df.groupby("sku"):
            group_sorted = group.sort_values("date").drop_duplicates(subset=["date"])
            reindexed = group_sorted.set_index("date").reindex(full_dates)

            # Metadata forward/backward fills
            reindexed["sku"] = sku
            reindexed["tenant_id"] = reindexed["tenant_id"].ffill().bfill()
            reindexed["product_name"] = reindexed["product_name"].ffill().bfill()
            reindexed["category_id"] = reindexed["category_id"].ffill().bfill()
            if "category_name" in reindexed.columns:
                reindexed["category_name"] = reindexed["category_name"].ffill().bfill()
            reindexed["unit"] = reindexed["unit"].ffill().bfill()
            if "shelf_life_days" in reindexed.columns:
                reindexed["shelf_life_days"] = reindexed["shelf_life_days"].ffill().bfill()

            # Economic values forward/backward fill or default
            if "unit_cost" in reindexed.columns:
                reindexed["unit_cost"] = reindexed["unit_cost"].ffill().bfill().fillna(0.0)
            else:
                reindexed["unit_cost"] = 0.0

            if "selling_price" in reindexed.columns:
                reindexed["selling_price"] = reindexed["selling_price"].ffill().bfill().fillna(0.0)
            else:
                reindexed["selling_price"] = 0.0

            # Activity values: unobserved days had zero sales/restock/waste
            reindexed["recorded_sales"] = reindexed["recorded_sales"].fillna(0.0)
            if "restock_quantity" in reindexed.columns:
                reindexed["restock_quantity"] = reindexed["restock_quantity"].fillna(0.0)
            else:
                reindexed["restock_quantity"] = 0.0

            if "waste_quantity" in reindexed.columns:
                reindexed["waste_quantity"] = reindexed["waste_quantity"].fillna(0.0)
            else:
                reindexed["waste_quantity"] = 0.0

            # Inventory stock: forward-fill
            reindexed["closing_stock"] = reindexed["closing_stock"].ffill().fillna(0.0)
            if "opening_stock" in reindexed.columns:
                reindexed["opening_stock"] = reindexed["opening_stock"].fillna(reindexed["closing_stock"])
            else:
                reindexed["opening_stock"] = reindexed["closing_stock"]
            reindexed["is_stockout"] = reindexed["closing_stock"] <= 0.0

            # If latent_demand was present in raw data, preserve it or fallback to recorded_sales
            if "latent_demand" in reindexed.columns:
                reindexed["latent_demand"] = reindexed["latent_demand"].fillna(reindexed["recorded_sales"])

            grid_list.append(reindexed.reset_index())

        full_grid = pd.concat(grid_list, ignore_index=True)
        return full_grid.sort_values(["sku", "date"]).reset_index(drop=True)

    def validate_minimum_history(
        self,
        df_grid: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, Dict[str, str]]:
        """
        Validates whether each SKU possesses sufficient observation history (>= min_history_days).
        Flags SKUs with insufficient history without silently dropping data.
        """
        history_status: Dict[str, str] = {}
        df = df_grid.copy()
        df["history_status"] = "SUFFICIENT_HISTORY"

        for sku, group in df.groupby("sku"):
            n_days = len(group["date"].unique())
            if n_days < self.min_history_days:
                status = f"INSUFFICIENT_HISTORY_{n_days}_DAYS"
                history_status[sku] = status
                df.loc[df["sku"] == sku, "history_status"] = status
            else:
                history_status[sku] = "SUFFICIENT_HISTORY"

        return df, history_status

    def classify_demand_patterns(
        self,
        df_grid: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Applies Syntetos-Boylan demand classification to each SKU:
        - ADI (Average Demand Interval): periods / non-zero periods
        - CV^2 (Squared Coefficient of Variation): (std / mean)^2 of non-zero demand
        
        Quadrants:
        - ADI < 1.32 & CV^2 < 0.49  => SMOOTH
        - ADI < 1.32 & CV^2 >= 0.49 => ERRATIC
        - ADI >= 1.32 & CV^2 < 0.49 => INTERMITTENT
        - ADI >= 1.32 & CV^2 >= 0.49 => LUMPY
        """
        df = df_grid.copy()
        df["demand_pattern"] = "UNKNOWN"
        df["adi"] = 0.0
        df["cv2"] = 0.0

        for sku, group in df.groupby("sku"):
            sales = group["recorded_sales"].to_numpy()
            non_zero_indices = np.where(sales > 0)[0]
            non_zero_count = len(non_zero_indices)
            total_periods = len(sales)

            if non_zero_count == 0:
                pattern = "INTERMITTENT"
                adi = float(total_periods)
                cv2 = 0.0
            elif non_zero_count == 1:
                pattern = "INTERMITTENT"
                adi = float(total_periods)
                cv2 = 0.0
            else:
                adi = total_periods / non_zero_count
                non_zero_values = sales[non_zero_indices]
                mean_val = np.mean(non_zero_values)
                std_val = np.std(non_zero_values, ddof=1) if len(non_zero_values) > 1 else 0.0
                cv2 = (std_val / mean_val) ** 2 if mean_val > 0 else 0.0

                if adi < 1.32 and cv2 < 0.49:
                    pattern = "SMOOTH"
                elif adi < 1.32 and cv2 >= 0.49:
                    pattern = "ERRATIC"
                elif adi >= 1.32 and cv2 < 0.49:
                    pattern = "INTERMITTENT"
                else:
                    pattern = "LUMPY"

            df.loc[df["sku"] == sku, "demand_pattern"] = pattern
            df.loc[df["sku"] == sku, "adi"] = round(adi, 3)
            df.loc[df["sku"] == sku, "cv2"] = round(cv2, 3)

        return df
