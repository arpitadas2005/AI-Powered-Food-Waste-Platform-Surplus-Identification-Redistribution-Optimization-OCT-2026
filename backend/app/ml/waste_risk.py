"""
Waste Risk Assessment and Replenishment Calculation Engine.

FORMULAS AND CONTRACTS:
1. Expected Surplus = max(0, Current Stock - Cumulative Predicted Demand before Expiry)
2. Surplus Risk Ratio = Expected Surplus / Current Stock
3. Potential Value at Risk = Expected Surplus * Cost per Unit
4. Reorder Point (ROP) = (Daily Forecast * Lead Time) + Safety Stock
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass
class WasteRiskAssessment:
    sku: str
    product_name: str
    current_stock: float
    days_to_expiry: float
    predicted_demand_before_expiry: float
    expected_surplus_units: float
    surplus_ratio: float
    unit_cost: float
    value_at_risk: float
    risk_tier: str  # HIGH, MEDIUM, LOW
    recommended_action: str


def compute_waste_risk(
    sku: str,
    product_name: str,
    current_stock: float,
    days_to_expiry: float,
    predicted_demand_before_expiry: float,
    unit_cost: float,
) -> WasteRiskAssessment:
    """
    Compute explainable waste risk metric based on current stock vs forecast demand before expiration.
    """
    if current_stock <= 0.0:
        return WasteRiskAssessment(
            sku=sku,
            product_name=product_name,
            current_stock=0.0,
            days_to_expiry=days_to_expiry,
            predicted_demand_before_expiry=predicted_demand_before_expiry,
            expected_surplus_units=0.0,
            surplus_ratio=0.0,
            unit_cost=unit_cost,
            value_at_risk=0.0,
            risk_tier="NONE",
            recommended_action="MONITOR",
        )

    expected_surplus = max(0.0, current_stock - predicted_demand_before_expiry)
    surplus_ratio = expected_surplus / current_stock
    value_at_risk = round(expected_surplus * unit_cost, 2)

    # Explainable Risk Classification (Operational heuristic, not arbitrary)
    if days_to_expiry <= 2.0 and surplus_ratio > 0.3:
        risk_tier = "HIGH"
        action = "DISCOUNT_IMMEDIATELY_OR_PREPARE_DONATION"
    elif days_to_expiry <= 5.0 and surplus_ratio > 0.15:
        risk_tier = "MEDIUM"
        action = "FLAG_FOR_PROMOTIONAL_DISCOUNT"
    elif expected_surplus > 0:
        risk_tier = "LOW"
        action = "MONITOR_DEMAND_VELOCITY"
    else:
        risk_tier = "NEGLIGIBLE"
        action = "NORMAL_OPERATIONS"

    return WasteRiskAssessment(
        sku=sku,
        product_name=product_name,
        current_stock=round(current_stock, 2),
        days_to_expiry=round(days_to_expiry, 1),
        predicted_demand_before_expiry=round(predicted_demand_before_expiry, 2),
        expected_surplus_units=round(expected_surplus, 2),
        surplus_ratio=round(surplus_ratio, 3),
        unit_cost=round(unit_cost, 2),
        value_at_risk=value_at_risk,
        risk_tier=risk_tier,
        recommended_action=action,
    )


def compute_reorder_recommendation(
    current_stock: float,
    predicted_daily_demand: float,
    lead_time_days: int = 3,
    service_level_z: float = 1.65,  # 95% service level
    demand_std_dev: float = 2.0,
    target_cover_days: int = 7,
    in_transit_quantity: float = 0.0,
) -> Dict[str, float]:
    """
    Calculate statistical reorder point and recommended replenishment order quantity.
    """
    lead_time_demand = predicted_daily_demand * lead_time_days
    safety_stock = service_level_z * demand_std_dev * np.sqrt(lead_time_days)
    reorder_point = lead_time_demand + safety_stock

    target_stock = (predicted_daily_demand * target_cover_days) + safety_stock
    effective_inventory = current_stock + in_transit_quantity

    recommended_order = max(0.0, target_stock - effective_inventory)

    return {
        "predicted_daily_demand": round(predicted_daily_demand, 2),
        "lead_time_days": lead_time_days,
        "safety_stock": round(safety_stock, 2),
        "reorder_point": round(reorder_point, 2),
        "current_effective_stock": round(effective_inventory, 2),
        "is_reorder_triggered": bool(effective_inventory <= reorder_point),
        "recommended_order_quantity": round(recommended_order, 2),
    }
