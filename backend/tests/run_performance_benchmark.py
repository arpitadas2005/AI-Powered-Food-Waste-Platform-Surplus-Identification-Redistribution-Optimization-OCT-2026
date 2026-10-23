"""
Milestone 1 — Independent QA Performance Benchmark Suite.

Measures:
1. Inventory Listing & Pagination Latency (p50, p95)
2. Search & Filtering Latency (p50, p95)
3. CSV Ingestion Throughput (500 and 1,000 rows, dry-run vs commit)
4. Expiry Batch Evaluation Duration & Deduplication Speed
5. API Endpoint Response Latencies (p50, p95)
6. Peak Memory Usage via tracemalloc

Hardware and environment metrics are captured dynamically.
"""

import csv
from datetime import date, datetime, timedelta, timezone
import io
import os
import platform
import statistics
import sys
import time
import tracemalloc
from typing import Dict, List
import uuid

sys.path.insert(0, os.path.abspath("."))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.app.core.security import create_access_token, get_password_hash
from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.alert import TenantAlertConfig
from backend.app.models.category import Category, PerishabilityTier, StorageRequirement
from backend.app.models.inventory import InventoryItem, InventoryStatus
from backend.app.models.tenant import BusinessType, Tenant
from backend.app.models.user import User, UserRole
from backend.app.services.csv_service import process_csv_import
from backend.app.services.expiry_service import evaluate_tenant_inventory
from backend.app.services.inventory_service import (
    adjust_stock_quantity,
    get_item_transactions,
    list_inventory_items,
    lookup_by_barcode,
)
from backend.app.schemas.inventory import StockAdjustmentRequest


def format_stats(latencies_ms: List[float]) -> Dict[str, float]:
    sorted_l = sorted(latencies_ms)
    n = len(sorted_l)
    return {
        "count": n,
        "min_ms": round(sorted_l[0], 2),
        "p50_ms": round(statistics.median(sorted_l), 2),
        "p95_ms": round(sorted_l[int(n * 0.95)], 2),
        "max_ms": round(sorted_l[-1], 2),
        "mean_ms": round(statistics.mean(sorted_l), 2),
    }


