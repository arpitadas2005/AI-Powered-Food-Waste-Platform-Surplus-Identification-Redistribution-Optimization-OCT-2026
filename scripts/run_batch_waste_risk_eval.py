"""
CLI entrypoint for running batch waste-risk and smart reorder evaluations.
"""

import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.db.session import SessionLocal
from backend.app.ml.batch_job import BatchPredictionJob


def main():
    print("=" * 70)
    print("STARTING SCHEDULED BATCH WASTE-RISK & REORDER EVALUATION")
    print("=" * 70)

    db = SessionLocal()
    try:
        job = BatchPredictionJob()
        results = job.execute_all_tenants(db=db)
        print(f"\nProcessed {len(results)} active store tenants:")
        for r in results:
            print(f"Tenant {r['tenant_id']}: {r['items_evaluated']} items evaluated, "
                  f"Critical: {r['risk_counts']['CRITICAL']}, High: {r['risk_counts']['HIGH']}, "
                  f"Reorders Recommended: {r['reorders_recommended_count']}, "
                  f"Reorders Blocked: {r['reorders_blocked_by_expiry']} (Elapsed: {r['elapsed_ms']}ms)")
    finally:
        db.close()

    print("\n" + "=" * 70)
    print("BATCH EVALUATION COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()
