"""
Milestone 2 — Phase 4: Automated Test Suite for Waste-Risk Scoring,
Smart Reorders, and Forecast API Integration.

Validates:
- InferenceService model loading and fallback resilience.
- Waste-Risk Engine (Critical/High surplus vs Low risk with adequate demand, zero stock, reservations).
- Smart Reorder Service (Safety stock, lead-time demand, storage limits, and expiry risk block).
- Forecast API Endpoints (/forecasts/health, /forecasts/sku/{sku}, /forecasts/summary).
- Waste-Risk API Endpoints (/waste-risk/evaluate, /waste-risk/alerts, /waste-risk/reorders, /waste-risk/batch-evaluate).
- Strict tenant isolation and cross-tenant authorization guardrails.
"""

from datetime import date, datetime, timedelta
import zoneinfo
import numpy as np
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.models.tenant import Tenant, BusinessType
from backend.app.models.user import User, UserRole
from backend.app.models.category import Category, PerishabilityTier, StorageRequirement
from backend.app.models.inventory import InventoryItem, InventoryStatus, ItemUnit
from backend.app.models.surplus import SurplusListing, SurplusStatus
from backend.app.models.waste_risk import WasteRiskAssessmentRecord, SmartReorderRecord
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.ml.inference_service import InferenceService
from backend.app.ml.waste_risk_service import WasteRiskService
from backend.app.ml.smart_reorder_service import SmartReorderService
from backend.app.ml.batch_job import BatchPredictionJob


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def auth_tenant_and_user(tenant_a: Tenant, user_a_owner: User, token_a_owner: str, db_session: Session):
    """Reuses standard test tenant A, owner, and seeded category."""
    cat = db_session.query(Category).first()
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    return {"tenant": tenant_a, "user": user_a_owner, "category": cat, "headers": headers}


@pytest.fixture
def other_tenant_and_user(tenant_b: Tenant, user_b_owner: User, token_b_owner: str):
    """Sets up an adversarial second tenant to test cross-tenant isolation."""
    headers2 = {"Authorization": f"Bearer {token_b_owner}"}
    return {"tenant": tenant_b, "user": user_b_owner, "headers": headers2}


# -----------------------------------------------------------------------------
# 1. Inference Service Tests
# -----------------------------------------------------------------------------

def test_inference_service_model_loading_and_predictions():
    service = InferenceService()
    health = service.get_health_status()
    assert health["status"] == "HEALTHY"

    res = service.predict_daily_trajectory(
        sku="DAI-MILK-01",
        horizon_days=7,
        tenant_id="tenant-test",
        product_name="Whole Milk",
        unit="liters",
    )
    assert res.sku == "DAI-MILK-01"
    assert len(res.daily_forecasts) == 7
    assert res.predicted_7d_demand > 0.0
    for p in res.daily_forecasts:
        assert p.predicted_sales >= 0.0
        assert p.lower_bound_80 <= p.predicted_sales
        assert p.upper_bound_80 >= p.predicted_sales


def test_inference_service_fallback_resilience():
    # Provide non-existent model paths to test safe fallback
    fallback_service = InferenceService(
        models_dir="non_existent_dir",
        default_1d_model_file="fake_model.joblib",
        default_7d_model_file="fake_model.joblib",
    )
    health = fallback_service.get_health_status()
    assert health["is_using_fallback"] is True

    # Predictions must still succeed safely via Seasonal Naive fallback
    res = fallback_service.predict_daily_trajectory(sku="UNKNOWN-SKU", horizon_days=5)
    assert len(res.daily_forecasts) == 5
    assert (np.array([p.predicted_sales for p in res.daily_forecasts]) >= 0.0).all()


# -----------------------------------------------------------------------------
# 2. Waste-Risk Assessment Engine Tests
# -----------------------------------------------------------------------------

def test_waste_risk_critical_imminent_expiry_with_surplus(db_session: Session, auth_tenant_and_user):
    tenant = auth_tenant_and_user["tenant"]
    cat = auth_tenant_and_user["category"]

    tz = zoneinfo.ZoneInfo(tenant.timezone)
    today = datetime.now(tz).date()
    item = InventoryItem(
        id="item-expiring-soon",
        tenant_id=tenant.id,
        category_id=cat.id,
        name="Organic Greek Yogurt",
        sku="DAI-YOG-01",
        current_quantity=50.0,
        unit="units",
        cost_per_unit=2.0,
        selling_price=3.5,
        purchase_date=today - timedelta(days=10),
        expiry_date=today + timedelta(days=2),  # Expiry in 2 days
    )
    db_session.add(item)
    db_session.commit()

    service = WasteRiskService()
    assessment = service.evaluate_item_risk(item, db_session, persist=False)

    assert assessment.days_to_expiry <= 2.0
    assert assessment.expected_surplus_units > 0.0
    assert assessment.surplus_ratio > 0.20
    # Must be categorized as CRITICAL
    assert assessment.risk_tier == "CRITICAL"
    assert "DISPATCH_DONATION" in assessment.recommended_action