def run_benchmarks():
    print("=" * 70)
    print("MILESTONE 1 — INDEPENDENT QA PERFORMANCE BENCHMARK")
    print("=" * 70)

    # 1. Environment Details
    env_info = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu": platform.processor(),
        "python": platform.python_version(),
        "database": "SQLite 3 (In-Memory with Foreign Keys)",
    }
    for k, v in env_info.items():
        print(f"  {k.upper()}: {v}")
    print("-" * 70)

    tracemalloc.start()

    # 2. Setup isolated in-memory database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()

    # Seed Tenant & Categories
    tenant = Tenant(
        id=str(uuid.uuid4()),
        name="Benchmark Supermarket",
        slug="benchmark-market",
        business_type=BusinessType.SUPERMARKET.value,
        contact_email="qa@benchmark.test",
        is_active=True,
    )
    db.add(tenant)

    user = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        email="qa-owner@benchmark.test",
        hashed_password=get_password_hash("BenchmarkPass123!"),
        full_name="QA Lead Engineer",
        role=UserRole.BUSINESS_OWNER.value,
        is_active=True,
    )
    db.add(user)

    alert_config = TenantAlertConfig(
        tenant_id=tenant.id,
        critical_threshold_hours=24,
        warning_threshold_days=3,
        notice_threshold_days=7,
        auto_flag_for_donation=True,
    )
    db.add(alert_config)

    categories = [
        Category(
            id=f"cat-{i}",
            name=f"Category {i}",
            slug=f"category-{i}",
            perishability_tier=PerishabilityTier.HIGH.value,
            recommended_storage=StorageRequirement.REFRIGERATED.value,
            default_shelf_life_days=7,
        )
        for i in range(10)
    ]
    for c in categories:
        db.add(c)
    db.commit()

    # 3. Seed Realistic Inventory (1,000 items)
    print("[1/5] Seeding 1,000 synthetic inventory items...")
    seed_start = time.perf_counter()
    today = date.today()

    items = []
    for i in range(1, 1001):
        cat = categories[i % 10]
        # Spread expiry: 10% expired, 20% critical/warning, 70% fresh
        if i % 10 == 0:
            exp = today - timedelta(days=2)
        elif i % 5 == 0:
            exp = today + timedelta(days=2)
        else:
            exp = today + timedelta(days=14)

        items.append(
            InventoryItem(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                category_id=cat.id,
                name=f"Fresh Food Product #{i}",
                sku=f"SKU-BM-{i:05d}",
                barcode=f"088000{i:06d}",
                current_quantity=50.0 + (i % 25),
                unit="kg" if i % 2 == 0 else "units",
                cost_per_unit=2.50 + (i % 10),
                selling_price=4.99 + (i % 15),
                purchase_date=today - timedelta(days=5),
                expiry_date=exp,
                batch_number=f"BATCH-{202600 + (i % 50)}",
                storage_requirement=cat.recommended_storage,
                storage_location=f"Aisle {1 + (i % 10)}",
                status=InventoryStatus.ACTIVE.value,
                is_active=True,
            )
        )
    db.add_all(items)
    db.commit()
    seed_dur = (time.perf_counter() - seed_start) * 1000.0
    print(f"      Seeded 1,000 items in {seed_dur:.2f} ms")

    # Warmup
    for _ in range(5):
        list_inventory_items(db, tenant.id, page=1, size=50)

    # 4. Listing Latency Benchmark (1,000 items dataset)
    print("\n[2/5] Benchmarking Inventory Listing & Pagination (50 iterations)...")
    listing_latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        res, count = list_inventory_items(db, tenant.id, page=1, size=50)
        t1 = time.perf_counter()
        listing_latencies.append((t1 - t0) * 1000.0)
    stats_list = format_stats(listing_latencies)
    print(f"      p50: {stats_list['p50_ms']} ms | p95: {stats_list['p95_ms']} ms | min: {stats_list['min_ms']} ms | max: {stats_list['max_ms']} ms")

    # 5. Search & Filter Latency Benchmark
    print("\n[3/5] Benchmarking Search & Filter Operations (50 iterations each)...")
    search_latencies = []
    for i in range(50):
        kw = f"#{10 + i * 5}"
        t0 = time.perf_counter()
        res, count = list_inventory_items(db, tenant.id, search=kw, page=1, size=20)
        t1 = time.perf_counter()
        search_latencies.append((t1 - t0) * 1000.0)
    stats_search = format_stats(search_latencies)
    print(f"      Full-Text Search -> p50: {stats_search['p50_ms']} ms | p95: {stats_search['p95_ms']} ms")

    filter_latencies = []
    for i in range(50):
        cat_id = f"cat-{i % 10}"
        t0 = time.perf_counter()
        res, count = list_inventory_items(
            db, tenant.id, category_id=cat_id, storage_requirement="REFRIGERATED", page=1, size=20
        )
        t1 = time.perf_counter()
        filter_latencies.append((t1 - t0) * 1000.0)
    stats_filter = format_stats(filter_latencies)
    print(f"      Category+Storage Filter -> p50: {stats_filter['p50_ms']} ms | p95: {stats_filter['p95_ms']} ms")

    barcode_latencies = []
    for i in range(50):
        code = f"088000{100 + i:06d}"
        t0 = time.perf_counter()
        matched, ctype, emb = lookup_by_barcode(db, tenant.id, code)
        t1 = time.perf_counter()
        barcode_latencies.append((t1 - t0) * 1000.0)
    stats_barcode = format_stats(barcode_latencies)
    print(f"      Barcode Point-Lookup -> p50: {stats_barcode['p50_ms']} ms | p95: {stats_barcode['p95_ms']} ms")

    # Stock Adjustment Latency
    target_item = items[0]
    adj_latencies = []
    for i in range(50):
        req = StockAdjustmentRequest(
            quantity_delta=1.0,
            adjustment_type="RESTOCK",
            reason=f"Bench restock {i}",
            idempotency_key=str(uuid.uuid4()),
        )
        t0 = time.perf_counter()
        adjust_stock_quantity(db, tenant.id, user.id, target_item.id, req)
        t1 = time.perf_counter()
        adj_latencies.append((t1 - t0) * 1000.0)
    stats_adj = format_stats(adj_latencies)
    print(f"      Stock Adjustment (Atomic Ledger) -> p50: {stats_adj['p50_ms']} ms | p95: {stats_adj['p95_ms']} ms")

    # Transaction History Query Latency
    tx_latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        txs = get_item_transactions(db, tenant.id, target_item.id)
        t1 = time.perf_counter()
        tx_latencies.append((t1 - t0) * 1000.0)
    stats_tx = format_stats(tx_latencies)
    print(f"      Transaction History Query -> p50: {stats_tx['p50_ms']} ms | p95: {stats_tx['p95_ms']} ms")

    # 6. CSV Bulk Ingestion Throughput
    print("\n[4/5] Benchmarking CSV Import Pipeline...")
    # Generate 500-row and 1,000-row CSVs
    def make_csv(num_rows: int, prefix: str) -> bytes:
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["name", "category", "sku", "barcode", "current_quantity", "unit", "purchase_date", "expiry_date"])
        for r in range(1, num_rows + 1):
            w.writerow([
                f"{prefix} Bulk Item {r}",
                "category-0",
                f"CSV-{prefix}-{r:04d}",
                f"99{r:08d}",
                25.0,
                "kg",
                str(today),
                str(today + timedelta(days=10)),
            ])
        return out.getvalue().encode("utf-8")

    csv_500 = make_csv(500, "SET500")
    csv_1000 = make_csv(1000, "SET1K")

    # 500 rows Dry Run
    t0 = time.perf_counter()
    res_dry500 = process_csv_import(db, tenant.id, user.id, "bench500.csv", csv_500, dry_run=True)
    t_dry500 = time.perf_counter() - t0
    tp_dry500 = 500 / t_dry500
    print(f"      500 rows (Dry Run): {t_dry500*1000:.2f} ms ({tp_dry500:.0f} rows/sec) — accepted: {res_dry500.summary.accepted_rows}")

    # 1,000 rows Dry Run
    t0 = time.perf_counter()
    res_dry1k = process_csv_import(db, tenant.id, user.id, "bench1k.csv", csv_1000, dry_run=True)
    t_dry1k = time.perf_counter() - t0
    tp_dry1k = 1000 / t_dry1k
    print(f"      1,000 rows (Dry Run): {t_dry1k*1000:.2f} ms ({tp_dry1k:.0f} rows/sec) — accepted: {res_dry1k.summary.accepted_rows}")

    # 500 rows Live Commit
    t0 = time.perf_counter()
    res_com500 = process_csv_import(db, tenant.id, user.id, "bench500_commit.csv", csv_500, dry_run=False, allow_partial=False)
    t_com500 = time.perf_counter() - t0
    tp_com500 = 500 / t_com500
    print(f"      500 rows (Live DB Commit): {t_com500*1000:.2f} ms ({tp_com500:.0f} rows/sec) — accepted: {res_com500.summary.accepted_rows}")

    # 7. Expiry Batch Processing Duration
    print("\n[5/5] Benchmarking Expiry Batch Processing...")
    t0 = time.perf_counter()
    exp_eval_1 = evaluate_tenant_inventory(db, tenant.id)
    t_exp1 = (time.perf_counter() - t0) * 1000.0
    print(f"      Initial Run (1,500 active items): {t_exp1:.2f} ms | Evaluated: {exp_eval_1.summary.total_evaluated} | Alerts Created: {exp_eval_1.summary.alerts_created}")

    # Repeated Run (Deduplication)
    t0 = time.perf_counter()
    exp_eval_2 = evaluate_tenant_inventory(db, tenant.id)
    t_exp2 = (time.perf_counter() - t0) * 1000.0
    print(f"      Deduplication Run: {t_exp2:.2f} ms | Evaluated: {exp_eval_2.summary.total_evaluated} | Alerts Created: {exp_eval_2.summary.alerts_created} (0 expected)")

    # 8. API Endpoint Latency via TestClient
    print("\n[6/6] Benchmarking HTTP API Endpoints via TestClient...")
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    token = create_access_token(user.id, tenant.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)

    # Health
    health_latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        r = client.get("/health")
        t1 = time.perf_counter()
        assert r.status_code == 200
        health_latencies.append((t1 - t0) * 1000.0)
    stats_health = format_stats(health_latencies)
    print(f"      GET /health -> p50: {stats_health['p50_ms']} ms | p95: {stats_health['p95_ms']} ms")

    # Categories
    cat_latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        r = client.get("/api/v1/categories", headers=headers)
        t1 = time.perf_counter()
        assert r.status_code == 200
        cat_latencies.append((t1 - t0) * 1000.0)
    stats_cat = format_stats(cat_latencies)
    print(f"      GET /api/v1/categories -> p50: {stats_cat['p50_ms']} ms | p95: {stats_cat['p95_ms']} ms")

    # Expiry Config
    cfg_latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        r = client.get("/api/v1/alerts/config", headers=headers)
        t1 = time.perf_counter()
        assert r.status_code == 200
        cfg_latencies.append((t1 - t0) * 1000.0)
    stats_cfg = format_stats(cfg_latencies)
    print(f"      GET /api/v1/alerts/config -> p50: {stats_cfg['p50_ms']} ms | p95: {stats_cfg['p95_ms']} ms")

    # 9. Memory Footprint
    app.dependency_overrides.clear()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\n      Memory Footprint: Current = {current_mem / 1024 / 1024:.2f} MB, Peak = {peak_mem / 1024 / 1024:.2f} MB")
    print("=" * 70)
    print("BENCHMARK COMPLETE — ALL MEASUREMENTS CAPTURED")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmarks()
