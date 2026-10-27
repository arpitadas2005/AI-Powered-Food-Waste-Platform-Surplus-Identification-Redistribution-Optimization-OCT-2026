"""Milestone 3 - Phase 2 Test Suite: Claim Management, Pickup Scheduling & Notifications.

Validates:
  1. Pickup Scheduling Engine: window validation, food-safety deadline enforcement.
  2. Rejecting scheduling in past or beyond item expiry date.
  3. Rescheduling: window updates, increment counter, required reason, notifications.
  4. Milestones: READY_FOR_COLLECTION, COLLECTED, COMPLETED, and MISSED.
  5. Atomic stock deduction on handover completion via DONATION_DISPATCH idempotency.
  6. Cancellation cascades (cancelling listing/claim cancels schedule).
  7. In-App Notifications: creation, scoped listing, single read, and bulk mark_all_read.
  8. REST API Endpoints with role-based access control and tenant isolation.
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
    PickupSchedule,
    PickupScheduleStatus,
    SurplusClaim,
    SurplusListing,
    SurplusNotification,
    SurplusStatus,
)
from backend.app.models.tenant import BusinessType, Tenant
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.models.user import User, UserRole
from backend.app.schemas.surplus import (
    PickupScheduleBase,
    PickupScheduleCreate,
    PickupScheduleReschedule,
    SurplusClaimCreate,
    SurplusListingCreate,
)
from backend.app.services.surplus_service import (
    ClaimNotFoundError,
    ExcessiveClaimError,
    FoodSafetyValidationError,
    InvalidListingStateError,
    InvalidPickupScheduleStateError,
    InvalidPickupWindowError,
    PickupScheduleNotFoundError,
    cancel_surplus_claim,
    cancel_surplus_listing,
    complete_surplus_transfer,
    confirm_pickup_collection,
    create_or_schedule_pickup,
    create_surplus_claim,
    create_surplus_listing,
    get_pickup_schedule_by_claim_id,
    list_pickup_schedules,
    list_surplus_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    mark_pickup_missed,
    mark_pickup_ready,
    reschedule_pickup,
    review_surplus_claim,
    serialize_claim_response,
    serialize_pickup_schedule_response,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def ngo_fixture(db_session: Session):
    """Fixture creating an authorized NGO tenant and user."""
    ngo_tenant = Tenant(
        id="tenant_ngo_m3p2",
        name="Harbor Community Kitchen",
        slug="harbor-kitchen",
        business_type=BusinessType.NGO_RECIPIENT.value,
        contact_email="logistics@harborkitchen.org",
        phone="+1-555-4321",
        address="78 River Road, Boston, MA",
        timezone="America/New_York",
        currency="USD",
        is_active=True,
    )
    db_session.add(ngo_tenant)
    db_session.flush()

    ngo_user = User(
        id="user_ngo_m3p2",
        tenant_id=ngo_tenant.id,
        email="coordinator@harborkitchen.org",
        hashed_password=get_password_hash("HarborPass123!"),
        full_name="Elena Logistics",
        role=UserRole.RECIPIENT_NGO.value,
        is_active=True,
    )
    db_session.add(ngo_user)
    db_session.flush()

    ngo_profile = NgoProfile(
        id="profile_harbor_m3p2",
        tenant_id=ngo_tenant.id,
        organization_type=OrganizationType.SOUP_KITCHEN.value,
        is_verified=True,
        verification_date=datetime.now(timezone.utc),
        contact_person="Elena Logistics",
        contact_phone="+1-555-4321",
        contact_email="coordinator@harborkitchen.org",
        address="78 River Road, Boston, MA",
        latitude=42.3601,
        longitude=-71.0589,
        service_radius_km=25.0,
        accepted_categories=json.dumps(["Produce", "Bakery", "Dairy"]),
        storage_facilities=json.dumps(["AMBIENT", "REFRIGERATED"]),
        max_capacity_units=600.0,
        operating_hours="07:00 - 19:00",
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
def active_listing_and_approved_claim(
    db_session: Session,
    tenant_a: Tenant,
    user_a_owner: User,
    ngo_fixture: dict,
):
    """
    Creates an active surplus listing on Tenant A (expiry 3 days from now)
    and an approved claim of 20 units by Harbor Community Kitchen.
    """
    today = date.today()
    item = InventoryItem(
        id="item_fresh_apples_m3p2",
        tenant_id=tenant_a.id,
        category_id="cat_dairy_eggs",
        name="Fresh Honeycrisp Apples",
        sku="PRD-APP-02",
        current_quantity=100.0,
        unit="kg",
        cost_per_unit=1.50,
        selling_price=3.50,
        purchase_date=today - timedelta(days=2),
        expiry_date=today + timedelta(days=3),
        storage_requirement="AMBIENT",
        is_active=True,
    )
    db_session.add(item)
    db_session.commit()

    listing_in = SurplusListingCreate(
        item_id=item.id,
        title="Honeycrisp Apples Surplus Crate",
        quantity=40.0,
        pickup_address="45 Market St, Warehouse Dock 4",
        pickup_instructions="Ring buzzer at Bay 2",
        storage_requirement="AMBIENT",
        available_until=datetime.now(timezone.utc) + timedelta(days=2, hours=22),
    )
    listing = create_surplus_listing(
        db=db_session,
        tenant_id=tenant_a.id,
        user_id=user_a_owner.id,
        listing_in=listing_in,
    )

    # NGO requests 20 kg
    claim_in = SurplusClaimCreate(
        listing_id=listing.id,
        claimed_quantity=20.0,
        notes="Pick up for soup kitchen dinner service",
    )
    claim = create_surplus_claim(
        db=db_session,
        ngo_tenant_id=ngo_fixture["tenant"].id,
        user_id=ngo_fixture["user"].id,
        claim_in=claim_in,
    )

    # Donor approves claim
    reviewed_claim = review_surplus_claim(
        db=db_session,
        donor_tenant_id=tenant_a.id,
        reviewer_user_id=user_a_owner.id,
        claim_id=claim.id,
        action="APPROVE",
    )

    return {
        "item": item,
        "listing": listing,
        "claim": reviewed_claim,
        "donor_tenant": tenant_a,
        "donor_user": user_a_owner,
        "ngo_tenant": ngo_fixture["tenant"],
        "ngo_user": ngo_fixture["user"],
    }


# -----------------------------------------------------------------------------
# 1. Pickup Scheduling Engine & Validation Tests
# -----------------------------------------------------------------------------

def test_schedule_pickup_window_success(db_session: Session, active_listing_and_approved_claim: dict):
    """
    Verifies successful pickup scheduling within valid window before food expiry.
    Confirms audit event and counterpart notification.
    """
    data = active_listing_and_approved_claim
    claim = data["claim"]
    ngo = data["ngo_user"]
    ngo_tenant = data["ngo_tenant"]

    target_date = date.today() + timedelta(days=1)
    start_dt = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    end_dt = start_dt + timedelta(hours=3)

    schedule_in = PickupScheduleCreate(
        claim_id=claim.id,
        pickup_date=target_date,
        pickup_start_time=start_dt,
        pickup_end_time=end_dt,
        pickup_location="45 Market St, Bay 2",
        pickup_instructions="Van plate XYZ-987",
        vehicle_type="VAN",
        driver_name="Elena Logistics",
        driver_phone="+1-555-4321",
    )

    schedule = create_or_schedule_pickup(
        db=db_session,
        requesting_tenant_id=ngo_tenant.id,
        user_id=ngo.id,
        schedule_in=schedule_in,
    )

    assert schedule.id is not None
    assert schedule.status == PickupScheduleStatus.SCHEDULED.value
    assert schedule.claim_id == claim.id
    assert schedule.rescheduled_count == 0
    assert schedule.vehicle_type == "VAN"

    # Notification sent to donor business
    notif = (
        db_session.execute(
            select(SurplusNotification).where(
                SurplusNotification.tenant_id == data["donor_tenant"].id,
                SurplusNotification.notification_type == "PICKUP_SCHEDULED",
            )
        )
        .scalars()
        .first()
    )
    assert notif is not None
    assert "Elena Logistics" not in notif.message or "scheduled pickup" in notif.message

    # Audit log recorded
    audit = (
        db_session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == AuditEventType.SURPLUS_PICKUP_SCHEDULE.value,
                AuditEvent.resource_id == schedule.id,
            )
        )
        .scalars()
        .first()
    )
    assert audit is not None


def test_schedule_pickup_fails_when_past_window(db_session: Session, active_listing_and_approved_claim: dict):
    """Verifies that scheduling in the past is rejected."""
    data = active_listing_and_approved_claim
    claim = data["claim"]
    ngo_tenant = data["ngo_tenant"]

    past_start = datetime.now(timezone.utc) - timedelta(hours=5)
    past_end = datetime.now(timezone.utc) - timedelta(hours=2)

    schedule_in = PickupScheduleCreate(
        claim_id=claim.id,
        pickup_date=date.today() - timedelta(days=1),
        pickup_start_time=past_start,
        pickup_end_time=past_end,
    )

    with pytest.raises(InvalidPickupWindowError, match="past"):
        create_or_schedule_pickup(
            db=db_session,
            requesting_tenant_id=ngo_tenant.id,
            user_id=data["ngo_user"].id,
            schedule_in=schedule_in,
        )


def test_schedule_pickup_fails_after_item_expiry(db_session: Session, active_listing_and_approved_claim: dict):
    """
    Food safety rule: Pickup cannot be scheduled after the food item has expired.
    Item expires in 3 days; scheduling for day 4 must be rejected.
    """
    data = active_listing_and_approved_claim
    claim = data["claim"]
    ngo_tenant = data["ngo_tenant"]

    post_expiry_date = date.today() + timedelta(days=4)
    post_expiry_start = datetime.now(timezone.utc) + timedelta(days=4, hours=1)
    post_expiry_end = post_expiry_start + timedelta(hours=2)

    schedule_in = PickupScheduleCreate(
        claim_id=claim.id,
        pickup_date=post_expiry_date,
        pickup_start_time=post_expiry_start,
        pickup_end_time=post_expiry_end,
    )

    with pytest.raises(InvalidPickupWindowError, match="extends past item expiry date"):
        create_or_schedule_pickup(
            db=db_session,
            requesting_tenant_id=ngo_tenant.id,
            user_id=data["ngo_user"].id,
            schedule_in=schedule_in,
        )


# -----------------------------------------------------------------------------
# 2. Rescheduling & Milestone Transitions
# -----------------------------------------------------------------------------

def test_reschedule_pickup_increments_counter_and_stores_reason(
    db_session: Session, active_listing_and_approved_claim: dict
):
    """
    Tests rescheduling an active pickup window:
      - Validates new window
      - Increments rescheduled_count
      - Stores reason
      - Notifies counterpart
    """
    data = active_listing_and_approved_claim
    claim = data["claim"]
    ngo_tenant = data["ngo_tenant"]
    ngo_user = data["ngo_user"]

    # Initial schedule on day 1
    start_dt = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    end_dt = start_dt + timedelta(hours=2)
    create_or_schedule_pickup(
        db=db_session,
        requesting_tenant_id=ngo_tenant.id,
        user_id=ngo_user.id,
        schedule_in=PickupScheduleCreate(
            claim_id=claim.id,
            pickup_date=date.today() + timedelta(days=1),
            pickup_start_time=start_dt,
            pickup_end_time=end_dt,
        ),
    )

    # Reschedule to day 2 due to van delay
    new_date = date.today() + timedelta(days=2)
    new_start = datetime.now(timezone.utc) + timedelta(days=2, hours=3)
    new_end = new_start + timedelta(hours=2)

    reschedule_in = PickupScheduleReschedule(
        pickup_date=new_date,
        pickup_start_time=new_start,
        pickup_end_time=new_end,
        rescheduled_reason="Driver vehicle maintenance delay",
        driver_name="Elena Sub-Driver",
    )

    updated_schedule = reschedule_pickup(
        db=db_session,
        requesting_tenant_id=ngo_tenant.id,
        user_id=ngo_user.id,
        claim_id=claim.id,
        reschedule_in=reschedule_in,
    )

    assert updated_schedule.status == PickupScheduleStatus.RESCHEDULED.value
    assert updated_schedule.rescheduled_count == 1
    assert updated_schedule.rescheduled_reason == "Driver vehicle maintenance delay"
    assert updated_schedule.driver_name == "Elena Sub-Driver"

    # Notification sent to donor
    notif = (
        db_session.execute(
            select(SurplusNotification).where(
                SurplusNotification.tenant_id == data["donor_tenant"].id,
                SurplusNotification.notification_type == "PICKUP_RESCHEDULED",
            )
        )
        .scalars()
        .first()
    )
    assert notif is not None
    assert "Driver vehicle maintenance delay" in notif.message


def test_full_pickup_lifecycle_ready_collect_and_complete(
    db_session: Session, active_listing_and_approved_claim: dict
):
    """
    End-to-end milestone progression:
      1. SCHEDULED -> 2. READY_FOR_COLLECTION -> 3. COLLECTED -> 4. COMPLETED
    Verifies atomic stock deduction of claimed quantity from physical inventory.
    """
    data = active_listing_and_approved_claim
    claim = data["claim"]
    donor_tenant = data["donor_tenant"]
    donor_user = data["donor_user"]
    ngo_tenant = data["ngo_tenant"]
    item = data["item"]

    initial_qty = float(item.current_quantity)
    claimed_qty = float(claim.claimed_quantity)

    # 1. Schedule
    start_dt = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    end_dt = start_dt + timedelta(hours=2)
    create_or_schedule_pickup(
        db=db_session,
        requesting_tenant_id=ngo_tenant.id,
        user_id=data["ngo_user"].id,
        schedule_in=PickupScheduleCreate(
            claim_id=claim.id,
            pickup_date=date.today() + timedelta(days=1),
            pickup_start_time=start_dt,
            pickup_end_time=end_dt,
        ),
    )

    # 2. Donor marks READY_FOR_COLLECTION
    ready_schedule = mark_pickup_ready(
        db=db_session,
        donor_tenant_id=donor_tenant.id,
        user_id=donor_user.id,
        claim_id=claim.id,
    )
    assert ready_schedule.status == PickupScheduleStatus.READY_FOR_COLLECTION.value
    assert ready_schedule.ready_at is not None
    db_session.refresh(claim)
    assert claim.status == ClaimStatus.READY_FOR_PICKUP.value

    # 3. NGO confirms COLLECTED (handover in transit)
    collected_schedule = confirm_pickup_collection(
        db=db_session,
        requesting_tenant_id=ngo_tenant.id,
        user_id=data["ngo_user"].id,
        claim_id=claim.id,
    )
    assert collected_schedule.status == PickupScheduleStatus.COLLECTED.value
    assert collected_schedule.collected_at is not None
    db_session.refresh(claim)
    assert claim.status == ClaimStatus.PICKED_UP.value

    # 4. Donor marks COMPLETE
    completed_claim, updated_item = complete_surplus_transfer(
        db=db_session,
        donor_tenant_id=donor_tenant.id,
        user_id=donor_user.id,
        claim_id=claim.id,
    )
    assert completed_claim.status == ClaimStatus.COMPLETED.value
    db_session.refresh(ready_schedule)
    assert ready_schedule.status == PickupScheduleStatus.COMPLETED.value
    assert ready_schedule.completed_at is not None

    # Verify physical stock deducted via DONATION_DISPATCH
    assert float(updated_item.current_quantity) == initial_qty - claimed_qty

    stock_tx = (
        db_session.execute(
            select(StockTransaction).where(
                StockTransaction.item_id == item.id,
                StockTransaction.transaction_type == TransactionType.DONATION_DISPATCH.value,
            )
        )
        .scalars()
        .first()
    )
    assert stock_tx is not None
    assert float(stock_tx.quantity_change) == -claimed_qty


def test_mark_pickup_missed_when_volunteer_fails_to_arrive(
    db_session: Session, active_listing_and_approved_claim: dict
):
    """Tests donor marking a scheduled pickup as MISSED."""
    data = active_listing_and_approved_claim
    claim = data["claim"]
    donor_tenant = data["donor_tenant"]
    donor_user = data["donor_user"]

    start_dt = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    end_dt = start_dt + timedelta(hours=2)
    create_or_schedule_pickup(
        db=db_session,
        requesting_tenant_id=data["ngo_tenant"].id,
        user_id=data["ngo_user"].id,
        schedule_in=PickupScheduleCreate(
            claim_id=claim.id,
            pickup_date=date.today() + timedelta(days=1),
            pickup_start_time=start_dt,
            pickup_end_time=end_dt,
        ),
    )

    missed_schedule = mark_pickup_missed(
        db=db_session,
        donor_tenant_id=donor_tenant.id,
        user_id=donor_user.id,
        claim_id=claim.id,
        reason="No show by 18:00 window deadline",
    )

    assert missed_schedule.status == PickupScheduleStatus.MISSED.value
    assert missed_schedule.missed_at is not None
    assert missed_schedule.cancellation_reason == "No show by 18:00 window deadline"

    # In-app notification sent to NGO
    notif = (
        db_session.execute(
            select(SurplusNotification).where(
                SurplusNotification.tenant_id == data["ngo_tenant"].id,
                SurplusNotification.notification_type == "PICKUP_MISSED",
            )
        )
        .scalars()
        .first()
    )
    assert notif is not None
    assert "No show by 18:00 window deadline" in notif.message


def test_cancel_claim_cascades_cancellation_to_pickup_schedule(
    db_session: Session, active_listing_and_approved_claim: dict
):
    """Cancelling a claim automatically marks any active pickup schedule as CANCELLED."""
    data = active_listing_and_approved_claim
    claim = data["claim"]
    ngo_tenant = data["ngo_tenant"]

    start_dt = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    end_dt = start_dt + timedelta(hours=2)
    schedule = create_or_schedule_pickup(
        db=db_session,
        requesting_tenant_id=ngo_tenant.id,
        user_id=data["ngo_user"].id,
        schedule_in=PickupScheduleCreate(
            claim_id=claim.id,
            pickup_date=date.today() + timedelta(days=1),
            pickup_start_time=start_dt,
            pickup_end_time=end_dt,
        ),
    )
    assert schedule.status == PickupScheduleStatus.SCHEDULED.value

    # NGO cancels the claim
    cancel_surplus_claim(
        db=db_session,
        requesting_tenant_id=ngo_tenant.id,
        user_id=data["ngo_user"].id,
        claim_id=claim.id,
        reason="Volunteer driver unavailable",
    )

    db_session.refresh(schedule)
    assert schedule.status == PickupScheduleStatus.CANCELLED.value
    assert "Volunteer driver unavailable" in (schedule.cancellation_reason or "")


def test_cancel_listing_cascades_cancellation_to_pickup_schedules(
    db_session: Session, active_listing_and_approved_claim: dict
):
    """Cancelling a donor listing automatically cascades cancellation to all active pickup schedules."""
    data = active_listing_and_approved_claim
    listing = data["listing"]
    claim = data["claim"]
    donor_tenant = data["donor_tenant"]
    donor_user = data["donor_user"]

    start_dt = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    end_dt = start_dt + timedelta(hours=2)
    schedule = create_or_schedule_pickup(
        db=db_session,
        requesting_tenant_id=data["ngo_tenant"].id,
        user_id=data["ngo_user"].id,
        schedule_in=PickupScheduleCreate(
            claim_id=claim.id,
            pickup_date=date.today() + timedelta(days=1),
            pickup_start_time=start_dt,
            pickup_end_time=end_dt,
        ),
    )

    cancel_surplus_listing(
        db=db_session,
        tenant_id=donor_tenant.id,
        user_id=donor_user.id,
        listing_id=listing.id,
        reason="Kitchen storage refrigeration breakdown",
    )

    db_session.refresh(schedule)
    assert schedule.status == PickupScheduleStatus.CANCELLED.value
    assert "Listing cancelled by donor" in (schedule.cancellation_reason or "")


# -----------------------------------------------------------------------------
# 3. Notification Queries & Bulk Mark-Read
# -----------------------------------------------------------------------------

def test_notifications_scoped_and_bulk_mark_read(
    db_session: Session, active_listing_and_approved_claim: dict
):
    """Tests in-app notification listing and bulk read actions."""
    data = active_listing_and_approved_claim
    ngo_tenant = data["ngo_tenant"]

    # Create 3 unread notifications for NGO
    for i in range(3):
        n = SurplusNotification(
            tenant_id=ngo_tenant.id,
            title=f"Notification #{i}",
            message=f"Test message body {i}",
            notification_type="SYSTEM_TEST",
            is_read=False,
        )
        db_session.add(n)
    db_session.commit()

    unread_notifs = list_surplus_notifications(
        db=db_session, tenant_id=ngo_tenant.id, unread_only=True
    )
    assert len(unread_notifs) >= 3

    # Bulk mark read
    count = mark_all_notifications_read(db=db_session, tenant_id=ngo_tenant.id)
    assert count >= 3

    # Verify zero unread remaining
    unread_after = list_surplus_notifications(
        db=db_session, tenant_id=ngo_tenant.id, unread_only=True
    )
    assert len(unread_after) == 0


# -----------------------------------------------------------------------------
# 4. REST API Endpoint Tests & Security Boundaries
# -----------------------------------------------------------------------------

def test_api_schedule_reschedule_and_milestones(
    client: TestClient,
    active_listing_and_approved_claim: dict,
    token_a_owner: str,
    ngo_fixture: dict,
):
    """
    Tests the complete API flow:
      1. POST /claims/{id}/schedule (by NGO)
      2. POST /claims/{id}/reschedule (by NGO)
      3. POST /claims/{id}/ready (by Donor)
      4. POST /claims/{id}/collect (by NGO)
      5. POST /claims/{id}/complete (by Donor)
      6. GET /pickups (Paginated query)
      7. POST /notifications/read-all
    """
    data = active_listing_and_approved_claim
    claim_id = data["claim"].id
    ngo_headers = ngo_fixture["headers"]
    donor_headers = {"Authorization": f"Bearer {token_a_owner}"}

    # 1. Schedule Pickup via API
    target_date = (date.today() + timedelta(days=1)).isoformat()
    start_dt = (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).isoformat()
    end_dt = (datetime.now(timezone.utc) + timedelta(days=1, hours=4)).isoformat()

    schedule_payload = {
        "pickup_date": target_date,
        "pickup_start_time": start_dt,
        "pickup_end_time": end_dt,
        "pickup_location": "Dock 4, Bay 2",
        "vehicle_type": "VAN",
        "driver_name": "Elena Driver",
        "driver_phone": "+1-555-4321",
    }

    res = client.post(
        f"/api/v1/surplus/claims/{claim_id}/schedule",
        headers=ngo_headers,
        json=schedule_payload,
    )
    assert res.status_code == 201, res.text
    sched_data = res.json()["data"]
    assert sched_data["status"] == "SCHEDULED"
    assert sched_data["driver_name"] == "Elena Driver"

    # 2. Reschedule Pickup via API
    resched_date = (date.today() + timedelta(days=2)).isoformat()
    resched_start = (datetime.now(timezone.utc) + timedelta(days=2, hours=1)).isoformat()
    resched_end = (datetime.now(timezone.utc) + timedelta(days=2, hours=3)).isoformat()

    resched_payload = {
        "pickup_date": resched_date,
        "pickup_start_time": resched_start,
        "pickup_end_time": resched_end,
        "rescheduled_reason": "Traffic delay on highway",
        "driver_name": "Elena Driver",
    }
    res = client.post(
        f"/api/v1/surplus/claims/{claim_id}/reschedule",
        headers=ngo_headers,
        json=resched_payload,
    )
    assert res.status_code == 200, res.text
    resched_data = res.json()["data"]
    assert resched_data["status"] == "RESCHEDULED"
    assert resched_data["rescheduled_count"] == 1

    # 3. Mark Ready for Collection via Donor API
    res = client.post(
        f"/api/v1/surplus/claims/{claim_id}/ready",
        headers=donor_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "READY_FOR_COLLECTION"

    # 4. Confirm Collection Underway via NGO API
    res = client.post(
        f"/api/v1/surplus/claims/{claim_id}/collect",
        headers=ngo_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "COLLECTED"

    # 5. Complete Handover via Donor API
    res = client.post(
        f"/api/v1/surplus/claims/{claim_id}/complete",
        headers=donor_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "COMPLETED"

    # 6. Query Pickups API
    res = client.get("/api/v1/surplus/pickups", headers=ngo_headers)
    assert res.status_code == 200, res.text
    pickups = res.json()["data"]
    assert len(pickups) >= 1
    assert pickups[0]["claim_id"] == claim_id

    # 7. Bulk Read Notifications API
    res = client.post("/api/v1/surplus/notifications/read-all", headers=ngo_headers)
    assert res.status_code == 200, res.text
    assert isinstance(res.json()["data"], int)


def test_api_cross_tenant_isolation_and_permissions(
    client: TestClient,
    active_listing_and_approved_claim: dict,
    ngo_fixture: dict,
    user_b_owner: User,
    tenant_b: Tenant,
):
    """
    Verifies strict tenant isolation:
      - Tenant B (an unrelated business) cannot view, schedule, or modify claims/pickups for Tenant A or Harbor NGO.
    """
    data = active_listing_and_approved_claim
    claim_id = data["claim"].id

    # Schedule pickup first
    start_dt = (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).isoformat()
    end_dt = (datetime.now(timezone.utc) + timedelta(days=1, hours=4)).isoformat()
    client.post(
        f"/api/v1/surplus/claims/{claim_id}/schedule",
        headers=ngo_fixture["headers"],
        json={
            "pickup_date": (date.today() + timedelta(days=1)).isoformat(),
            "pickup_start_time": start_dt,
            "pickup_end_time": end_dt,
        },
    )

    # Token for unrelated Tenant B
    token_b = create_access_token(
        subject=user_b_owner.id,
        tenant_id=tenant_b.id,
        role=user_b_owner.role,
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant B tries to get pickup schedule for Tenant A's claim -> 404
    res = client.get(
        f"/api/v1/surplus/claims/{claim_id}/schedule",
        headers=headers_b,
    )
    assert res.status_code == 404

    # Tenant B tries to mark ready -> 404
    res = client.post(
        f"/api/v1/surplus/claims/{claim_id}/ready",
        headers=headers_b,
    )
    assert res.status_code == 404
