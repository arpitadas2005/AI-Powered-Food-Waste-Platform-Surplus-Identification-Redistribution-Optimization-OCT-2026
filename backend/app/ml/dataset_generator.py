"""
Synthetic Operational Supermarket History Generator for ML Pipeline Development.

Generates realistic, reproducible historical transactions (PURCHASE, POS_SALE, WASTE_DISPOSAL)
over a 365-day observation window across standardized food categories.

INCLUDES CONTROLLED ANOMALIES TO TEST DATA PROFILING AND QUALITY PIPELINES:
- Day-of-week seasonality (weekend sales boosts).
- Perishability-correlated waste events.
- Stockout periods (censored demand).
- Explicit data quality issues: missing timestamps, negative entries, unit anomalies, outlier spikes.
"""

from datetime import date, datetime, timedelta
import math
import os
import random
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np


CATEGORIES = [
    {"id": "cat_dairy", "name": "Dairy & Eggs", "shelf_life": 14, "base_waste_rate": 0.05, "base_daily_demand": 25.0},
    {"id": "cat_meat", "name": "Fresh Meat & Poultry", "shelf_life": 4, "base_waste_rate": 0.08, "base_daily_demand": 18.0},
    {"id": "cat_produce", "name": "Fresh Produce", "shelf_life": 6, "base_waste_rate": 0.07, "base_daily_demand": 40.0},
    {"id": "cat_bakery", "name": "Bakery & Bread", "shelf_life": 3, "base_waste_rate": 0.10, "base_daily_demand": 30.0},
    {"id": "cat_seafood", "name": "Fresh Seafood", "shelf_life": 3, "base_waste_rate": 0.09, "base_daily_demand": 12.0},
    {"id": "cat_deli", "name": "Prepared Foods & Deli", "shelf_life": 5, "base_waste_rate": 0.07, "base_daily_demand": 22.0},
    {"id": "cat_pantry", "name": "Pantry & Dry Goods", "shelf_life": 180, "base_waste_rate": 0.005, "base_daily_demand": 15.0},
    {"id": "cat_frozen", "name": "Frozen Foods", "shelf_life": 120, "base_waste_rate": 0.01, "base_daily_demand": 20.0},
    {"id": "cat_beverages", "name": "Beverages", "shelf_life": 90, "base_waste_rate": 0.01, "base_daily_demand": 35.0},
    {"id": "cat_snacks", "name": "Snacks & Confectionery", "shelf_life": 120, "base_waste_rate": 0.005, "base_daily_demand": 28.0},
]

PRODUCTS = [
    # Dairy
    {"sku": "DAI-MILK-01", "name": "Whole Milk 1L", "category_id": "cat_dairy", "unit": "liters", "cost": 1.40, "price": 2.29},
    {"sku": "DAI-EGGS-01", "name": "Large Grade A Eggs 12pk", "category_id": "cat_dairy", "unit": "packs", "cost": 2.50, "price": 3.99},
    # Meat
    {"sku": "MEA-BEEF-01", "name": "Ground Beef 80/20", "category_id": "cat_meat", "unit": "kg", "cost": 7.50, "price": 11.99},
    {"sku": "MEA-CHIC-01", "name": "Chicken Breast Boneless", "category_id": "cat_meat", "unit": "kg", "cost": 6.00, "price": 9.49},
    # Produce
    {"sku": "PRO-BANA-01", "name": "Cavendish Bananas", "category_id": "cat_produce", "unit": "kg", "cost": 0.80, "price": 1.49},
    {"sku": "PRO-SPIN-01", "name": "Baby Spinach 250g", "category_id": "cat_produce", "unit": "packs", "cost": 1.20, "price": 2.49},
    # Bakery
    {"sku": "BAK-SOUR-01", "name": "Artisan Sourdough Loaf", "category_id": "cat_bakery", "unit": "units", "cost": 1.80, "price": 4.50},
    {"sku": "BAK-CROI-01", "name": "Butter Croissants 4pk", "category_id": "cat_bakery", "unit": "packs", "cost": 2.00, "price": 4.99},
    # Seafood
    {"sku": "SEA-SALM-01", "name": "Atlantic Salmon Fillet", "category_id": "cat_seafood", "unit": "kg", "cost": 14.00, "price": 22.99},
    # Deli
    {"sku": "DEL-SAND-01", "name": "Roast Turkey Club Sandwich", "category_id": "cat_deli", "unit": "units", "cost": 2.80, "price": 6.99},
    # Pantry
    {"sku": "PAN-PAST-01", "name": "Organic Penne Rigate 500g", "category_id": "cat_pantry", "unit": "packs", "cost": 1.10, "price": 2.19},
    {"sku": "PAN-RICE-01", "name": "Basmati Rice 2kg", "category_id": "cat_pantry", "unit": "packs", "cost": 3.20, "price": 5.99},
    # Frozen
    {"sku": "FRO-PEAS-01", "name": "Frozen Sweet Peas 1kg", "category_id": "cat_frozen", "unit": "packs", "cost": 1.50, "price": 2.89},
    {"sku": "FRO-PIZZ-01", "name": "Four Cheese Thin Crust Pizza", "category_id": "cat_frozen", "unit": "units", "cost": 3.00, "price": 5.99},
    # Beverages
    {"sku": "BEV-OJ-01", "name": "Fresh Squeezed Orange Juice 1L", "category_id": "cat_beverages", "unit": "liters", "cost": 2.20, "price": 4.29},
    {"sku": "BEV-COLA-01", "name": "Sparkling Mineral Water 750ml", "category_id": "cat_beverages", "unit": "units", "cost": 0.90, "price": 1.99},
    # Snacks
    {"sku": "SNA-CHIP-01", "name": "Sea Salt Kettle Chips 150g", "category_id": "cat_snacks", "unit": "packs", "cost": 1.30, "price": 2.99},
    # Sparse demand products (for testing sparse time series handling)
    {"sku": "PAN-TRUF-01", "name": "White Truffle Infused Olive Oil", "category_id": "cat_pantry", "unit": "units", "cost": 18.00, "price": 34.99, "sparse": True},
    {"sku": "SEA-CAVI-01", "name": "Sturgeon Caviar Tin 50g", "category_id": "cat_seafood", "unit": "units", "cost": 45.00, "price": 89.99, "sparse": True},
]


