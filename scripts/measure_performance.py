"""
Milestone 3 — Phase 4: Performance & Latency Benchmarking Utility.
Measures real response latency and execution metrics across critical API paths and ML inference.
"""

import json
import statistics
import time
from datetime import date, timedelta
from starlette.testclient import TestClient

from backend.app.core.security import create_access_token
from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.ml.inference_service import InferenceService
from backend.app.models.tenant import Tenant
from backend.app.models.user import User


def benchmark_operation(name: str, fn, iterations: int = 50):
    durations = []
    # Warm-up call
    try:
        fn()
    except Exception as e:
        pass

    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        durations.append((t1 - t0) * 1000.0) # Convert to ms

    durations.sort()
    p50 = statistics.median(durations)
    p95 = durations[int(len(durations) * 0.95)]
    mean_val = statistics.mean(durations)
    min_val = min(durations)
    max_val = max(durations)

    return {
        "operation": name,
        "iterations": iterations,
        "mean_ms": round(mean_val, 2),
        "median_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "min_ms": round(min_val, 2),
        "max_ms": round(max_val, 2),
    }


def main():
    client = TestClient(app)
    db = SessionLocal()

    # Grab first active tenant or create temp token
    tenant = db.query(Tenant).first()
    tenant_id = tenant.id if tenant else "tenant_test"
    user = db.query(User).filter(User.tenant_id == tenant_id).first()
    user_id = user.id if user else "user_test"
    role = user.role if user else "BUSINESS_OWNER"
    db.close()

    token = create_access_token(user_id, tenant_id, role)
    headers = {"Authorization": f"Bearer {token}"}

    results = []

    # 1. Health Probe
    res1 = benchmark_operation("GET /health (Liveness)", lambda: client.get("/health"), 100)
    results.append(res1)

    # 2. Readiness Probe
    res2 = benchmark_operation("GET /health/ready (Database ping)", lambda: client.get("/health/ready"), 100)
    results.append(res2)

    # 3. Inventory List
    res3 = benchmark_operation("GET /api/v1/inventory (Authenticated)", lambda: client.get("/api/v1/inventory?size=20", headers=headers), 50)
    results.append(res3)

    # 4. ML Model Inference
    inf = InferenceService()
    res4 = benchmark_operation("ML Inference: predict_daily_trajectory (7 days)", lambda: inf.predict_daily_trajectory("SKU-DAIRY-001", horizon_days=7), 100)
    results.append(res4)

    # 5. Business Analytics Summary
    res5 = benchmark_operation("GET /api/v1/analytics/business/summary", lambda: client.get("/api/v1/analytics/business/summary", headers=headers), 50)
    results.append(res5)

    # 6. Sustainability Impact Query
    res6 = benchmark_operation("GET /api/v1/analytics/sustainability", lambda: client.get("/api/v1/analytics/sustainability", headers=headers), 50)
    results.append(res6)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
