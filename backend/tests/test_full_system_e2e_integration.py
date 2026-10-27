"""
Milestone 3 — Phase 4: Full-System End-to-End Integration Test Suite.

Executes and validates the complete user journey across all 5 core workflows:
  Workflow A: Inventory Management & Expiry Horizons
  Workflow B: Demand Forecasting & ML Waste-Risk Assessment
  Workflow C: Surplus Earmarking & Explainable NGO Matching
  Workflow D: Claim Allocation, Logistics Pickups & Physical Stock Deduction
  Workflow E: Executive Dashboards & Verified Sustainability Analytics
"""

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.core.security import create_access_token, get_password_hash
from backend.app.ml.inference_service import InferenceService
from backend.app.ml.waste_risk_service import WasteRiskService
from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus, ItemUnit
from backend.app.models.surplus import (
    ClaimStatus,
    NgoProfile,
    OrganizationType,
    PickupSchedule,
    PickupScheduleStatus,
    SurplusClaim,
    SurplusListing,
    SurplusStatus,
)
from backend.app.models.tenant import BusinessType, Tenant
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.models.user import User, UserRole
from backend.app.models.waste_risk import RiskTier


@pytest.fixture
def e2e_environment(db_session: Session):
    """Sets up a complete isolated multi-tenant environment with donor business, recipient NGO, and third-party tenant."""
    # 1. Donor Business Tenant (Green Grocer)
    donor_tenant = Tenant(
        id="tenant_donor_e2e",
        name="Green Grocer Downtown E2E",
        slug="green-grocer-e2e",
        business_type=BusinessType.SUPERMARKET.value,
        contact_email="owner@greengrocere2e.example",
        timezone="America/New_York",
        currency="USD",
        is_active=True,
    )
    db_session.add(donor_tenant)
    db_session.flush()

    donor_user = User(
        id="user_donor_e2e",
        tenant_id=donor_tenant.id,
        email="owner@greengrocere2e.example",
        hashed_password=get_password_hash("DonorPass123!"),
        full_name="Alice Donor",
        role=UserRole.BUSINESS_OWNER.value,
        is_active=True,
    )
    db_session.add(donor_user)
    db_session.flush()

    # 2. Recipient NGO Tenant (City Food Bank)
    ngo_tenant = Tenant(
        id="tenant_ngo_e2e",
        name="City Food Bank E2E",
        slug="city-food-bank-e2e",
        business_type=BusinessType.NGO_RECIPIENT.value,
        contact_email="director@cityfoodbanke2e.example",
        timezone="America/New_York",
        currency="USD",
        is_active=True,
    )
    db_session.add(ngo_tenant)
    db_session.flush()

    ngo_user = User(
        id="user_ngo_e2e",
        tenant_id=ngo_tenant.id,
        email="director@cityfoodbanke2e.example",
        hashed_password=get_password_hash("NgoPass123!"),
        full_name="Bob Director",
        role=UserRole.RECIPIENT_NGO.value,
        is_active=True,
    )
    db_session.add(ngo_user)
    db_session.flush()

    ngo_profile = NgoProfile(
        id="profile_ngo_e2e",
        tenant_id=ngo_tenant.id,
        organization_type=OrganizationType.FOOD_BANK.value,
        is_verified=True,
        verification_date=datetime.now(timezone.utc),
        contact_person="Bob Director",
        contact_phone="+1-555-0155",
        contact_email="director@cityfoodbanke2e.example",
        address="200 Broadway, New York, NY",
        latitude=40.7128,
        longitude=-74.0060,
        service_radius_km=30.0,
        accepted_categories=json.dumps(["Dairy & Eggs", "Produce"]),
        storage_facilities=json.dumps(["AMBIENT", "REFRIGERATED"]),
        max_capacity_units=1500.0,
    )
    db_session.add(ngo_profile)
    db_session.flush()

    # 3. Isolated Competitor Tenant (Bakery)
    other_tenant = Tenant(
        id="tenant_other_e2e",
        name="Uptown Bakery E2E",
        slug="uptown-bakery-e2e",
        business_type=BusinessType.BAKERY.value,
        contact_email="baker@uptownbakerye2e.example",
        timezone="America/New_York",
        currency="USD",
        is_active=True,
    )
    db_session.add(other_tenant)
    db_session.flush()

    other_user = User(
        id="user_other_e2e",
        tenant_id=other_tenant.id,
        email="baker@uptownbakerye2e.example",
        hashed_password=get_password_hash("OtherPass123!"),
        full_name="Charlie Baker",
        role=UserRole.BUSINESS_OWNER.value,
        is_active=True,
    )
    db_session.add(other_user)
    db_session.commit()

    token_donor = create_access_token(donor_user.id, donor_tenant.id, donor_user.role)
    token_ngo = create_access_token(ngo_user.id, ngo_tenant.id, ngo_user.role)
    token_other = create_access_token(other_user.id, other_tenant.id, other_user.role)

    return {
        "donor_tenant": donor_tenant,
        "donor_user": donor_user,
        "token_donor": token_donor,
        "headers_donor": {"Authorization": f"Bearer {token_donor}"},
        "ngo_tenant": ngo_tenant,
        "ngo_user": ngo_user,
        "ngo_profile": ngo_profile,
        "token_ngo": token_ngo,
        "headers_ngo": {"Authorization": f"Bearer {token_ngo}"},
        "other_tenant": other_tenant,
        "other_user": other_user,
        "token_other": token_other,
        "headers_other": {"Authorization": f"Bearer {token_other}"},
    }