def test_waste_risk_adequate_demand_long_shelf_life(db_session: Session, auth_tenant_and_user):
    tenant = auth_tenant_and_user["tenant"]
    cat = auth_tenant_and_user["category"]

    today = date.today()
    item = InventoryItem(
        id="item-adequate-stock",
        tenant_id=tenant.id,
        category_id=cat.id,
        name="Cheddar Cheese Block",
        sku="DAI-CHED-01",
        current_quantity=10.0,  # Small stock
        unit="units",
        cost_per_unit=3.0,
        selling_price=5.0,
        purchase_date=today,
        expiry_date=today + timedelta(days=25),  # 25 days until expiry
    )
    db_session.add(item)
    db_session.commit()

    service = WasteRiskService()
    assessment = service.evaluate_item_risk(item, db_session, persist=False)

    # 10 units will easily sell in 25 days -> 0 surplus
    assert assessment.expected_surplus_units == 0.0
    assert assessment.risk_tier == "LOW"
    assert assessment.recommended_action == "NORMAL_RETAIL_OPERATIONS"


def test_waste_risk_deducts_active_surplus_reservations(db_session: Session, auth_tenant_and_user):
    tenant = auth_tenant_and_user["tenant"]
    user = auth_tenant_and_user["user"]
    cat = auth_tenant_and_user["category"]

    today = date.today()
    item = InventoryItem(
        id="item-with-reservations",
        tenant_id=tenant.id,
        category_id=cat.id,
        name="Skim Milk",
        sku="DAI-SKIM-01",
        current_quantity=50.0,
        unit="liters",
        cost_per_unit=1.5,
        selling_price=2.5,
        purchase_date=today - timedelta(days=5),
        expiry_date=today + timedelta(days=2),
    )
    db_session.add(item)
    db_session.commit()

    # Create active surplus reservation of 30 units
    surplus = SurplusListing(
        id="surplus-res-01",
        tenant_id=tenant.id,
        item_id=item.id,
        quantity=30.0,
        unit="liters",
        expiry_date=item.expiry_date,
        status=SurplusStatus.AVAILABLE.value,
        pickup_address="123 Store St",
        available_from=datetime.now(),
        available_until=datetime.now() + timedelta(days=1),
        created_by_user_id=user.id,
    )
    db_session.add(surplus)
    db_session.commit()

    service = WasteRiskService()
    assessment = service.evaluate_item_risk(item, db_session, persist=False)

    # Available stock should be 50 - 30 = 20 liters
    assert assessment.current_stock == 20.0


# -----------------------------------------------------------------------------
# 3. Smart Reorder Service Tests
# -----------------------------------------------------------------------------

def test_smart_reorder_triggers_when_stock_below_rop(db_session: Session, auth_tenant_and_user):
    tenant = auth_tenant_and_user["tenant"]
    cat = auth_tenant_and_user["category"]

    today = date.today()
    item = InventoryItem(
        id="item-reorder-needed",
        tenant_id=tenant.id,
        category_id=cat.id,
        name="Butter Salted",
        sku="DAI-BTR-01",
        current_quantity=3.0,  # Depleted stock (below ROP ~25)
        unit="packs",
        cost_per_unit=2.0,
        purchase_date=today,
        expiry_date=today + timedelta(days=30),
    )
    db_session.add(item)
    db_session.commit()

    service = SmartReorderService()
    rec = service.generate_reorder_recommendation(item, db_session, lead_time_days=2, persist=False)

    assert rec.reorder_point > rec.current_stock
    assert rec.recommended_reorder_quantity > 0.0
    assert rec.is_blocked_by_expiry_risk is False
    assert rec.status == "RECOMMENDED"


def test_smart_reorder_blocked_when_item_at_expiry_risk(db_session: Session, auth_tenant_and_user):
    tenant = auth_tenant_and_user["tenant"]
    cat = auth_tenant_and_user["category"]

    today = date.today()
    item = InventoryItem(
        id="item-expiring-surplus",
        tenant_id=tenant.id,
        category_id=cat.id,
        name="Fresh Cream",
        sku="DAI-CRM-01",
        current_quantity=40.0,  # Large quantity expiring in 2 days
        unit="liters",
        cost_per_unit=2.5,
        purchase_date=today - timedelta(days=5),
        expiry_date=today + timedelta(days=2),
    )
    db_session.add(item)
    db_session.commit()

    service = SmartReorderService()
    rec = service.generate_reorder_recommendation(item, db_session, persist=False)

    # Must be BLOCKED due to expiry risk!
    assert rec.is_blocked_by_expiry_risk is True
    assert rec.recommended_reorder_quantity == 0.0
    assert "REORDER SUPPRESSED" in rec.reason


