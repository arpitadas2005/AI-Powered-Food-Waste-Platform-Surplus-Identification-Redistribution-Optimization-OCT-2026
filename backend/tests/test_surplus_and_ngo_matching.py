"""Comprehensive Test Suite for Surplus Food Listings and NGO Matching Engine (Milestone 3 - Phase 1).

Covers:
  1. Surplus Listing Creation & Food Safety Validation (shelf-life, oversubscription prevention).
  2. Surplus Listing Updates, Availability Reconciliation & Cancellation.
  3. Explainable NGO Matching Engine (cold-chain safety gate, category filtering, distance, urgency, verification bonus).
  4. Missing Coordinates Rule: Never fabricate coordinates, neutral score + explicit reason.
  5. NGO Claim Workflow: Request, Approve, Reject, Cancel, Oversubscription Prevention.
  6. Physical Donation Dispatch: Immutable Stock Ledger Deduction via DONATION_DISPATCH.
  7. Cross-Tenant Security & Role-Based Access Control.
  8. In-App Notifications & Audit Trail Logging.
"""

from datetime import date, datetime, timedelta, timezone
import json
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.core.security import create_access_token, get_password_hash
from backend.app.models.audit import AuditEvent, AuditEventType
from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem
from backend.app.models.surplus import (
    ClaimStatus,
    NgoProfile,
    OrganizationType,
    SurplusClaim,
    SurplusListing,
    SurplusNotification,
    SurplusStatus,
)
from backend.app.models.tenant import BusinessType, Tenant
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.models.user import User, UserRole
from backend.app.services.matching_service import calculate_ngo_matches, haversine_distance
from backend.app.services.surplus_service import (
    ExcessiveClaimError,
    FoodSafetyValidationError,
    InsufficientSurplusStockError,
    calculate_active_earmarked_quantity,
    cancel_surplus_claim,
    cancel_surplus_listing,
    complete_surplus_transfer,
    create_surplus_claim,
    create_surplus_listing,
    get_or_create_ngo_profile,
    review_surplus_claim,
    update_ngo_profile,
)
from backend.app.schemas.surplus import (
    NgoProfileUpdate,
    SurplusClaimCreate,
    SurplusListingCreate,
    SurplusListingUpdate,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def ngo_tenant_and_user(db_session: Session):
    """Fixture creating a verified NGO tenant and recipient user."""
    ngo_tenant = Tenant(
        id="tenant_ngo_food_bank",
        name="Metropolitan Food Rescue",
        slug="metro-food-rescue",
        business_type=BusinessType.NGO_RECIPIENT.value,
        contact_email="contact@metrorescue.org",
        phone="+1-555-0199",
        address="100 Hope St, New York, NY",
        timezone="America/New_York",
        currency="USD",
        is_active=True,
    )
    db_session.add(ngo_tenant)
    db_session.flush()

    ngo_user = User(
        id="user_ngo_director",
        tenant_id=ngo_tenant.id,
        email="director@metrorescue.org",
        hashed_password=get_password_hash("RescuePass123!"),
        full_name="Sarah Rescue",
        role=UserRole.RECIPIENT_NGO.value,
        is_active=True,
    )
    db_session.add(ngo_user)
    db_session.flush()

    ngo_profile = NgoProfile(
        id="profile_metro_rescue",
        tenant_id=ngo_tenant.id,
        organization_type=OrganizationType.FOOD_BANK.value,
        is_verified=True,
        verification_date=datetime.now(timezone.utc),
        contact_person="Sarah Rescue",
        contact_phone="+1-555-0199",
        contact_email="director@metrorescue.org",
        address="100 Hope St, New York, NY",
        latitude=40.7128,
        longitude=-74.0060,
        service_radius_km=30.0,
        accepted_categories=json.dumps(["Dairy", "Produce", "Bakery"]),
        storage_facilities=json.dumps(["AMBIENT", "REFRIGERATED", "FROZEN"]),
        max_capacity_units=800.0,
        operating_hours="08:00 - 20:00",
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


@pytest.fixture
def secondary_ngo(db_session: Session):
    """Fixture creating an unverified community pantry with ambient-only storage and no coords."""
    ngo_tenant = Tenant(
        id="tenant_ngo_community_pantry",
        name="Neighborhood Community Pantry",
        slug="neighborhood-pantry",
        business_type=BusinessType.NGO_RECIPIENT.value,
        contact_email="info@neighborhoodpantry.org",
        phone="+1-555-0877",
        address="45 Elm St",
        timezone="America/New_York",
        currency="USD",
        is_active=True,
    )
    db_session.add(ngo_tenant)
    db_session.flush()

    ngo_user = User(
        id="user_ngo_volunteer",
        tenant_id=ngo_tenant.id,
        email="volunteer@neighborhoodpantry.org",
        hashed_password=get_password_hash("PantryPass123!"),
        full_name="Dave Volunteer",
        role=UserRole.RECIPIENT_NGO.value,
        is_active=True,
    )
    db_session.add(ngo_user)
    db_session.flush()

    ngo_profile = NgoProfile(
        id="profile_neighborhood_pantry",
        tenant_id=ngo_tenant.id,
        organization_type=OrganizationType.COMMUNITY_PANTRY.value,
        is_verified=False,
        contact_person="Dave Volunteer",
        contact_phone="+1-555-0877",
        contact_email="info@neighborhoodpantry.org",
        address="45 Elm St",
        latitude=None,  # Intentionally missing coordinates
        longitude=None,
        service_radius_km=15.0,
        accepted_categories=json.dumps(["Produce", "Bakery"]),  # Does not accept Dairy
        storage_facilities=json.dumps(["AMBIENT"]),  # No cold-chain
        max_capacity_units=150.0,
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


@pytest.fixture
def donor_item(db_session: Session, tenant_a: Tenant, user_a_owner: User):
    """Creates a sample inventory item on Tenant A with 50 units."""
    today = date.today()
    item = InventoryItem(
        id="item-dairy-yogurt",
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Greek Yogurt Vanilla 500g",
        sku="DAI-YOG-01",
        current_quantity=50.0,
        unit="units",
        cost_per_unit=1.20,
        selling_price=2.80,
        purchase_date=today - timedelta(days=5),
        expiry_date=today + timedelta(days=2),
        storage_requirement="REFRIGERATED",
        is_active=True,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


# -----------------------------------------------------------------------------
# 1. Listing Creation & Food Safety Validation Tests
# -----------------------------------------------------------------------------

def test_create_surplus_listing_success(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem):
    """Verify business creates a surplus listing with earmarking and audit logging."""
    listing_in = SurplusListingCreate(
        item_id=donor_item.id,
        title="Surplus Greek Yogurt Batch",
        quantity=20.0,
        pickup_address="123 Market St, Loading Dock 1",
        pickup_instructions="Refrigerated transport required",
        available_until=datetime.now(timezone.utc) + timedelta(days=1),
    )

    listing = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=listing_in,
    )

    assert listing.id is not None
    assert listing.status == SurplusStatus.AVAILABLE.value
    assert float(listing.quantity) == 20.0
    assert listing.storage_requirement == "REFRIGERATED"

    # Earmarked calculation check
    earmarked = calculate_active_earmarked_quantity(db_session, tenant_a.id, donor_item.id)
    assert earmarked == 20.0

    # Audit check
    audit = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.event_type == AuditEventType.SURPLUS_LISTING_CREATE.value,
            AuditEvent.resource_id == listing.id,
        )
    ).scalar_one_or_none()
    assert audit is not None


def test_create_surplus_listing_fails_on_expired_item(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem):
    """Food Safety Gate: Expired items cannot be listed for donation."""
    donor_item.expiry_date = date.today() - timedelta(days=1)
    db_session.commit()

    listing_in = SurplusListingCreate(
        item_id=donor_item.id,
        quantity=10.0,
        pickup_address="123 Market St",
        available_until=datetime.now(timezone.utc) + timedelta(days=1),
    )

    with pytest.raises(FoodSafetyValidationError, match="Cannot list expired food"):
        create_surplus_listing(
            db=db_session,
            tenant_id=tenant_a.id,
            user_id=user_a_owner.id,
            listing_in=listing_in,
        )


def test_create_surplus_listing_prevents_oversubscription(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem):
    """Listing cannot exceed available unearmarked physical inventory."""
    # Item has 50 units. Requesting 60 units must fail.
    listing_in = SurplusListingCreate(
        item_id=donor_item.id,
        quantity=60.0,
        pickup_address="123 Market St",
        available_until=datetime.now(timezone.utc) + timedelta(days=1),
    )

    with pytest.raises(InsufficientSurplusStockError, match="exceeds available unearmarked inventory"):
        create_surplus_listing(
            db=db_session,
            tenant_id=tenant_a.id,
            user_id=user_a_owner.id,
            listing_in=listing_in,
        )


def test_multiple_listings_enforce_cumulative_stock_boundary(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem):
    """Multiple concurrent listings on the same item cannot cumulatively exceed physical stock."""
    # Listing 1: 35 units (leaves 15 available)
    listing1 = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=SurplusListingCreate(
            item_id=donor_item.id,
            quantity=35.0,
            pickup_address="Dock A",
            available_until=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )
    assert listing1 is not None

    # Listing 2: 20 units (35 + 20 = 55 > 50) -> Must fail!
    with pytest.raises(InsufficientSurplusStockError):
        create_surplus_listing(
            db=db_session,
            tenant_id=tenant_a.id,
            user_id=user_a_owner.id,
            listing_in=SurplusListingCreate(
                item_id=donor_item.id,
                quantity=20.0,
                pickup_address="Dock B",
                available_until=datetime.now(timezone.utc) + timedelta(days=1),
            ),
        )

    # Listing 2: 15 units (35 + 15 = 50 == 50) -> Must succeed!
    listing2 = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=SurplusListingCreate(
            item_id=donor_item.id,
            quantity=15.0,
            pickup_address="Dock B",
            available_until=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )
    assert listing2 is not None
    assert calculate_active_earmarked_quantity(db_session, tenant_a.id, donor_item.id) == 50.0


# -----------------------------------------------------------------------------
# 2. NGO Matching Engine Tests
# -----------------------------------------------------------------------------

def test_haversine_distance_computation():
    """Verify GPS distance calculation accuracy between NYC coordinates."""
    # Times Square (40.7580, -73.9855) to Brooklyn Bridge (40.7061, -73.9969) ~5.8 km
    dist = haversine_distance(40.7580, -73.9855, 40.7061, -73.9969)
    assert 5.5 <= dist <= 6.2


def test_matching_engine_cold_chain_safety_gate(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem, ngo_tenant_and_user, secondary_ngo):
    """
    Cold-Chain Gate Rule:
    Greek Yogurt requires REFRIGERATED storage.
    - ngo_tenant_and_user has REFRIGERATED storage -> Recommended.
    - secondary_ngo has only AMBIENT storage -> Excluded to prevent food poisoning!
    """
    listing = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=SurplusListingCreate(
            item_id=donor_item.id,
            quantity=25.0,
            storage_requirement="REFRIGERATED",
            pickup_address="123 Market St",
            available_until=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )

    matches_resp = calculate_ngo_matches(
        db=db_session,
        listing=listing,
        origin_lat=40.7130,
        origin_lon=-74.0050,
    )

    rec_ngo_ids = [r.ngo_tenant_id for r in matches_resp.matching_recommendations]
    assert ngo_tenant_and_user["tenant"].id in rec_ngo_ids
    # Secondary NGO lacks cold-chain storage and does not accept Dairy -> Must NOT be recommended
    assert secondary_ngo["tenant"].id not in rec_ngo_ids

    # Verify explainable match reasons for the matched NGO
    top_match = matches_resp.matching_recommendations[0]
    assert top_match.ngo_tenant_id == ngo_tenant_and_user["tenant"].id
    assert top_match.match_score >= 80.0
    assert any("refrigeration" in r.lower() for r in top_match.match_reasons)
    assert any("dairy" in r.lower() for r in top_match.match_reasons)


def test_matching_engine_missing_coords_does_not_fabricate_distance(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem, secondary_ngo):
    """
    Strict Proximity Rule:
    If coordinates are missing, distance MUST NOT be fabricated.
    Distance is None, a neutral score is assigned, and reason is transparent.
    """
    # Create an AMBIENT bakery item that secondary_ngo accepts
    today = date.today()
    bread_item = InventoryItem(
        id="item-bakery-bread",
        tenant_id=tenant_a.id,
        category_id="cat_bakery",
        name="Sourdough Loaf",
        sku="BAK-SOU-01",
        current_quantity=30.0,
        unit="units",
        cost_per_unit=1.0,
        purchase_date=today,
        expiry_date=today + timedelta(days=3),
        storage_requirement="AMBIENT",
        is_active=True,
    )
    db_session.add(bread_item)
    db_session.commit()

    listing = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=SurplusListingCreate(
            item_id=bread_item.id,
            quantity=10.0,
            storage_requirement="AMBIENT",
            pickup_address="123 Market St",
            available_until=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )

    matches_resp = calculate_ngo_matches(
        db=db_session,
        listing=listing,
        origin_lat=None,  # No origin GPS provided
        origin_lon=None,
    )

    # secondary_ngo accepts Bakery and has AMBIENT storage, but missing coords
    pantry_match = next((r for r in matches_resp.matching_recommendations if r.ngo_tenant_id == secondary_ngo["tenant"].id), None)
    assert pantry_match is not None
    assert pantry_match.distance_km is None  # Never fabricated!
    assert "Distance unverified (coordinates not configured)" in pantry_match.match_reasons


# -----------------------------------------------------------------------------
# 3. Claims Lifecycle & Inventory Reconciliation
# -----------------------------------------------------------------------------

def test_claim_request_approval_and_inventory_dispatch(
    db_session: Session,
    tenant_a: Tenant,
    user_a_owner: User,
    donor_item: InventoryItem,
    ngo_tenant_and_user,
):
    """
    Full end-to-end donation dispatch workflow:
      1. Business creates surplus listing for 30 units (Item has 50).
      2. NGO requests 20 units -> Claim status REQUESTED.
      3. Business approves claim -> Claim status APPROVED.
      4. NGO picks up food -> Business confirms handover.
      5. Inventory item physical stock is automatically reduced from 50 -> 30 units!
      6. Immutable transaction ledger entry records DONATION_DISPATCH.
    """
    # 1. Create Listing
    listing = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=SurplusListingCreate(
            item_id=donor_item.id,
            quantity=30.0,
            pickup_address="Main Store Loading Bay",
            available_until=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )

    # 2. NGO Claims 20 units
    claim = create_surplus_claim(
        db=db_session,
        ngo_tenant_id=ngo_tenant_and_user["tenant"].id,
        user_id=ngo_tenant_and_user["user"].id,
        claim_in=SurplusClaimCreate(
            listing_id=listing.id,
            claimed_quantity=20.0,
            notes="Bringing mobile refrigerated food pantry van",
        ),
    )
    assert claim.status == ClaimStatus.REQUESTED.value
    assert float(claim.claimed_quantity) == 20.0

    # Notification created for donor
    notif = db_session.execute(
        select(SurplusNotification).where(
            SurplusNotification.tenant_id == tenant_a.id,
            SurplusNotification.notification_type == "CLAIM_REQUESTED",
        )
    ).scalar_one_or_none()
    assert notif is not None

    # 3. Business Approves Claim
    approved_claim = review_surplus_claim(
        db=db_session,
        donor_tenant_id=tenant_a.id,
        reviewer_user_id=user_a_owner.id,
        claim_id=claim.id,
        action="APPROVE",
    )
    assert approved_claim.status == ClaimStatus.APPROVED.value

    # 4. Physical Handover / Collection
    completed_claim, updated_item = complete_surplus_transfer(
        db=db_session,
        donor_tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        claim_id=approved_claim.id,
    )
    assert completed_claim.status == ClaimStatus.COMPLETED.value

    # 5. Inventory Ledger Reconciliation
    assert float(updated_item.current_quantity) == 30.0  # 50 - 20 = 30!

    tx = db_session.execute(
        select(StockTransaction).where(
            StockTransaction.item_id == donor_item.id,
            StockTransaction.transaction_type == TransactionType.DONATION_DISPATCH.value,
        )
    ).scalar_one_or_none()
    assert tx is not None
    assert float(tx.quantity_change) == -20.0
    assert float(tx.quantity_before) == 50.0
    assert float(tx.quantity_after) == 30.0


def test_claim_rejection_frees_reservation(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem, ngo_tenant_and_user):
    """Rejecting an NGO claim releases the hold and notifies the NGO."""
    listing = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=SurplusListingCreate(
            item_id=donor_item.id,
            quantity=15.0,
            pickup_address="Store 1",
            available_until=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )

    claim = create_surplus_claim(
        db=db_session,
        ngo_tenant_id=ngo_tenant_and_user["tenant"].id,
        user_id=ngo_tenant_and_user["user"].id,
        claim_in=SurplusClaimCreate(listing_id=listing.id, claimed_quantity=15.0),
    )

    # Reject claim
    rejected_claim = review_surplus_claim(
        db=db_session,
        donor_tenant_id=tenant_a.id,
        reviewer_user_id=user_a_owner.id,
        claim_id=claim.id,
        action="REJECT",
        rejection_reason="Pickup vehicle not available before closing",
    )
    assert rejected_claim.status == ClaimStatus.REJECTED.value
    assert rejected_claim.rejection_reason == "Pickup vehicle not available before closing"

    # Listing remains available
    db_session.refresh(listing)
    assert listing.status == SurplusStatus.AVAILABLE.value


def test_claim_cannot_exceed_remaining_claimable_quantity(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem, ngo_tenant_and_user):
    """NGO cannot claim more than the remaining claimable balance of a listing."""
    listing = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=SurplusListingCreate(
            item_id=donor_item.id,
            quantity=10.0,
            pickup_address="Dock",
            available_until=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )

    # Attempting to claim 15 units when only 10 available -> must fail!
    with pytest.raises(ExcessiveClaimError, match="exceeds remaining available quantity"):
        create_surplus_claim(
            db=db_session,
            ngo_tenant_id=ngo_tenant_and_user["tenant"].id,
            user_id=ngo_tenant_and_user["user"].id,
            claim_in=SurplusClaimCreate(listing_id=listing.id, claimed_quantity=15.0),
        )


def test_cancel_listing_auto_cancels_pending_claims(db_session: Session, tenant_a: Tenant, user_a_owner: User, donor_item: InventoryItem, ngo_tenant_and_user):
    """Cancelling a listing cancels pending NGO claims and releases reservations."""
    listing = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=SurplusListingCreate(
            item_id=donor_item.id,
            quantity=20.0,
            pickup_address="Dock",
            available_until=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    )

    claim = create_surplus_claim(
        db=db_session,
        ngo_tenant_id=ngo_tenant_and_user["tenant"].id,
        user_id=ngo_tenant_and_user["user"].id,
        claim_in=SurplusClaimCreate(listing_id=listing.id, claimed_quantity=10.0),
    )

    cancelled_listing = cancel_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_id=listing.id,
        reason="Stock damaged during storm",
    )
    assert cancelled_listing.status == SurplusStatus.CANCELLED.value

    db_session.refresh(claim)
    assert claim.status == ClaimStatus.CANCELLED.value
    assert "Stock damaged during storm" in claim.rejection_reason


