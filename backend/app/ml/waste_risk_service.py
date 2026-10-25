"""
Milestone 2 — Phase 4: Waste-Risk Assessment Engine.

Integrates real-time inventory balances, lot-level expiration dates,
surplus listing reservations, and ML demand forecasts to quantify perishable food waste risk.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session
import zoneinfo

from backend.app.models.inventory import InventoryItem, InventoryStatus
from backend.app.models.surplus import SurplusListing, SurplusStatus
from backend.app.models.waste_risk import RiskTier, WasteRiskAssessmentRecord
from backend.app.ml.inference_service import InferenceService, get_inference_service
from backend.app.ml.risk_rules import classify_waste_risk, RiskThresholds


class WasteRiskService:
    """
    Evaluates perishable stock surplus probability and financial exposure.
    """

    def __init__(self, inference_service: Optional[InferenceService] = None):
        self.inference_service = inference_service or get_inference_service()

    def calculate_item_days_to_expiry(self, item: InventoryItem, tenant_timezone: str = "UTC") -> float:
        """Computes remaining calendar days until expiration anchored to tenant timezone."""
        try:
            tz = zoneinfo.ZoneInfo(tenant_timezone)
        except Exception:
            tz = zoneinfo.ZoneInfo("UTC")

        today_local = datetime.now(tz).date()
        if not item.expiry_date:
            return 14.0  # Safe default if expiry_date is null
        delta = (item.expiry_date - today_local).days
        return max(0.0, float(delta))

    def get_reserved_surplus_quantity(self, item_id: str, db: Session) -> float:
        """Computes inventory quantity already earmarked for donation/redistribution."""
        reserved_statuses = [SurplusStatus.AVAILABLE.value, SurplusStatus.RESERVED.value, SurplusStatus.CLAIMED.value]
        result = (
            db.query(func.sum(SurplusListing.quantity))
            .filter(
                SurplusListing.item_id == item_id,
                SurplusListing.status.in_(reserved_statuses),
            )
            .scalar()
        )
        return float(result) if result else 0.0

    def evaluate_item_risk(
        self,
        item: InventoryItem,
        db: Session,
        persist: bool = False,
        tenant_timezone: Optional[str] = None,
    ) -> WasteRiskAssessmentRecord:
        """
        Evaluates potential surplus and assigns an explainable waste risk classification.
        """
        tz_name = tenant_timezone or (item.tenant.timezone if item.tenant else "UTC")
        days_to_expiry = self.calculate_item_days_to_expiry(item, tz_name)
        reserved_qty = self.get_reserved_surplus_quantity(item.id, db)

        # Net physical stock available for normal retail sales
        available_stock = max(0.0, float(item.current_quantity) - reserved_qty)
        unit_cost = float(item.cost_per_unit)

        # Predict cumulative sales expected before expiry date
        sku_key = item.sku or item.name
        predicted_demand = self.inference_service.predict_demand_over_window(
            sku=sku_key,
            days_ahead=days_to_expiry,
        )

        # Compute surplus metrics
        expected_surplus = max(0.0, available_stock - predicted_demand)
        surplus_ratio = round(expected_surplus / available_stock, 3) if available_stock > 0 else 0.0
        value_at_risk = round(expected_surplus * unit_cost, 2)

        # Assign risk tier and recommended action
        risk_tier, action = classify_waste_risk(
            days_to_expiry=days_to_expiry,
            current_stock=available_stock,
            expected_surplus=expected_surplus,
            surplus_ratio=surplus_ratio,
        )

        health = self.inference_service.get_health_status()
        model_name = "RandomForestForecaster" if not health["is_using_fallback"] else "SeasonalNaiveBaseline"

        assessment = WasteRiskAssessmentRecord(
            tenant_id=item.tenant_id,
            item_id=item.id,
            sku=item.sku,
            current_stock=round(available_stock, 2),
            days_to_expiry=round(days_to_expiry, 1),
            predicted_demand_to_expiry=round(predicted_demand, 2),
            expected_surplus_units=round(expected_surplus, 2),
            surplus_ratio=surplus_ratio,
            unit_cost=round(unit_cost, 2),
            value_at_risk=value_at_risk,
            risk_tier=risk_tier,
            recommended_action=action,
            model_name=model_name,
            model_version="2.0.0-phase4",
            assessed_at=datetime.now(timezone.utc),
        )

        if persist:
            db.add(assessment)
            db.commit()
            db.refresh(assessment)

        return assessment

    def list_active_risk_alerts(
        self,
        tenant_id: str,
        db: Session,
        min_tier: str = "HIGH",
    ) -> List[Dict[str, Any]]:
        """
        Scans all active inventory items for a tenant and returns items matching min_tier.
        """
        items = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.is_active == True,
                InventoryItem.current_quantity > 0,
            )
            .all()
        )

        target_tiers = ["CRITICAL"] if min_tier == "CRITICAL" else ["HIGH", "CRITICAL"] if min_tier == "HIGH" else ["MEDIUM", "HIGH", "CRITICAL"]

        alerts = []
        for item in items:
            assessment = self.evaluate_item_risk(item, db, persist=False)
            if assessment.risk_tier in target_tiers:
                alerts.append({
                    "item_id": item.id,
                    "sku": item.sku,
                    "product_name": item.name,
                    "unit": item.unit,
                    "current_stock": assessment.current_stock,
                    "days_to_expiry": assessment.days_to_expiry,
                    "predicted_demand_to_expiry": assessment.predicted_demand_to_expiry,
                    "expected_surplus": assessment.expected_surplus_units,
                    "surplus_ratio": assessment.surplus_ratio,
                    "value_at_risk": assessment.value_at_risk,
                    "risk_tier": assessment.risk_tier,
                    "recommended_action": assessment.recommended_action,
                    "expiry_date": str(item.expiry_date),
                })

        # Sort by urgency: CRITICAL first, then highest value at risk
        alerts.sort(key=lambda a: (0 if a["risk_tier"] == "CRITICAL" else 1, -a["value_at_risk"]))
        return alerts
