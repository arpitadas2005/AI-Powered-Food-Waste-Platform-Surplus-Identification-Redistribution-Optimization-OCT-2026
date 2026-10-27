"""
Milestone 3 — Phase 3: Comprehensive Test Suite for Business/NGO Dashboards & Sustainability Impact Analytics.

Covers:
  1. Business Dashboard Summary (commercial stock, expiry risk, surplus listings, claims, pickups, transfers).
  2. Role Protection (NGOs receiving 403 on Business summary).
  3. NGO Dashboard Summary (eligible listings, claims under review, pickup logistics, food mass received, meals served).
  4. Sustainability Metrics Accuracy (EPA WARM v15 GHG avoidance: 2.5 kg CO2e/kg, Feeding America: 0.42 kg/meal, Trees & Car equivalents).
  5. Status Integrity Gate (Only COMPLETED claims contribute to rescued environmental & social impact).
  6. Chronological Time-Series Aggregation & Date Filtering.
  7. CSV Export & Spreadsheet Formula Injection Defense (CWE-1236 sanitization with leading apostrophe).
  8. Multi-Tenant Boundary Isolation.
  9. Empty-State & Zero-Division Resilience.
"""

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.core.security import create_access_token, get_password_hash
from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus
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
from backend.app.models.user import User, UserRole