def generate_synthetic_supermarket_dataset(
    start_date: date = date(2025, 10, 24),
    num_days: int = 365,
    seed: int = 42,
    tenant_id: str = "tenant-greengrocer-01",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate synthetic daily inventory balances and granular transactional events.
    
    Returns:
        (df_daily_observations, df_granular_transactions)
    """
    random.seed(seed)
    np.random.seed(seed)

    cat_map = {c["id"]: c for c in CATEGORIES}
    
    transactions: List[Dict] = []
    daily_records: List[Dict] = []

    tx_counter = 100000

    for prod in PRODUCTS:
        cat = cat_map[prod["category_id"]]
        sku = prod["sku"]
        unit = prod["unit"]
        is_sparse = prod.get("sparse", False)

        current_stock = 60.0 if not is_sparse else 5.0
        reorder_point = 25.0 if not is_sparse else 2.0
        reorder_quantity = 80.0 if not is_sparse else 6.0
        shelf_life = cat["shelf_life"]
        base_demand = cat["base_daily_demand"] * 0.7 if not is_sparse else 0.08
        base_waste_rate = cat["base_waste_rate"]

        for day_idx in range(num_days):
            current_date = start_date + timedelta(days=day_idx)
            day_of_week = current_date.weekday()  # 0=Monday, 6=Sunday

            # Day-of-week demand multiplier: Friday(4), Saturday(5), Sunday(6) are higher
            dow_multiplier = {
                0: 0.85, 1: 0.90, 2: 0.95, 3: 1.05, 4: 1.35, 5: 1.50, 6: 1.25
            }[day_of_week]

            # Seasonal trend: sine wave simulating annual peak during holidays (Nov-Dec)
            day_of_year = current_date.timetuple().tm_yday
            seasonal_multiplier = 1.0 + 0.15 * math.sin(2 * math.pi * (day_of_year - 60) / 365.0)

            # Restocking logic (PURCHASE)
            opening_stock = current_stock
            restock_qty = 0.0
            if current_stock <= reorder_point:
                restock_qty = reorder_quantity
                tx_counter += 1
                transactions.append({
                    "transaction_id": f"TX-{tx_counter}",
                    "timestamp": datetime.combine(current_date, datetime.min.time().replace(hour=7, minute=15)),
                    "tenant_id": tenant_id,
                    "sku": sku,
                    "product_name": prod["name"],
                    "category_id": cat["id"],
                    "transaction_type": "PURCHASE",
                    "quantity_change": restock_qty,
                    "quantity_before": current_stock,
                    "quantity_after": current_stock + restock_qty,
                    "unit": unit,
                    "unit_cost": prod["cost"],
                    "reason": "SCHEDULED_RESTOCK",
                })
                current_stock += restock_qty

            # True customer latent demand vs recorded sales (stockout truncation)
            if is_sparse:
                latent_demand = 1.0 if random.random() < base_demand else 0.0
            else:
                noise = np.random.normal(0, base_demand * 0.18)
                raw_demand = (base_demand * dow_multiplier * seasonal_multiplier) + noise
                latent_demand = max(0.0, round(raw_demand, 2))

            # Outlier demand injection for profiling (1 sudden spike in Bananas and Whole Milk)
            if sku == "PRO-BANA-01" and day_idx == 112:
                latent_demand = 145.0  # Massive community event spike
            elif sku == "DAI-MILK-01" and day_idx == 204:
                latent_demand = 95.0

            # Actual recorded sales (cannot exceed available stock)
            recorded_sales = min(current_stock, latent_demand)
            is_stockout = (latent_demand > current_stock) and (current_stock == 0.0)

            if recorded_sales > 0:
                tx_counter += 1
                transactions.append({
                    "transaction_id": f"TX-{tx_counter}",
                    "timestamp": datetime.combine(current_date, datetime.min.time().replace(hour=14, minute=30)),
                    "tenant_id": tenant_id,
                    "sku": sku,
                    "product_name": prod["name"],
                    "category_id": cat["id"],
                    "transaction_type": "POS_SALE",
                    "quantity_change": -recorded_sales,
                    "quantity_before": current_stock,
                    "quantity_after": current_stock - recorded_sales,
                    "unit": unit,
                    "unit_cost": prod["cost"],
                    "selling_price": prod["price"],
                    "reason": "CUSTOMER_PURCHASE",
                })
                current_stock -= recorded_sales

            # Expiry waste generation (WASTE_DISPOSAL)
            waste_qty = 0.0
            # Higher probability of waste if item is highly perishable and stock remained high
            if shelf_life <= 7 and current_stock > 10.0:
                if random.random() < 0.25:
                    waste_qty = round(min(current_stock * base_waste_rate, current_stock), 2)
            elif random.random() < 0.04 and current_stock > 0:
                waste_qty = round(min(current_stock * base_waste_rate, current_stock), 2)

            if waste_qty > 0.0:
                tx_counter += 1
                transactions.append({
                    "transaction_id": f"TX-{tx_counter}",
                    "timestamp": datetime.combine(current_date, datetime.min.time().replace(hour=21, minute=45)),
                    "tenant_id": tenant_id,
                    "sku": sku,
                    "product_name": prod["name"],
                    "category_id": cat["id"],
                    "transaction_type": "WASTE_DISPOSAL",
                    "quantity_change": -waste_qty,
                    "quantity_before": current_stock,
                    "quantity_after": current_stock - waste_qty,
                    "unit": unit,
                    "unit_cost": prod["cost"],
                    "reason": "EXPIRED_ON_SHELF",
                })
                current_stock -= waste_qty

            closing_stock = round(current_stock, 2)

            daily_records.append({
                "date": current_date.isoformat(),
                "tenant_id": tenant_id,
                "sku": sku,
                "product_name": prod["name"],
                "category_id": cat["id"],
                "category_name": cat["name"],
                "unit": unit,
                "opening_stock": opening_stock,
                "restock_quantity": restock_qty,
                "recorded_sales": recorded_sales,
                "latent_demand": latent_demand,
                "waste_quantity": waste_qty,
                "closing_stock": closing_stock,
                "is_stockout": is_stockout,
                "unit_cost": prod["cost"],
                "selling_price": prod["price"],
                "shelf_life_days": shelf_life,
            })

    df_daily = pd.DataFrame(daily_records)
    df_tx = pd.DataFrame(transactions)

    # Inject controlled anomalies into df_tx to verify data-profiler detection
    # 1. Missing timestamp (3 rows)
    df_tx.loc[12, "timestamp"] = np.nan
    df_tx.loc[154, "timestamp"] = np.nan
    df_tx.loc[320, "timestamp"] = np.nan

    # 2. Negative sales quantity anomaly (data entry glitch: positive change on POS_SALE)
    df_tx.loc[45, "quantity_change"] = 5.0  # Erroneous positive sign for POS_SALE

    # 3. Incompatible unit (e.g. lbs instead of kg)
    df_tx.loc[88, "unit"] = "lbs"
    df_tx.loc[210, "unit"] = "oz"

    # 4. Duplicate transaction_id
    dup_row = df_tx.iloc[100].copy()
    df_tx = pd.concat([df_tx, pd.DataFrame([dup_row])], ignore_index=True)

    return df_daily, df_tx


def save_synthetic_dataset(output_dir: str = "data"):
    """Generate and persist the benchmark dataset to disk with provenance metadata."""
    os.makedirs(output_dir, exist_ok=True)
    df_daily, df_tx = generate_synthetic_supermarket_dataset()

    daily_path = os.path.join(output_dir, "synthetic_daily_supermarket_history.csv")
    tx_path = os.path.join(output_dir, "synthetic_transactions_supermarket_history.csv")

    df_daily.to_csv(daily_path, index=False)
    df_tx.to_csv(tx_path, index=False)

    print(f"Generated synthetic supermarket history:")
    print(f"  Daily Observations : {daily_path} ({len(df_daily):,} rows, {len(df_daily.columns)} cols)")
    print(f"  Granular Events    : {tx_path} ({len(df_tx):,} rows, {len(df_tx.columns)} cols)")
    return daily_path, tx_path


if __name__ == "__main__":
    save_synthetic_dataset()