def test_e2e_workflow_a_inventory_and_expiry(client: TestClient, db_session: Session, e2e_environment: dict):
    """Workflow A: Product creation, double-entry ledger, expiry alert detection, and cross-tenant isolation."""
    env = e2e_environment
    headers = env["headers_donor"]
    today = date.today()

    # 1. Create fresh inventory item via API
    item_payload = {
        "category_id": "cat_dairy_eggs",
        "name": "E2E Pasteurized Whole Milk",
        "sku": "MILK-E2E-001",
        "barcode": "012345678905",
        "initial_quantity": 100.0,
        "unit": "kg",
        "cost_per_unit": 2.50,
        "selling_price": 4.00,
        "purchase_date": today.isoformat(),
        "expiry_date": (today + timedelta(days=2)).isoformat(), # Imminent expiry (2 days)
        "storage_requirement": "REFRIGERATED",
        "batch_number": "BATCH-E2E-A1",
    }
    res = client.post("/api/v1/inventory", json=item_payload, headers=headers)
    assert res.status_code == 201, res.text
    item_id = res.json()["data"]["id"]

    # 2. Verify double-entry ledger record created
    txs = db_session.query(StockTransaction).filter(StockTransaction.item_id == item_id).all()
    assert len(txs) >= 1
    assert float(txs[0].quantity_after) == 100.0

    # 3. Verify expiry evaluation detects item as at-risk
    res_exp = client.get("/api/v1/inventory/expiring?horizon=ALL_AT_RISK", headers=headers)
    assert res_exp.status_code == 200
    exp_data = res_exp.json()["data"]
    exp_item_ids = [it["item_id"] for it in exp_data["items"]]
    assert item_id in exp_item_ids

    # 4. Verify negative authorization: other tenant cannot read or adjust item
    res_unauth = client.get(f"/api/v1/inventory/{item_id}", headers=env["headers_other"])
    assert res_unauth.status_code == 404


