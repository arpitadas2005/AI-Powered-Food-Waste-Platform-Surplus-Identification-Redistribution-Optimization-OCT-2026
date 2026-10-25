"""
Milestone 2 — Phase 4: Configurable Waste-Risk Rules and Heuristic Parameters.

Defines:
- Risk Categories: LOW, MEDIUM, HIGH, CRITICAL
- Thresholds combining shelf-life urgency (days_to_expiry) and surplus volume (surplus_ratio, expected_surplus)
- Action mappings for retail discounting and food-bank donation dispatch
- Limitations and heuristic calibration documentation
"""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class RiskThresholds:
    """Configurable boundaries for waste-risk classification."""
    # Critical risk: Immediate loss imminent within 48-72h with surplus
    CRITICAL_DAYS_THRESHOLD: float = 2.0
    CRITICAL_SURPLUS_RATIO: float = 0.20

    # High risk: Imminent loss within 5 days with significant surplus
    HIGH_DAYS_THRESHOLD: float = 5.0
    HIGH_SURPLUS_RATIO: float = 0.25

    # Medium risk: Moderate shelf life remaining with noticeable surplus
    MEDIUM_DAYS_THRESHOLD: float = 10.0
    MEDIUM_SURPLUS_RATIO: float = 0.15

    # Minimum surplus volume to trigger above LOW (avoids flagging rounding dust)
    MIN_SURPLUS_UNITS: float = 0.50


# Reorder policy defaults
@dataclass(frozen=True)
class ReorderPolicyDefaults:
    DEFAULT_LEAD_TIME_DAYS: int = 2
    SERVICE_LEVEL_Z: float = 1.65  # 95% service level
    DEFAULT_DAILY_DEMAND_STD: float = 2.0
    REVIEW_PERIOD_DAYS: int = 7  # Weekly review cover
    MAX_STORAGE_FACTOR: float = 3.0  # Max inventory cannot exceed 3x weekly demand


def classify_waste_risk(
    days_to_expiry: float,
    current_stock: float,
    expected_surplus: float,
    surplus_ratio: float,
    thresholds: RiskThresholds = RiskThresholds(),
) -> Tuple[str, str]:
    """
    Evaluates combined urgency and surplus volume to assign risk tier and recommended action.
    
    Returns:
        (risk_tier, recommended_action)
    """
    if current_stock <= 0.0 or expected_surplus < thresholds.MIN_SURPLUS_UNITS:
        return "LOW", "NORMAL_RETAIL_OPERATIONS"

    # CRITICAL: Expiry imminent (<= 2 days) with actionable surplus
    if days_to_expiry <= thresholds.CRITICAL_DAYS_THRESHOLD and surplus_ratio >= thresholds.CRITICAL_SURPLUS_RATIO:
        return "CRITICAL", "DISPATCH_DONATION_OR_DEEP_MARKDOWN"

    # HIGH: Expiry within 5 days with substantial surplus (>= 25%)
    if days_to_expiry <= thresholds.HIGH_DAYS_THRESHOLD and surplus_ratio >= thresholds.HIGH_SURPLUS_RATIO:
        return "HIGH", "PROMOTIONAL_MARKDOWN_OR_SURPLUS_LISTING"

    # Critical fallback: Extremely high surplus ratio (>= 60%) even up to 3.5 days
    if days_to_expiry <= 3.5 and surplus_ratio >= 0.60:
        return "CRITICAL", "DISPATCH_DONATION_OR_DEEP_MARKDOWN"

    # MEDIUM: Moderate shelf life (<= 10 days) with moderate surplus (>= 15%)
    if days_to_expiry <= thresholds.MEDIUM_DAYS_THRESHOLD and surplus_ratio >= thresholds.MEDIUM_SURPLUS_RATIO:
        return "MEDIUM", "ROTATE_STOCK_AND_MONITOR_VELOCITY"

    # High surplus fallback for medium horizon
    if days_to_expiry <= 14.0 and surplus_ratio >= 0.50:
        return "MEDIUM", "ROTATE_STOCK_AND_MONITOR_VELOCITY"

    return "LOW", "NORMAL_RETAIL_OPERATIONS"
