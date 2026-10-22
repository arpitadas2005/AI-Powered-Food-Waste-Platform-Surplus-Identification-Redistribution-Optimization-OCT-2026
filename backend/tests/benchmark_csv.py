"""
CSV Ingestion Pipeline Performance Benchmark
Evaluates processing duration, throughput (rows/sec), and peak memory (RAM)
across multiple dataset sizes: 100, 500, 1000, and 5000 rows.
"""

import os
import sys
import time
import tracemalloc
import io
import csv
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

# Ensure workspace root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.seeds import seed_standard_categories
from backend.app.models.tenant import Tenant, BusinessType
from backend.app.models.user import User, UserRole
from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem
from backend.app.models.csv_import import CsvImportJob
from backend.app.services.csv_service import process_csv_import


def generate_benchmark_csv(num_rows: int, prefix: str = "BENCH") -> bytes:
    """Generate RFC 4180 compliant CSV bytes with diverse valid records."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "name",
        "category",
        "current_quantity",
        "unit",
        "expiry_date",
        "purchase_date",
        "cost_per_unit",
        "sku",
        "barcode",
        "batch_number",
        "storage_location"
    ])
    
    categories = [
        "dairy-and-eggs",
        "fresh-meat-and-poultry",
        "fresh-bakery-and-pastries",
        "leafy-greens-and-soft-produce",
        "pantry-and-dry-goods",
        "prepared-and-cooked-meals",
    ]
    units = ["kg", "g", "liters", "ml", "units", "boxes"]
    base_purchase = datetime(2026, 1, 1).date()
    
    for i in range(1, num_rows + 1):
        cat = categories[i % len(categories)]
        unit = units[i % len(units)]
        sku = f"{prefix}-SKU-{i:06d}"
        barcode = f"890100{i:06d}"
        batch = f"LOT-{i:05d}"
        days_ahead = 15 + (i % 60)
        expiry = base_purchase + timedelta(days=days_ahead)
        cost = f"{(2.50 + (i % 20) * 0.75):.2f}"
        qty = f"{(10 + (i % 100))}.00"
        
        writer.writerow([
            f"Benchmark Item {i}",
            cat,
            qty,
            unit,
            expiry.isoformat(),
            base_purchase.isoformat(),
            cost,
            sku,
            barcode,
            batch,
            f"Shelf {chr(65 + (i % 6))}-{(i % 20) + 1}"
        ])
        
    return output.getvalue().encode("utf-8")


def run_benchmark():
    # Setup in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    
    # Seed taxonomies
    seed_standard_categories(db)
        
    tenant = Tenant(
        name="Benchmark Tenant",
        slug="bench-tenant",
        business_type=BusinessType.SUPERMARKET.value,
        contact_email="bench@test.local",
        timezone="UTC",
        currency="USD",
        is_active=True,
    )
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email="bench@test.local",
        hashed_password="dummy",
        full_name="Benchmarker",
        role=UserRole.BUSINESS_OWNER.value,
        is_active=True,
    )
    db.add(user)
    db.commit()

    test_sizes = [100, 500, 1000, 5000]
    results = []

    print("\n" + "=" * 80)
    print("CSV INGESTION PERFORMANCE BENCHMARK (Multi-Size Scale Test)")
    print("=" * 80)

    for size in test_sizes:
        csv_bytes = generate_benchmark_csv(size, prefix=f"RUN{size}")
        file_size_kb = len(csv_bytes) / 1024.0

        tracemalloc.start()
        start_time = time.perf_counter()

        response = process_csv_import(
            db=db,
            tenant_id=tenant.id,
            user_id=user.id,
            file_bytes=csv_bytes,
            filename=f"bench_{size}.csv",
            dry_run=False,
            allow_partial=False
        )

        end_time = time.perf_counter()
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        duration = end_time - start_time
        throughput = size / duration if duration > 0 else 0
        peak_kb = peak_mem / 1024.0
        peak_mb = peak_kb / 1024.0

        # Verify database state
        inserted_count = db.query(InventoryItem).filter(
            InventoryItem.tenant_id == tenant.id,
            InventoryItem.sku.like(f"RUN{size}-%")
        ).count()
        assert response.status == "COMPLETED", f"Expected COMPLETED, got {response.status}: {response.errors}"
        assert inserted_count == size, f"Expected {size} items in DB, found {inserted_count}"

        results.append({
            "size": size,
            "file_size_kb": round(file_size_kb, 2),
            "duration_s": round(duration, 3),
            "throughput_rps": round(throughput, 1),
            "peak_mem_mb": round(peak_mb, 2),
            "accepted": response.summary.accepted_rows,
            "status": response.status
        })

        print(f"Dataset Size: {size:5d} rows | File: {file_size_kb:6.1f} KB | Duration: {duration:6.3f}s | Throughput: {throughput:7.1f} rows/s | Peak RAM: {peak_mb:5.2f} MB | Status: {response.status}")

    print("=" * 80)
    print("\n### Benchmark Summary Table\n")
    print("| Rows | File Size (KB) | Processing Time (s) | Throughput (rows/sec) | Peak Memory (MB) | DB Committed |")
    print("|------|----------------|---------------------|-----------------------|------------------|--------------|")
    for r in results:
        print(f"| {r['size']:<4} | {r['file_size_kb']:<14} | {r['duration_s']:<19} | {r['throughput_rps']:<21} | {r['peak_mem_mb']:<16} | {r['accepted']} rows ({r['status']}) |")
    print("\n" + "=" * 80 + "\n")

    db.close()

if __name__ == "__main__":
    run_benchmark()