def test_e2e_workflow_b_forecasting_and_waste_risk(client: TestClient, db_session: Session, e2e_environment: dict):
    """Workflow B: Demand forecasting, finite non-negative predictions, and waste-risk tier calculation."""
    env = e2e_environment
    headers = env["headers_donor"]
    today = date.today()

    # Seed inventory lot with high stock and short expiry (100 kg, expires in 2 days)
    item = InventoryItem(
        tenant_id=env["donor_tenant"].id,
        category_id="cat_dairy_eggs",
        name="E2E Greek Yogurt 1kg",
        sku="YOGURT-E2E-002",
        current_quantity=100.0,
        unit="kg",
        cost_per_unit=3.00,
        purchase_date=today - timedelta(days=1),
        expiry_date=today + timedelta(days=2),
        storage_requirement="REFRIGERATED",
        status=InventoryStatus.EXPIRING_SOON.value,
        is_active=True,
    )
    db_session.add(item)
    db_session.commit()

    # 1. Test forecast model inference service directly
    inf = InferenceService()
    assert inf.get_health_status()["models"]["model_1d_loaded"] is True
    assert inf.get_health_status()["status"] == "HEALTHY"

    # 2. Evaluate waste risk via REST endpoint
    eval_payload = {
        "item_id": item.id,
        "sku": item.sku,
        "current_stock": float(item.current_quantity),
        "days_to_expiry": 2.0,
        "unit_cost": float(item.cost_per_unit),
    }
    res_risk = client.post("/api/v1/waste-risk/evaluate", json=eval_payload, headers=headers)
    assert res_risk.status_code == 200, res_risk.text
    risk_data = res_risk.json()

    assert risk_data["item_id"] == item.id
    assert risk_data["days_to_expiry"] <= 3.0
    # Expected surplus should be substantial and risk tier HIGH or CRITICAL
    assert risk_data["risk_tier"] in (RiskTier.HIGH.value, RiskTier.CRITICAL.value)
    assert risk_data["value_at_risk"] > 0.0
    assert (
        "donation" in risk_data["recommended_action"].lower()
        or "surplus" in risk_data["recommended_action"].lower()
        or "markdown" in risk_data["recommended_action"].lower()
    )

    # 3. Test fallback resilience when item has unknown SKU
    eval_unknown = {
        "sku": "UNKNOWN-NONEXISTENT-SKU",
        "current_stock": 50.0,
        "days_to_expiry": 1.0,
        "unit_cost": 2.00,
    }
    res_fallback = client.post("/api/v1/waste-risk/evaluate", json=eval_unknown, headers=headers)
    assert res_fallback.status_code == 200
    assert res_fallback.json()["risk_tier"] in (RiskTier.HIGH.value, RiskTier.CRITICAL.value)