@pytest.fixture
def test_ngo(db_session: Session):
    """Fixture creating a verified NGO tenant, user, and profile."""
    ngo_tenant = Tenant(
        id="tenant_ngo_metro_meals",
        name="Metropolitan Food Rescue",
        slug="metro-food-rescue",
        business_type=BusinessType.NGO_RECIPIENT.value,
        contact_email="contact@metromeals.example",
        timezone="America/New_York",
        currency="USD",
        is_active=True,
    )
    db_session.add(ngo_tenant)
    db_session.flush()

    ngo_user = User(
        id="user_ngo_director_1",
        tenant_id=ngo_tenant.id,
        email="director@metromeals.example",
        hashed_password=get_password_hash("RescuePass123!"),
        full_name="Maria Rescue",
        role=UserRole.RECIPIENT_NGO.value,
        is_active=True,
    )
    db_session.add(ngo_user)
    db_session.flush()

    ngo_profile = NgoProfile(
        id="profile_metro_meals_1",
        tenant_id=ngo_tenant.id,
        organization_type=OrganizationType.FOOD_BANK.value,
        is_verified=True,
        verification_date=datetime.now(timezone.utc),
        contact_person="Maria Rescue",
        contact_phone="+1-555-0199",
        contact_email="director@metromeals.example",
        address="100 Hope St, New York, NY",
        latitude=40.7128,
        longitude=-74.0060,
        service_radius_km=25.0,
        accepted_categories=json.dumps(["Dairy & Eggs", "Bakery"]),
        storage_facilities=json.dumps(["AMBIENT", "REFRIGERATED"]),
        max_capacity_units=1000.0,
    )
    db_session.add(ngo_profile)
    db_session.commit()

    token = create_access_token(
        subject=ngo_user.id,
        tenant_id=ngo_tenant.id,
        role=ngo_user.role,
    )

    return {
        "tenant": ngo_tenant,
        "user": ngo_user,
        "profile": ngo_profile,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def test_business_dashboard_summary(
    client: TestClient,
    db_session: Session,
    tenant_a: Tenant,
    user_a_owner: User,
    token_a_owner: str,
    test_ngo: dict,
):
    """Verifies that business summary aggregates commercial stock, surplus, claims, and pickups accurately."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    today = date.today()

    # 1. Seed inventory items
    item1 = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Organic Greek Yogurt",
        current_quantity=50.0,
        unit="kg",
        cost_per_unit=4.00,
        purchase_date=today - timedelta(days=5),
        expiry_date=today + timedelta(days=2), # Expiring soon
        status=InventoryStatus.EXPIRING_SOON.value,
        is_active=True,
    )
    item2 = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Almond Milk",
        current_quantity=30.0,
        unit="kg",
        cost_per_unit=3.00,
        purchase_date=today - timedelta(days=10),
        expiry_date=today + timedelta(days=15),
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add_all([item1, item2])
    db_session.flush()

    # 2. Seed surplus listings
    listing1 = SurplusListing(
        tenant_id=tenant_a.id,
        item_id=item1.id,
        title="Surplus Greek Yogurt Batch",
        quantity=20.0,
        unit="kg",
        expiry_date=item1.expiry_date,
        storage_requirement="REFRIGERATED",
        status=SurplusStatus.AVAILABLE.value,
        pickup_address="123 Market St, Store #1",
        available_from=datetime.now(timezone.utc) - timedelta(hours=2),
        available_until=datetime.now(timezone.utc) + timedelta(days=1),
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(listing1)
    db_session.flush()

    # 3. Seed completed claim (20 kg yogurt @ $4.00 = $80 value rescued)
    completed_claim = SurplusClaim(
        listing_id=listing1.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=20.0,
        unit="kg",
        status=ClaimStatus.COMPLETED.value,
    )
    # Seed pending claim
    pending_claim = SurplusClaim(
        listing_id=listing1.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=5.0,
        unit="kg",
        status=ClaimStatus.REQUESTED.value,
    )
    db_session.add_all([completed_claim, pending_claim])
    db_session.flush()

    # 4. Seed upcoming pickup
    pickup = PickupSchedule(
        claim_id=completed_claim.id,
        listing_id=listing1.id,
        donor_tenant_id=tenant_a.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        pickup_date=today,
        pickup_start_time=datetime.now(timezone.utc) + timedelta(hours=1),
        pickup_end_time=datetime.now(timezone.utc) + timedelta(hours=3),
        pickup_location="123 Market St Loading Dock",
        status=PickupScheduleStatus.SCHEDULED.value,
        scheduled_by_user_id=user_a_owner.id,
    )
    db_session.add(pickup)
    db_session.commit()

    # Call endpoint
    res = client.get("/api/v1/analytics/business/summary", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    data = body["data"]

    assert data["tenant_id"] == tenant_a.id
    assert data["total_inventory_items"] == 2
    # Stock value: (50 * 4) + (30 * 3) = 200 + 90 = 290.0
    assert data["total_stock_value"] == 290.0
    assert data["items_expiring_soon_count"] == 1
    assert data["at_risk_value"] == 200.0 # 50 * 4.00
    assert data["active_surplus_listings_count"] == 1
    assert data["pending_claims_count"] == 1
    assert data["upcoming_pickups_count"] == 1
    assert data["completed_transfers_count"] == 1
    assert data["total_food_rescued_kg"] == 20.0
    # CO2e avoided: 20 * 2.5 = 50.0
    assert data["co2e_avoided_kg"] == 50.0
    # Meals provided: int(20 / 0.42) = 47
    assert data["meals_provided"] == 47
    assert data["total_value_rescued"] == 80.0
    assert len(data["recent_activity"]) >= 2


def test_business_summary_forbidden_for_ngo(
    client: TestClient,
    test_ngo: dict,
):
    """Verifies that recipient NGO roles cannot query commercial business dashboard metrics."""
    res = client.get("/api/v1/analytics/business/summary", headers=test_ngo["headers"])
    assert res.status_code == 403
    json_err = res.json()
    err_msg = json_err.get("detail") or json_err.get("error", {}).get("message", "")
    assert "NGO organizations should access" in err_msg


def test_ngo_dashboard_summary(
    client: TestClient,
    db_session: Session,
    tenant_a: Tenant,
    user_a_owner: User,
    test_ngo: dict,
):
    """Verifies that NGO dashboard summary accurately tracks intake, eligible listings, and meals served."""
    headers = test_ngo["headers"]
    today = date.today()

    # Seed inventory & listing from donor
    item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Cottage Cheese 500g",
        current_quantity=40.0,
        unit="kg",
        cost_per_unit=2.50,
        purchase_date=today - timedelta(days=2),
        expiry_date=today + timedelta(days=5),
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add(item)
    db_session.flush()

    listing = SurplusListing(
        tenant_id=tenant_a.id,
        item_id=item.id,
        title="Fresh Cottage Cheese",
        quantity=30.0,
        unit="kg",
        expiry_date=item.expiry_date,
        storage_requirement="REFRIGERATED",
        status=SurplusStatus.AVAILABLE.value,
        pickup_address="123 Market St",
        available_from=datetime.now(timezone.utc) - timedelta(hours=1),
        available_until=datetime.now(timezone.utc) + timedelta(days=2),
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(listing)
    db_session.flush()

    # Seed 1 accepted claim and 1 completed claim for this NGO
    accepted_claim = SurplusClaim(
        listing_id=listing.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=10.0,
        unit="kg",
        status=ClaimStatus.ACCEPTED.value,
    )
    completed_claim = SurplusClaim(
        listing_id=listing.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=15.0,
        unit="kg",
        status=ClaimStatus.COMPLETED.value,
    )
    db_session.add_all([accepted_claim, completed_claim])
    db_session.commit()

    res = client.get("/api/v1/analytics/ngo/summary", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    data = body["data"]

    assert data["tenant_id"] == test_ngo["tenant"].id
    assert data["organization_name"] == test_ngo["tenant"].name
    assert data["is_verified"] is True
    assert data["eligible_surplus_listings_count"] >= 1
    assert data["accepted_claims_count"] == 1
    assert data["completed_collections_count"] == 1
    assert data["total_food_rescued_kg"] == 15.0
    # Meals: int(15 / 0.42) = 35
    assert data["meals_provided"] == 35
    assert data["value_received"] == 37.50 # 15 * 2.50
    assert len(data["recent_claims"]) == 2


def test_sustainability_metrics_calculation_and_status_gate(
    client: TestClient,
    db_session: Session,
    tenant_a: Tenant,
    user_a_owner: User,
    token_a_owner: str,
    test_ngo: dict,
):
    """
    Verifies that ONLY COMPLETED claims contribute to rescued environmental & social impact.
    Pending, requested, or cancelled claims must NOT artificially inflate rescued metrics.
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    today = date.today()

    item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Artisan Cheddar",
        current_quantity=100.0,
        unit="kg",
        cost_per_unit=5.00,
        purchase_date=today - timedelta(days=1),
        expiry_date=today + timedelta(days=10),
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add(item)
    db_session.flush()

    listing = SurplusListing(
        tenant_id=tenant_a.id,
        item_id=item.id,
        title="Surplus Cheddar Block",
        quantity=50.0,
        unit="kg",
        expiry_date=item.expiry_date,
        storage_requirement="REFRIGERATED",
        status=SurplusStatus.AVAILABLE.value,
        pickup_address="123 Market St",
        available_from=datetime.now(timezone.utc) - timedelta(hours=1),
        available_until=datetime.now(timezone.utc) + timedelta(days=2),
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(listing)
    db_session.flush()

    # 1 Completed claim (40 kg @ $5 = $200)
    c_completed = SurplusClaim(
        listing_id=listing.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=40.0,
        unit="kg",
        status=ClaimStatus.COMPLETED.value,
    )
    # 1 Pending claim (100 kg) - MUST BE EXCLUDED
    c_pending = SurplusClaim(
        listing_id=listing.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=100.0,
        unit="kg",
        status=ClaimStatus.PENDING.value,
    )
    # 1 Cancelled claim (200 kg) - MUST BE EXCLUDED
    c_cancelled = SurplusClaim(
        listing_id=listing.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=200.0,
        unit="kg",
        status=ClaimStatus.CANCELLED.value,
    )
    db_session.add_all([c_completed, c_pending, c_cancelled])
    db_session.commit()

    res = client.get("/api/v1/analytics/sustainability", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    # Only the 40 kg from c_completed is counted!
    assert data["total_rescued_weight_kg"] == 40.0
    assert data["completed_claims_count"] == 1
    assert data["total_value_rescued"] == 200.0

    # EPA WARM v15: 40 kg * 2.5 = 100.0 kg CO2e
    assert data["co2e_avoided_kg"] == 100.0
    # Feeding America: int(40 / 0.42) = 95 meals
    assert data["total_meals_provided"] == 95

    # Environmental equivalencies
    # Trees: 100.0 / 21.77 ≈ 4.59
    assert abs(data["equivalencies"]["trees_planted_equivalent"] - (100.0 / 21.77)) < 0.05
    # Car miles: 100.0 / 0.393 ≈ 254.45
    assert abs(data["equivalencies"]["passenger_car_miles_avoided"] - (100.0 / 0.393)) < 1.0

    # Category breakdown check
    assert len(data["category_breakdown"]) >= 1
    cat0 = data["category_breakdown"][0]
    assert cat0["category_id"] == "cat_dairy_eggs"
    assert cat0["rescued_kg"] == 40.0
    assert cat0["co2e_avoided_kg"] == 100.0
    assert cat0["meals_provided"] == 95
    assert cat0["value_rescued"] == 200.0


def test_redistribution_time_series(
    client: TestClient,
    db_session: Session,
    tenant_a: Tenant,
    user_a_owner: User,
    token_a_owner: str,
    test_ngo: dict,
):
    """Verifies time-series timeline aggregation and date filtering."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    today = date.today()

    item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Fresh Milk 1L",
        current_quantity=20.0,
        unit="kg",
        cost_per_unit=1.50,
        purchase_date=today - timedelta(days=1),
        expiry_date=today + timedelta(days=4),
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add(item)
    db_session.flush()

    listing = SurplusListing(
        tenant_id=tenant_a.id,
        item_id=item.id,
        title="Milk Batch",
        quantity=10.0,
        unit="kg",
        expiry_date=item.expiry_date,
        storage_requirement="REFRIGERATED",
        status=SurplusStatus.AVAILABLE.value,
        pickup_address="123 Market St",
        available_from=datetime.now(timezone.utc) - timedelta(hours=1),
        available_until=datetime.now(timezone.utc) + timedelta(days=2),
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(listing)
    db_session.flush()

    claim = SurplusClaim(
        listing_id=listing.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=10.0,
        unit="kg",
        status=ClaimStatus.COMPLETED.value,
    )
    db_session.add(claim)
    db_session.commit()

    res = client.get(
        f"/api/v1/analytics/time-series?date_from={today - timedelta(days=7)}&date_to={today}&interval=daily",
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    assert data["interval"] == "daily"
    assert data["total_points"] >= 1
    pt = data["points"][0]
    assert pt["rescued_kg"] == 10.0
    assert pt["co2e_avoided_kg"] == 25.0 # 10 * 2.5
    assert pt["meals_provided"] == 23    # int(10 / 0.42)
    assert pt["value_rescued"] == 15.0   # 10 * 1.50


def test_csv_export_and_formula_injection_defense(
    client: TestClient,
    db_session: Session,
    tenant_a: Tenant,
    user_a_owner: User,
    token_a_owner: str,
    test_ngo: dict,
):
    """
    CRITICAL SECURITY TEST: Verifies that CSV export neutralizes formula injection attacks (CWE-1236).
    Any string starting with =, +, -, @, \\t, \\r must be prefixed with a single apostrophe (').
    """
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    today = date.today()

    # Create an item and listing with potentially malicious spreadsheet formulas
    malicious_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="=cmd|'/C calc'!A0",
        current_quantity=10.0,
        unit="kg",
        cost_per_unit=2.00,
        purchase_date=today - timedelta(days=1),
        expiry_date=today + timedelta(days=5),
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add(malicious_item)
    db_session.flush()

    malicious_listing = SurplusListing(
        tenant_id=tenant_a.id,
        item_id=malicious_item.id,
        title="@SUM(1,2)*cmd|'/C calc'!A0",
        quantity=5.0,
        unit="kg",
        expiry_date=malicious_item.expiry_date,
        storage_requirement="AMBIENT",
        status=SurplusStatus.AVAILABLE.value,
        pickup_address="+12345 Dangerous Street",
        available_from=datetime.now(timezone.utc) - timedelta(hours=1),
        available_until=datetime.now(timezone.utc) + timedelta(days=2),
        created_by_user_id=user_a_owner.id,
    )
    db_session.add(malicious_listing)
    db_session.flush()

    claim = SurplusClaim(
        listing_id=malicious_listing.id,
        ngo_tenant_id=test_ngo["tenant"].id,
        claimed_by_user_id=test_ngo["user"].id,
        claimed_quantity=5.0,
        unit="kg",
        status=ClaimStatus.COMPLETED.value,
    )
    db_session.add(claim)
    db_session.commit()

    res = client.get("/api/v1/analytics/export/csv", headers=headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment; filename=" in res.headers["content-disposition"]

    csv_text = res.text
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) >= 2 # Header + at least 1 row

    data_row = rows[1]
    # Check listing title column (index 2) was sanitized with leading '
    listing_title_cell = data_row[2]
    assert listing_title_cell.startswith("'@"), f"Expected sanitized formula injection cell: {listing_title_cell}"


def test_multi_tenant_isolation_in_analytics(
    client: TestClient,
    db_session: Session,
    tenant_a: Tenant,
    tenant_b: Tenant,
    user_a_owner: User,
    user_b_owner: User,
    token_a_owner: str,
    test_ngo: dict,
):
    """Verifies that Tenant A's business analytics never leak Tenant B's inventory or surplus."""
    headers_a = {"Authorization": f"Bearer {token_a_owner}"}
    token_b = create_access_token(subject=user_b_owner.id, tenant_id=tenant_b.id, role=user_b_owner.role)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    today = date.today()

    # Tenant A item
    item_a = InventoryItem(
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Tenant A Secret Stock",
        current_quantity=100.0,
        unit="kg",
        cost_per_unit=10.00,
        purchase_date=today,
        expiry_date=today + timedelta(days=20),
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    # Tenant B item
    item_b = InventoryItem(
        tenant_id=tenant_b.id,
        category_id="cat_dairy_eggs",
        name="Tenant B Secret Stock",
        current_quantity=500.0,
        unit="kg",
        cost_per_unit=5.00,
        purchase_date=today,
        expiry_date=today + timedelta(days=20),
        status=InventoryStatus.ACTIVE.value,
        is_active=True,
    )
    db_session.add_all([item_a, item_b])
    db_session.commit()

    # Tenant A request
    res_a = client.get("/api/v1/analytics/business/summary", headers=headers_a)
    assert res_a.status_code == 200
    data_a = res_a.json()["data"]
    assert data_a["total_inventory_items"] == 1
    assert data_a["total_stock_value"] == 1000.0 # 100 * 10

    # Tenant B request
    res_b = client.get("/api/v1/analytics/business/summary", headers=headers_b)
    assert res_b.status_code == 200
    data_b = res_b.json()["data"]
    assert data_b["total_inventory_items"] == 1
    assert data_b["total_stock_value"] == 2500.0 # 500 * 5


def test_empty_state_resilience(
    client: TestClient,
    tenant_b: Tenant,
    user_b_owner: User,
):
    """Verifies that brand new tenants with zero inventory and zero surplus get clean zeroed metrics without crashing."""
    token_b = create_access_token(subject=user_b_owner.id, tenant_id=tenant_b.id, role=user_b_owner.role)
    headers = {"Authorization": f"Bearer {token_b}"}

    # Business summary
    res1 = client.get("/api/v1/analytics/business/summary", headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()["data"]
    assert data1["total_inventory_items"] == 0
    assert data1["total_stock_value"] == 0.0
    assert data1["total_food_rescued_kg"] == 0.0
    assert data1["co2e_avoided_kg"] == 0.0
    assert data1["meals_provided"] == 0

    # Sustainability
    res2 = client.get("/api/v1/analytics/sustainability", headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()["data"]
    assert data2["total_rescued_weight_kg"] == 0.0
    assert data2["total_meals_provided"] == 0
    assert data2["completed_claims_count"] == 0
    assert len(data2["category_breakdown"]) == 0

    # Time series
    res3 = client.get("/api/v1/analytics/time-series", headers=headers)
    assert res3.status_code == 200
    data3 = res3.json()["data"]
    assert data3["total_points"] == 0

    # CSV export
    res4 = client.get("/api/v1/analytics/export/csv", headers=headers)
    assert res4.status_code == 200
    reader = csv.reader(io.StringIO(res4.text))
    rows = list(reader)
    assert len(rows) == 1 # Only header row
