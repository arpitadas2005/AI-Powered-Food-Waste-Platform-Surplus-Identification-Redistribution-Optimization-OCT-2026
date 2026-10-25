"""
Milestone 2 — Phase 4: Scheduled Batch Prediction & Risk Evaluation Job.

Idempotently scans active tenant inventory records, evaluates multi-horizon
waste risks and replenishment points, and records audit history.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.models.inventory import InventoryItem
from backend.app.models.tenant import Tenant
from backend.app.ml.waste_risk_service import WasteRiskService
from backend.app.ml.smart_reorder_service import SmartReorderService

logger = logging.getLogger(__name__)


class BatchPredictionJob:
    """
    Executes scheduled or on-demand batch risk evaluation across store tenants.
    """

    def __init__(
        self,
        waste_risk_service: Optional[WasteRiskService] = None,
        smart_reorder_service: Optional[SmartReorderService] = None,
    ):
        self.waste_risk_service = waste_risk_service or WasteRiskService()
        self.smart_reorder_service = smart_reorder_service or SmartReorderService()

    def execute_tenant_batch(self, tenant_id: str, db: Session) -> Dict[str, Any]:
        """
        Executes batch assessment for a single tenant.
        """
        start_time = datetime.now(timezone.utc)
        items = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.is_active == True,
            )
            .all()
        )

        counts = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
        }
        reorder_recommended = 0
        reorder_blocked = 0
        errors = 0

        for item in items:
            try:
                # 1. Risk Evaluation
                assessment = self.waste_risk_service.evaluate_item_risk(item, db, persist=True)
                counts[assessment.risk_tier] = counts.get(assessment.risk_tier, 0) + 1

                # 2. Reorder Recommendation
                rec = self.smart_reorder_service.generate_reorder_recommendation(item, db, persist=True)
                if rec.is_blocked_by_expiry_risk:
                    reorder_blocked += 1
                elif rec.recommended_reorder_quantity > 0:
                    reorder_recommended += 1

            except Exception as e:
                logger.error(f"Error evaluating batch item {item.id} (SKU {item.sku}): {e}")
                errors += 1

        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0

        summary = {
            "tenant_id": tenant_id,
            "items_evaluated": len(items),
            "errors": errors,
            "risk_counts": counts,
            "reorders_recommended_count": reorder_recommended,
            "reorders_blocked_by_expiry": reorder_blocked,
            "executed_at": start_time.isoformat(),
            "elapsed_ms": round(elapsed_ms, 2),
        }
        logger.info(f"Batch prediction complete for tenant {tenant_id}: {summary}")
        return summary

    def execute_all_tenants(self, db: Session) -> List[Dict[str, Any]]:
        """Executes batch predictions across all active tenants."""
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        results = []
        for t in tenants:
            res = self.execute_tenant_batch(tenant_id=t.id, db=db)
            results.append(res)
        return results
