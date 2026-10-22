"""
Scheduled Execution Engine for Expiry Evaluation.

Can be triggered:
1. Periodically via external cron: `python -m backend.app.services.expiry_scheduler`
2. Programmatically from background task workers or FastAPI lifespans.
"""

import logging
import sys
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.tenant import Tenant
from backend.app.services.expiry_service import evaluate_tenant_inventory, get_scheduler_diagnostics

logger = logging.getLogger("expiry_scheduler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def run_scheduled_expiry_evaluation(db: Session) -> Dict[str, Any]:
    """
    Evaluates expiry states across all active tenants.
    Isolated per-tenant error handling ensures one tenant error does not abort others.
    """
    diagnostics = get_scheduler_diagnostics()
    logger.info("Starting scheduled expiry evaluation run across all active tenants.")
    if diagnostics.missing_configurations:
        logger.warning(
            "External notification services missing: %s",
            ", ".join(diagnostics.missing_configurations),
        )

    tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
    results = {
        "tenants_evaluated": 0,
        "tenants_failed": 0,
        "total_items_evaluated": 0,
        "total_alerts_created": 0,
        "details": [],
    }

    for tenant in tenants:
        try:
            resp = evaluate_tenant_inventory(db=db, tenant_id=tenant.id, dry_run=False)
            results["tenants_evaluated"] += 1
            results["total_items_evaluated"] += resp.summary.total_evaluated
            results["total_alerts_created"] += resp.summary.alerts_created
            results["details"].append({
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "items": resp.summary.total_evaluated,
                "critical": resp.summary.critical_count,
                "expired": resp.summary.expired_count,
                "alerts_created": resp.summary.alerts_created,
                "status": "SUCCESS",
            })
            logger.info(
                "Tenant '%s' (%s): Evaluated %d items, %d alerts created, %d expired.",
                tenant.name,
                tenant.id,
                resp.summary.total_evaluated,
                resp.summary.alerts_created,
                resp.summary.expired_count,
            )
        except Exception as exc:
            db.rollback()
            results["tenants_failed"] += 1
            results["details"].append({
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "error": str(exc),
                "status": "FAILED",
            })
            logger.error("Failed evaluation for tenant '%s' (%s): %s", tenant.name, tenant.id, exc, exc_info=True)

    return results


def main():
    """CLI entrypoint for cron execution."""
    db = SessionLocal()
    try:
        report = run_scheduled_expiry_evaluation(db)
        print("\n--- Scheduled Expiry Run Complete ---")
        print(f"Tenants Evaluated: {report['tenants_evaluated']} (Failed: {report['tenants_failed']})")
        print(f"Total Items: {report['total_items_evaluated']} | Alerts Created: {report['total_alerts_created']}")
        if report["tenants_failed"] > 0:
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
