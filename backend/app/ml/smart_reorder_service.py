"""
Milestone 2 — Phase 4: Smart Replenishment & Reorder Recommendation Service.

Calculates:
- Lead-time demand: D_lead = daily_demand * lead_time_days
- Dynamic safety stock: SS = Z * sqrt(lead_time_days) * demand_std
- Reorder Point: ROP = D_lead + SS
- Target replenishment stock: S = D_lead + SS + review_period_demand
- Storage capacity constraints
- Expiry risk guard: Blocks reorders for items with imminent expiration surplus
"""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.inventory import InventoryItem
from backend.app.models.surplus import SurplusListing, SurplusStatus
from backend.app.models.waste_risk import SmartReorderRecord, ReorderStatus
from backend.app.ml.inference_service import InferenceService, get_inference_service
from backend.app.ml.waste_risk_service import WasteRiskService
from backend.app.ml.risk_rules import ReorderPolicyDefaults


class SmartReorderService:
    """
    Evaluates dynamic inventory replenishment points and issues safe,
    expiry-aware purchase order recommendations.
    """

    def __init__(
        self,
        inference_service: Optional[InferenceService] = None,
        waste_risk_service: Optional[WasteRiskService] = None,
        defaults: ReorderPolicyDefaults = ReorderPolicyDefaults(),
    ):
        self.inference_service = inference_service or get_inference_service()
        self.waste_risk_service = waste_risk_service or WasteRiskService(self.inference_service)
        self.defaults = defaults

    def generate_reorder_recommendation(
        self,
        item: InventoryItem,
        db: Session,
        lead_time_days: Optional[int] = None,
        persist: bool = False,
    ) -> SmartReorderRecord:
        """
        Calculates dynamic safety stock and recommends purchase replenishment volume.
        """
        lead_time = lead_time_days or self.defaults.DEFAULT_LEAD_TIME_DAYS
        sku_key = item.sku or item.name

        # 1. Obtain ML Demand Forecast
        trajectory = self.inference_service.predict_daily_trajectory(sku=sku_key, horizon_days=7)
        weekly_forecast = trajectory.predicted_7d_demand
        daily_demand = max(0.5, weekly_forecast / 7.0)

        # 2. Compute Net Available Physical Stock (minus active surplus reservations)
        reserved_statuses = [SurplusStatus.AVAILABLE.value, SurplusStatus.RESERVED.value, SurplusStatus.CLAIMED.value]
        reserved_qty = (
            db.query(func.sum(SurplusListing.quantity))
            .filter(
                SurplusListing.item_id == item.id,
                SurplusListing.status.in_(reserved_statuses),
            )
            .scalar()
            or 0.0
        )
        current_stock = max(0.0, float(item.current_quantity) - float(reserved_qty))

        # 3. Dynamic Safety Stock & Reorder Point
        # SS = Z * sqrt(L) * sigma
        sigma = self.defaults.DEFAULT_DAILY_DEMAND_STD
        z = self.defaults.SERVICE_LEVEL_Z
        safety_stock = round(z * math.sqrt(lead_time) * sigma, 2)
        lead_time_demand = round(daily_demand * lead_time, 2)
        reorder_point = round(lead_time_demand + safety_stock, 2)

        # 4. Target Stock Position (Lead time + 7-day review period cover)
        target_stock = round(lead_time_demand + safety_stock + (daily_demand * self.defaults.REVIEW_PERIOD_DAYS), 2)

        # Storage capacity constraint
        max_storage_limit = round(weekly_forecast * self.defaults.MAX_STORAGE_FACTOR, 2)

        # 5. Expiry Risk Guard Check
        # Check if the product currently has imminent expiry risk
        risk_assessment = self.waste_risk_service.evaluate_item_risk(item, db, persist=False)
        is_blocked = False
        reorder_qty = 0.0
        reason = ""

        if risk_assessment.risk_tier in ["HIGH", "CRITICAL"]:
            is_blocked = True
            reorder_qty = 0.0
            reason = (
                f"REORDER SUPPRESSED: Product is currently at {risk_assessment.risk_tier} waste risk "
                f"({risk_assessment.expected_surplus_units:.1f} {item.unit} expected surplus before expiry). "
                f"Deplete or redistribute current stock before reordering."
            )
        elif current_stock <= reorder_point:
            raw_qty = max(0.0, target_stock - current_stock)
            # Clip by storage capacity
            reorder_qty = min(raw_qty, max_storage_limit)
            reorder_qty = round(reorder_qty, 1)
            reason = (
                f"REORDER RECOMMENDED: Current stock ({current_stock:.1f} {item.unit}) is below reorder point "
                f"({reorder_point:.1f} {item.unit}). Order {reorder_qty:.1f} {item.unit} to cover {lead_time} days lead time "
                f"and safety stock ({safety_stock:.1f} {item.unit})."
            )
        else:
            reorder_qty = 0.0
            reason = (
                f"STOCK ADEQUATE: Current stock ({current_stock:.1f} {item.unit}) is above reorder point "
                f"({reorder_point:.1f} {item.unit}). Target cover is {target_stock:.1f} {item.unit}."
            )

        record = SmartReorderRecord(
            tenant_id=item.tenant_id,
            item_id=item.id,
            sku=item.sku,
            current_stock=round(current_stock, 2),
            predicted_daily_demand=round(daily_demand, 2),
            lead_time_days=lead_time,
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            recommended_reorder_quantity=reorder_qty,
            status=ReorderStatus.RECOMMENDED.value if (reorder_qty > 0 and not is_blocked) else ReorderStatus.DISMISSED.value,
            reason=reason,
            is_blocked_by_expiry_risk=is_blocked,
            generated_at=datetime.now(timezone.utc),
        )

        if persist:
            db.add(record)
            db.commit()
            db.refresh(record)

        return record

    def list_active_reorder_recommendations(
        self,
        tenant_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """Scans tenant inventory and returns active replenishment recommendations."""
        items = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.is_active == True,
            )
            .all()
        )

        results = []
        for item in items:
            rec = self.generate_reorder_recommendation(item, db, persist=False)
            results.append({
                "item_id": item.id,
                "sku": item.sku,
                "product_name": item.name,
                "unit": item.unit,
                "current_stock": rec.current_stock,
                "predicted_daily_demand": rec.predicted_daily_demand,
                "reorder_point": rec.reorder_point,
                "recommended_quantity": rec.recommended_reorder_quantity,
                "lead_time_days": rec.lead_time_days,
                "safety_stock": rec.safety_stock,
                "is_blocked_by_expiry_risk": rec.is_blocked_by_expiry_risk,
                "status": rec.status,
                "reason": rec.reason,
            })

        # Order by actionability: items needing reorders first
        results.sort(key=lambda r: (-r["recommended_quantity"], r["is_blocked_by_expiry_risk"]))
        return results