# -----------------------------------------------------------------------------
# 4. Forecast & Waste-Risk API Endpoints & Tenant Isolation Tests
# -----------------------------------------------------------------------------

def test_api_forecast_health(client: TestClient, auth_tenant_and_user):
    resp = client.get("/api/v1/forecasts/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"


def test_api_sku_forecast_and_tenant_isolation(client: TestClient, db_session: Session, auth_tenant_and_user, other_tenant_and_user):
    tenant1 = auth_tenant_and_user["tenant"]
    headers1 = auth_tenant_and_user["headers"]
    headers2 = other_tenant_and_user["headers"]
    cat1 = auth_tenant_and_user["category"]

    today = date.today()
    item1 = InventoryItem(
        id="item-sku-forecast",
        tenant_id=tenant1.id,
        category_id=cat1.id,
        name="Organic Eggs Large",
        sku="DAI-EGGS-01",
        current_quantity=30.0,
        unit="units",
        cost_per_unit=2.5,
        purchase_date=today,
        expiry_date=today + timedelta(days=14),
    )
    db_session.add(item1)
    db_session.commit()

    # 1. Tenant 1 requests its own SKU forecast -> 200 OK
    resp1 = client.get("/api/v1/forecasts/sku/DAI-EGGS-01?horizon_days=7", headers=headers1)
    assert resp1.status_code == 200
    f_data = resp1.json()
    assert f_data["sku"] == "DAI-EGGS-01"
    assert len(f_data["daily_forecasts"]) == 7

    # 2. Tenant 2 requests Tenant 1's SKU -> 404 NOT FOUND (Cross-Tenant Isolation)
    resp2 = client.get("/api/v1/forecasts/sku/DAI-EGGS-01", headers=headers2)
    assert resp2.status_code == 404


def test_api_waste_risk_evaluate_and_alerts(client: TestClient, db_session: Session, auth_tenant_and_user):
    tenant = auth_tenant_and_user["tenant"]
    headers = auth_tenant_and_user["headers"]
    cat = auth_tenant_and_user["category"]

    tz = zoneinfo.ZoneInfo(tenant.timezone)
    today = datetime.now(tz).date()
    item = InventoryItem(
        id="item-api-risk",
        tenant_id=tenant.id,
        category_id=cat.id,
        name="Ripe Strawberries",
        sku="PRO-STR-01",
        current_quantity=60.0,
        unit="packs",
        cost_per_unit=2.0,
        selling_price=4.0,
        purchase_date=today - timedelta(days=3),
        expiry_date=today + timedelta(days=2),
    )
    db_session.add(item)
    db_session.commit()

    # POST /api/v1/waste-risk/evaluate
    eval_resp = client.post(
        "/api/v1/waste-risk/evaluate",
        json={"item_id": item.id, "current_stock": 60.0, "days_to_expiry": 2.0, "unit_cost": 2.0},
        headers=headers,
    )
    assert eval_resp.status_code == 200
    res_data = eval_resp.json()
    assert res_data["risk_tier"] == "CRITICAL"
    assert res_data["value_at_risk"] > 0.0

    # GET /api/v1/waste-risk/alerts
    alerts_resp = client.get("/api/v1/waste-risk/alerts?min_tier=HIGH", headers=headers)
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    assert len(alerts) >= 1
    assert alerts[0]["item_id"] == item.id


def test_api_reorder_recommendations(client: TestClient, auth_tenant_and_user):
    headers = auth_tenant_and_user["headers"]

    resp = client.get("/api/v1/waste-risk/reorders", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_batch_prediction_job_execution(db_session: Session, auth_tenant_and_user):
    tenant = auth_tenant_and_user["tenant"]
    cat = auth_tenant_and_user["category"]

    today = date.today()
    for i in range(3):
        item = InventoryItem(
            id=f"batch-test-item-{i}",
            tenant_id=tenant.id,
            category_id=cat.id,
            name=f"Batch Item {i}",
            sku=f"SKU-BATCH-{i}",
            current_quantity=15.0 + i * 5,
            unit="units",
            cost_per_unit=1.5,
            purchase_date=today,
            expiry_date=today + timedelta(days=4 + i * 3),
        )
        db_session.add(item)
    db_session.commit()

    job = BatchPredictionJob()
    summary = job.execute_tenant_batch(tenant_id=tenant.id, db=db_session)

    assert summary["tenant_id"] == tenant.id
    assert summary["items_evaluated"] >= 3
    assert summary["errors"] == 0
    assert summary["elapsed_ms"] > 0.0

    # Verify records were persisted to the database
    persisted_assessments = db_session.query(WasteRiskAssessmentRecord).filter(WasteRiskAssessmentRecord.tenant_id == tenant.id).count()
    assert persisted_assessments >= 3

    persisted_reorders = db_session.query(SmartReorderRecord).filter(SmartReorderRecord.tenant_id == tenant.id).count()
    assert persisted_reorders >= 3