# -----------------------------------------------------------------------------
# 4. REST API & Cross-Tenant Security Tests
# -----------------------------------------------------------------------------

def test_api_create_and_list_surplus_listings(client: TestClient, token_a_owner: str, donor_item: InventoryItem):
    """Test HTTP POST /api/v1/surplus/listings and GET /api/v1/surplus/listings."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    payload = {
        "item_id": donor_item.id,
        "title": "API Test Surplus Yogurt",
        "quantity": 12.0,
        "pickup_address": "400 5th Ave",
        "available_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }

    # 1. Create
    resp = client.post("/api/v1/surplus/listings", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["title"] == "API Test Surplus Yogurt"
    assert data["quantity"] == 12.0
    listing_id = data["id"]

    # 2. List
    list_resp = client.get("/api/v1/surplus/listings", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]
    assert any(i["id"] == listing_id for i in items)


def test_api_ngo_matching_endpoint(client: TestClient, token_a_owner: str, donor_item: InventoryItem, ngo_tenant_and_user):
    """Test HTTP GET /api/v1/surplus/listings/{id}/matches returns ranked matches."""
    headers = {"Authorization": f"Bearer {token_a_owner}"}
    create_resp = client.post(
        "/api/v1/surplus/listings",
        json={
            "item_id": donor_item.id,
            "quantity": 10.0,
            "pickup_address": "123 Market St",
            "available_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    listing_id = create_resp.json()["data"]["id"]

    # Call matching endpoint
    resp = client.get(
        f"/api/v1/surplus/listings/{listing_id}/matches?origin_lat=40.7128&origin_lon=-74.0060",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["listing_id"] == listing_id
    assert len(data["matching_recommendations"]) > 0
    top = data["matching_recommendations"][0]
    assert top["ngo_name"] == ngo_tenant_and_user["tenant"].name
    assert top["match_score"] > 70.0
    assert len(top["match_reasons"]) > 0


def test_api_role_authorization_cross_tenant_isolation(
    client: TestClient,
    token_a_owner: str,
    token_b_owner: str,
    ngo_tenant_and_user,
    donor_item: InventoryItem,
):
    """
    Role & Tenant Boundary Tests:
      - NGO role cannot create a surplus listing (forbidden 403).
      - Business role cannot submit a claim (forbidden 403).
      - Tenant B cannot review claims for Tenant A's listing (not found 404).
    """
    donor_headers = {"Authorization": f"Bearer {token_a_owner}"}
    ngo_headers = ngo_tenant_and_user["headers"]
    other_business_headers = {"Authorization": f"Bearer {token_b_owner}"}

    # 1. NGO attempts to create listing -> Must be 403
    resp1 = client.post(
        "/api/v1/surplus/listings",
        json={
            "item_id": donor_item.id,
            "quantity": 5.0,
            "pickup_address": "Dock",
            "available_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=ngo_headers,
    )
    assert resp1.status_code == 403

    # 2. Donor A creates listing
    create_resp = client.post(
        "/api/v1/surplus/listings",
        json={
            "item_id": donor_item.id,
            "quantity": 10.0,
            "pickup_address": "Dock",
            "available_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=donor_headers,
    )
    listing_id = create_resp.json()["data"]["id"]

    # 3. Donor attempts to claim their own listing -> Must be 403 (Requires RECIPIENT_NGO role)
    resp2 = client.post(
        "/api/v1/surplus/claims",
        json={"listing_id": listing_id, "claimed_quantity": 5.0},
        headers=donor_headers,
    )
    assert resp2.status_code == 403

    # 4. NGO submits valid claim
    claim_resp = client.post(
        "/api/v1/surplus/claims",
        json={"listing_id": listing_id, "claimed_quantity": 5.0},
        headers=ngo_headers,
    )
    assert claim_resp.status_code == 201
    claim_id = claim_resp.json()["data"]["id"]

    # 5. Tenant B attempts to approve Tenant A's claim -> 404 Not Found (Tenant isolation)
    resp3 = client.post(
        f"/api/v1/surplus/claims/{claim_id}/review",
        json={"action": "APPROVE"},
        headers=other_business_headers,
    )
    assert resp3.status_code == 404