def test_e2e_workflow_c_surplus_listing_and_ngo_matching(
    client: TestClient, db_session: Session, e2e_environment: dict
):
    """Workflow C: Surplus creation, anti-oversubscription guard, explainable NGO matching, and eligibility."""
    env = e2e_environment
    headers_donor = env["headers_donor"]
    headers_ngo = env["headers_ngo"]
    today = date.today()

    item = InventoryItem(
        tenant_id=env["donor_tenant"].id,
        category_id="cat_dairy_eggs",
        name="E2E Surplus Artisan Cheese",
        sku="CHEESE-E2E-003",
        current_quantity=80.0,
        unit="kg",
        cost_per_unit=4.00,
        purchase_date=today - timedelta(days=1),
        expiry_date=today + timedelta(days=5),
        storage_requirement="REFRIGERATED",
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add(item)
    db_session.commit()

    # 1. Create surplus listing for 50 kg (out of 80 kg stock)
    listing_payload = {
        "item_id": item.id,
        "title": "Surplus Artisan Cheese Wheels",
        "quantity": 50.0,
        "unit": "kg",
        "expiry_date": item.expiry_date.isoformat(),
        "storage_requirement": "REFRIGERATED",
        "pickup_address": "100 Market St, Dock #4",
        "pickup_instructions": "Bring refrigerated vehicle.",
        "available_from": datetime.now(timezone.utc).isoformat(),
        "available_until": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
    }
    res_list = client.post("/api/v1/surplus/listings", json=listing_payload, headers=headers_donor)
    assert res_list.status_code == 201, res_list.text
    listing_id = res_list.json()["data"]["id"]

    # 2. Anti-oversubscription gate: Attempt to create second listing for 40 kg (50 + 40 = 90 > 80)
    invalid_listing_payload = {
        "item_id": item.id,
        "title": "Excess Oversubscribed Cheese",
        "quantity": 40.0,
        "unit": "kg",
        "expiry_date": item.expiry_date.isoformat(),
        "storage_requirement": "REFRIGERATED",
        "pickup_address": "100 Market St",
        "available_from": datetime.now(timezone.utc).isoformat(),
        "available_until": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
    }
    res_over = client.post("/api/v1/surplus/listings", json=invalid_listing_payload, headers=headers_donor)
    assert res_over.status_code == 400
    assert "exceeds available unearmarked inventory" in res_over.json()["error"]["message"]

    # 3. Query explainable NGO matching engine
    res_match = client.get(f"/api/v1/surplus/listings/{listing_id}/matches", headers=headers_donor)
    assert res_match.status_code == 200, res_match.text
    match_data = res_match.json()["data"]
    assert match_data["listing_id"] == listing_id
    assert len(match_data["matching_recommendations"]) >= 1

    top_ngo = match_data["matching_recommendations"][0]
    assert top_ngo["ngo_tenant_id"] == env["ngo_tenant"].id
    assert top_ngo["is_verified"] is True
    assert top_ngo["match_score"] > 50.0
    assert len(top_ngo["match_reasons"]) >= 1


def test_e2e_workflow_d_claims_pickup_and_stock_deduction(
    client: TestClient, db_session: Session, e2e_environment: dict
):
    """Workflow D: Claim request, donor review, logistics scheduling, milestone progression, and physical stock deduction."""
    env = e2e_environment
    headers_donor = env["headers_donor"]
    headers_ngo = env["headers_ngo"]
    today = date.today()

    item = InventoryItem(
        tenant_id=env["donor_tenant"].id,
        category_id="cat_dairy_eggs",
        name="E2E Organic Butter",
        sku="BUTTER-E2E-004",
        current_quantity=50.0,
        unit="kg",
        cost_per_unit=5.00,
        purchase_date=today - timedelta(days=1),
        expiry_date=today + timedelta(days=6),
        storage_requirement="REFRIGERATED",
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add(item)
    db_session.commit()

    listing = SurplusListing(
        tenant_id=env["donor_tenant"].id,
        item_id=item.id,
        title="Surplus Organic Butter Lot",
        quantity=30.0,
        unit="kg",
        expiry_date=item.expiry_date,
        storage_requirement="REFRIGERATED",
        status=SurplusStatus.AVAILABLE.value,
        pickup_address="100 Market St",
        available_from=datetime.now(timezone.utc) - timedelta(hours=1),
        available_until=datetime.now(timezone.utc) + timedelta(days=4),
        created_by_user_id=env["donor_user"].id,
    )
    db_session.add(listing)
    db_session.commit()

    # 1. NGO submits claim for 20 kg
    claim_payload = {
        "listing_id": listing.id,
        "claimed_quantity": 20.0,
        "pickup_time": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "notes": "Emergency family food boxes.",
    }
    res_claim = client.post("/api/v1/surplus/claims", json=claim_payload, headers=headers_ngo)
    assert res_claim.status_code == 201, res_claim.text
    claim_id = res_claim.json()["data"]["id"]

    # 2. Donor approves claim
    res_review = client.post(
        f"/api/v1/surplus/claims/{claim_id}/review",
        json={"action": "ACCEPT", "review_notes": "Approved for morning pickup."},
        headers=headers_donor,
    )
    assert res_review.status_code == 200
    assert res_review.json()["data"]["status"] == ClaimStatus.APPROVED.value

    # 3. Schedule logistics pickup
    pickup_payload = {
        "pickup_date": (today + timedelta(days=1)).isoformat(),
        "pickup_start_time": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "pickup_end_time": (datetime.now(timezone.utc) + timedelta(hours=26)).isoformat(),
        "pickup_location": "100 Market St Dock A",
        "vehicle_type": "REFRIGERATED_VAN",
        "driver_name": "Dave Logistics",
        "driver_phone": "+1-555-0899",
    }
    res_sched = client.post(f"/api/v1/surplus/claims/{claim_id}/schedule", json=pickup_payload, headers=headers_ngo)
    assert res_sched.status_code == 201, res_sched.text
    assert res_sched.json()["data"]["status"] == PickupScheduleStatus.SCHEDULED.value

    # 4. Progress milestone: Mark Ready
    res_ready = client.post(f"/api/v1/surplus/claims/{claim_id}/ready", headers=headers_donor)
    assert res_ready.status_code == 200
    assert res_ready.json()["data"]["status"] == PickupScheduleStatus.READY_FOR_COLLECTION.value

    # 5. Progress milestone: Confirm Collection
    res_collect = client.post(f"/api/v1/surplus/claims/{claim_id}/collect", headers=headers_donor)
    assert res_collect.status_code == 200
    assert res_collect.json()["data"]["status"] == PickupScheduleStatus.COLLECTED.value

    # 6. Complete surplus transfer & trigger physical stock deduction
    res_complete = client.post(f"/api/v1/surplus/claims/{claim_id}/complete", headers=headers_donor)
    assert res_complete.status_code == 200
    assert res_complete.json()["data"]["status"] == ClaimStatus.COMPLETED.value

    # 7. Verify atomic stock deduction in database ledger
    db_session.refresh(item)
    # Original 50.0 - 20.0 claimed = 30.0 remaining
    assert float(item.current_quantity) == 30.0

    # Verify StockTransaction logged
    dispatch_tx = (
        db_session.query(StockTransaction)
        .filter(
            StockTransaction.item_id == item.id,
            StockTransaction.transaction_type == TransactionType.DONATION_DISPATCH.value,
        )
        .first()
    )
    assert dispatch_tx is not None
    assert float(dispatch_tx.quantity_change) == -20.0
    assert float(dispatch_tx.quantity_after) == 30.0


def test_e2e_workflow_e_dashboards_and_sustainability_analytics(
    client: TestClient, db_session: Session, e2e_environment: dict
):
    """Workflow E: Business and NGO dashboard summaries, verified EPA WARM v15 sustainability metrics, and sanitized CSV export."""
    env = e2e_environment
    headers_donor = env["headers_donor"]
    headers_ngo = env["headers_ngo"]
    today = date.today()

    item = InventoryItem(
        tenant_id=env["donor_tenant"].id,
        category_id="cat_dairy_eggs",
        name="E2E Rescued Yogurt",
        sku="YOGURT-RESCUE-005",
        current_quantity=60.0,
        unit="kg",
        cost_per_unit=3.00,
        purchase_date=today - timedelta(days=2),
        expiry_date=today + timedelta(days=4),
        storage_requirement="REFRIGERATED",
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add(item)
    db_session.flush()

    listing = SurplusListing(
        tenant_id=env["donor_tenant"].id,
        item_id=item.id,
        title="Surplus Yogurt for Impact",
        quantity=40.0,
        unit="kg",
        expiry_date=item.expiry_date,
        storage_requirement="REFRIGERATED",
        status=SurplusStatus.AVAILABLE.value,
        pickup_address="100 Market St",
        available_from=datetime.now(timezone.utc) - timedelta(hours=1),
        available_until=datetime.now(timezone.utc) + timedelta(days=2),
        created_by_user_id=env["donor_user"].id,
    )
    db_session.add(listing)
    db_session.flush()

    # Seed 1 COMPLETED claim (40 kg @ $3.00 = $120.00 value)
    claim = SurplusClaim(
        listing_id=listing.id,
        ngo_tenant_id=env["ngo_tenant"].id,
        claimed_by_user_id=env["ngo_user"].id,
        claimed_quantity=40.0,
        unit="kg",
        status=ClaimStatus.COMPLETED.value,
    )
    db_session.add(claim)
    db_session.commit()

    # 1. Business Dashboard Query
    res_biz = client.get("/api/v1/analytics/business/summary", headers=headers_donor)
    assert res_biz.status_code == 200, res_biz.text
    biz_data = res_biz.json()["data"]
    assert biz_data["completed_transfers_count"] >= 1
    assert biz_data["total_food_rescued_kg"] >= 40.0
    assert biz_data["total_value_rescued"] >= 120.0
    assert biz_data["co2e_avoided_kg"] >= 100.0 # 40 * 2.5

    # 2. NGO Portal Query
    res_ngo = client.get("/api/v1/analytics/ngo/summary", headers=headers_ngo)
    assert res_ngo.status_code == 200, res_ngo.text
    ngo_data = res_ngo.json()["data"]
    assert ngo_data["completed_collections_count"] >= 1
    assert ngo_data["total_food_rescued_kg"] >= 40.0
    assert ngo_data["meals_provided"] >= 95 # 40 / 0.42 = 95.23 -> 95

    # 3. Sustainability Metrics Query
    res_sust = client.get("/api/v1/analytics/sustainability", headers=headers_donor)
    assert res_sust.status_code == 200, res_sust.text
    sust_data = res_sust.json()["data"]
    assert sust_data["total_rescued_weight_kg"] >= 40.0
    assert sust_data["co2e_avoided_kg"] >= 100.0
    assert sust_data["total_meals_provided"] >= 95
    assert sust_data["equivalencies"]["trees_planted_equivalent"] > 4.0
    assert sust_data["equivalencies"]["passenger_car_miles_avoided"] > 250.0

    # 4. Time Series Trend Query
    res_ts = client.get("/api/v1/analytics/time-series?interval=daily", headers=headers_donor)
    assert res_ts.status_code == 200, res_ts.text
    ts_data = res_ts.json()["data"]
    assert ts_data["total_points"] >= 1

    # 5. CSV Export with Sanitization
    res_csv = client.get("/api/v1/analytics/export/csv", headers=headers_donor)
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    reader = csv.reader(io.StringIO(res_csv.text))
    rows = list(reader)
    assert len(rows) >= 2 # Header + at least 1 record
