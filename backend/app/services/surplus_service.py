"""Surplus Food Listings and NGO Claim Allocation Service (Milestone 3 - Phase 1).

Orchestrates the lifecycle of surplus food donations:
  1. Business Listing Creation with Food Safety and Inventory Earmarking
  2. Oversubscription Prevention and Quantity Reconciliation
  3. Claim Allocation, Approval, Rejection, and Cancellation
  4. Physical Transfer Completion with Immutable Ledger Stock Deduction
  5. In-App Notifications for Donor Businesses and Recipient NGOs
  6. Operational Audit Trail
"""

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from backend.app.models.audit import AuditEvent, AuditEventType
from backend.app.models.inventory import InventoryItem, InventoryStatus
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
from backend.app.models.transaction import ReferenceType, TransactionType
from backend.app.models.user import User, UserRole
from backend.app.schemas.inventory import StockAdjustmentRequest
from backend.app.schemas.surplus import (
    NgoProfileCreate,
    NgoProfileResponse,
    NgoProfileUpdate,
    PickupMilestoneUpdate,
    PickupScheduleCreate,
    PickupScheduleReschedule,
    PickupScheduleResponse,
    SurplusClaimCreate,
    SurplusClaimResponse,
    SurplusListingCreate,
    SurplusListingResponse,
    SurplusListingUpdate,
    SurplusNotificationResponse,
)
from backend.app.services.inventory_service import (
    adjust_stock_quantity,
    calculate_days_to_expiry,
)


class SurplusServiceError(Exception):
    """Base exception for surplus listing and claim operations."""
    pass


class ListingNotFoundError(SurplusServiceError):
    """Raised when surplus listing does not exist or access is forbidden."""
    pass


class ClaimNotFoundError(SurplusServiceError):
    """Raised when surplus claim does not exist or access is forbidden."""
    pass


class FoodSafetyValidationError(SurplusServiceError):
    """Raised when item has expired or shelf-life fails donation safety criteria."""
    pass


class InsufficientSurplusStockError(SurplusServiceError):
    """Raised when requested listing exceeds available physical/unearmarked stock."""
    pass


class ExcessiveClaimError(SurplusServiceError):
    """Raised when claimed quantity exceeds remaining available listing quantity."""
    pass


class InvalidListingStateError(SurplusServiceError):
    """Raised when attempting an action on a listing in an invalid state."""
    pass


class PickupScheduleNotFoundError(SurplusServiceError):
    """Raised when pickup schedule does not exist or access is forbidden."""
    pass


class InvalidPickupScheduleStateError(SurplusServiceError):
    """Raised when attempting an action on a pickup schedule in an invalid state."""
    pass


class InvalidPickupWindowError(SurplusServiceError):
    """Raised when proposed pickup window violates listing availability or food shelf life."""
    pass


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def validate_pickup_window(
    pickup_start_time: datetime,
    pickup_end_time: datetime,
    listing: SurplusListing,
) -> None:
    """
    Validates that proposed pickup window is logically valid, in the future,
    and does not breach food safety expiration.
    """
    if pickup_start_time >= pickup_end_time:
        raise InvalidPickupWindowError("Pickup start time must be strictly before pickup end time.")

    now = datetime.now(timezone.utc)
    # 15-minute grace buffer for immediate pickup coordination
    if pickup_start_time < now - timedelta(minutes=15):
        raise InvalidPickupWindowError("Pickup window cannot be scheduled in the past.")

    # Expiry validation: food must not expire before pickup completion
    expiry_limit = datetime.combine(listing.expiry_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    if pickup_end_time > expiry_limit:
        raise InvalidPickupWindowError(
            f"Pickup window extends past item expiry date ({listing.expiry_date.isoformat()}). "
            f"Food cannot be collected after expiration."
        )

    # Listing availability window
    if listing.available_until:
        listing_until = listing.available_until
        if listing_until.tzinfo is None:
            listing_until = listing_until.replace(tzinfo=timezone.utc)
        if pickup_start_time > listing_until:
            raise InvalidPickupWindowError(
                f"Pickup window starts after listing available window ({listing.available_until.isoformat()})."
            )


def calculate_active_earmarked_quantity(
    db: Session, tenant_id: str, item_id: str, exclude_listing_id: Optional[str] = None
) -> float:
    """
    Computes total quantity currently earmarked across active surplus listings.
    Active statuses = AVAILABLE, RESERVED.
    """
    query = (
        select(func.coalesce(func.sum(SurplusListing.quantity), 0.0))
        .where(
            SurplusListing.tenant_id == tenant_id,
            SurplusListing.item_id == item_id,
            SurplusListing.status.in_([SurplusStatus.AVAILABLE.value, SurplusStatus.RESERVED.value]),
        )
    )
    if exclude_listing_id:
        query = query.where(SurplusListing.id != exclude_listing_id)
    return float(db.execute(query).scalar_one())


def calculate_claimed_quantity_for_listing(
    db: Session, listing_id: str, exclude_claim_id: Optional[str] = None
) -> float:
    """
    Computes total quantity locked by active claims against a listing.
    Active claim statuses = REQUESTED, APPROVED, COMPLETED.
    """
    query = (
        select(func.coalesce(func.sum(SurplusClaim.claimed_quantity), 0.0))
        .where(
            SurplusClaim.listing_id == listing_id,
            SurplusClaim.status.in_([
                ClaimStatus.REQUESTED.value,
                ClaimStatus.PENDING.value,
                ClaimStatus.APPROVED.value,
                ClaimStatus.ACCEPTED.value,
                ClaimStatus.READY_FOR_PICKUP.value,
                ClaimStatus.PICKED_UP.value,
                ClaimStatus.COMPLETED.value,
            ]),
        )
    )
    if exclude_claim_id:
        query = query.where(SurplusClaim.id != exclude_claim_id)
    return float(db.execute(query).scalar_one())


def record_audit(
    db: Session,
    tenant_id: Optional[str],
    user_id: Optional[str],
    event_type: AuditEventType,
    resource_type: str,
    resource_id: Optional[str],
    payload: Dict[str, Any],
) -> None:
    """Records an operational audit event."""
    from decimal import Decimal

    def json_default(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return str(obj)

    audit = AuditEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type.value,
        resource_type=resource_type,
        resource_id=resource_id,
        payload_summary=json.dumps(payload, default=json_default),
    )
    db.add(audit)


def create_notification(
    db: Session,
    tenant_id: str,
    user_id: Optional[str],
    title: str,
    message: str,
    notification_type: str,
    reference_id: Optional[str] = None,
) -> SurplusNotification:
    """Creates an in-app operational notification."""
    notif = SurplusNotification(
        tenant_id=tenant_id,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        reference_id=reference_id,
    )
    db.add(notif)
    return notif


# -----------------------------------------------------------------------------
# Listing Management
# -----------------------------------------------------------------------------

def create_surplus_listing(
    db: Session,
    tenant_id: str,
    user_id: str,
    listing_in: SurplusListingCreate,
) -> SurplusListing:
    """
    Creates a new surplus listing with food-safety and stock availability validation.
    Earmarks stock without prematurely deducting physical inventory until pickup.
    """
    # 1. Fetch and validate inventory item
    item = (
        db.execute(
            select(InventoryItem)
            .options(joinedload(InventoryItem.category))
            .where(
                InventoryItem.id == listing_in.item_id,
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.is_active == True,
            )
        )
        .scalars()
        .first()
    )
    if not item:
        raise ListingNotFoundError(f"Inventory item '{listing_in.item_id}' not found")

    # 2. Food Safety Check: Shelf-life validation
    today = datetime.now(timezone.utc).date()
    item_expiry = listing_in.expiry_date or item.expiry_date
    if item_expiry < today:
        raise FoodSafetyValidationError(
            f"Cannot list expired food. Item expired on {item_expiry}."
        )

    days_left = (item_expiry - today).days
    if days_left == 0:
        # Check available_until window
        now_utc = datetime.now(timezone.utc)
        if listing_in.available_until <= now_utc:
            raise FoodSafetyValidationError(
                "Donation window 'available_until' must be in the future."
            )

    # 3. Oversubscription Check
    already_earmarked = calculate_active_earmarked_quantity(db, tenant_id, item.id)
    available_to_list = float(item.current_quantity) - already_earmarked

    if listing_in.quantity > available_to_list:
        raise InsufficientSurplusStockError(
            f"Requested listing quantity ({listing_in.quantity:.2f} {item.unit}) "
            f"exceeds available unearmarked inventory ({available_to_list:.2f} {item.unit}). "
            f"Physical on-hand: {item.current_quantity:.2f}, already earmarked: {already_earmarked:.2f}."
        )

    # 4. Resolve default metadata
    unit = listing_in.unit or item.unit
    storage = listing_in.storage_requirement or item.storage_requirement or "AMBIENT"
    title = listing_in.title or f"Surplus {item.name} ({listing_in.quantity:.0f} {unit})"
    available_from = listing_in.available_from or datetime.now(timezone.utc)

    # 5. Create SurplusListing record
    listing = SurplusListing(
        tenant_id=tenant_id,
        item_id=item.id,
        title=title,
        quantity=listing_in.quantity,
        unit=unit,
        expiry_date=item_expiry,
        storage_requirement=storage.upper(),
        status=listing_in.status or SurplusStatus.AVAILABLE.value,
        pickup_address=listing_in.pickup_address,
        pickup_instructions=listing_in.pickup_instructions,
        description=listing_in.description,
        available_from=available_from,
        available_until=listing_in.available_until,
        created_by_user_id=user_id,
    )
    db.add(listing)
    db.flush()

    # 6. Audit Logging
    record_audit(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_LISTING_CREATE,
        resource_type="SurplusListing",
        resource_id=listing.id,
        payload={
            "item_id": item.id,
            "product_name": item.name,
            "quantity": listing.quantity,
            "unit": listing.unit,
            "available_until": listing.available_until.isoformat(),
        },
    )

    db.commit()
    db.refresh(listing)
    return listing


def update_surplus_listing(
    db: Session,
    tenant_id: str,
    user_id: str,
    listing_id: str,
    update_in: SurplusListingUpdate,
) -> SurplusListing:
    """Updates an active or draft surplus listing."""
    listing = (
        db.execute(
            select(SurplusListing)
            .options(joinedload(SurplusListing.item))
            .where(
                SurplusListing.id == listing_id,
                SurplusListing.tenant_id == tenant_id,
            )
        )
        .scalars()
        .first()
    )
    if not listing:
        raise ListingNotFoundError(f"Surplus listing '{listing_id}' not found")

    if listing.status not in (SurplusStatus.AVAILABLE.value, SurplusStatus.DRAFT.value):
        raise InvalidListingStateError(
            f"Cannot edit listing in state '{listing.status}'"
        )

    # If updating quantity, check availability
    if update_in.quantity is not None and update_in.quantity != float(listing.quantity):
        item = listing.item
        other_earmarked = calculate_active_earmarked_quantity(
            db, tenant_id, item.id, exclude_listing_id=listing.id
        )
        available_to_list = float(item.current_quantity) - other_earmarked

        # Also cannot reduce below already approved/requested claims
        claimed_qty = calculate_claimed_quantity_for_listing(db, listing.id)
        if update_in.quantity < claimed_qty:
            raise InsufficientSurplusStockError(
                f"Cannot decrease listing quantity to {update_in.quantity:.2f} below "
                f"already locked claims ({claimed_qty:.2f})."
            )

        if update_in.quantity > available_to_list:
            raise InsufficientSurplusStockError(
                f"Quantity {update_in.quantity:.2f} exceeds available inventory {available_to_list:.2f}."
            )
        listing.quantity = update_in.quantity

    if update_in.title is not None:
        listing.title = update_in.title
    if update_in.pickup_address is not None:
        listing.pickup_address = update_in.pickup_address
    if update_in.pickup_instructions is not None:
        listing.pickup_instructions = update_in.pickup_instructions
    if update_in.description is not None:
        listing.description = update_in.description
    if update_in.available_until is not None:
        listing.available_until = update_in.available_until
    if update_in.status is not None:
        listing.status = update_in.status

    record_audit(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_LISTING_UPDATE,
        resource_type="SurplusListing",
        resource_id=listing.id,
        payload=update_in.model_dump(exclude_unset=True),
    )

    db.commit()
    db.refresh(listing)
    return listing


def cancel_surplus_listing(
    db: Session,
    tenant_id: str,
    user_id: str,
    listing_id: str,
    reason: Optional[str] = None,
) -> SurplusListing:
    """
    Cancels an active surplus listing, releases all earmarked reservations,
    and notifies affected NGOs.
    """
    listing = (
        db.execute(
            select(SurplusListing)
            .options(
                joinedload(SurplusListing.claims),
                joinedload(SurplusListing.pickup_schedules),
            )
            .where(
                SurplusListing.id == listing_id,
                SurplusListing.tenant_id == tenant_id,
            )
        )
        .scalars()
        .first()
    )
    if not listing:
        raise ListingNotFoundError(f"Surplus listing '{listing_id}' not found")

    if listing.status in (SurplusStatus.COMPLETED.value, SurplusStatus.CANCELLED.value):
        raise InvalidListingStateError(
            f"Listing '{listing_id}' is already {listing.status}"
        )

    listing.status = SurplusStatus.CANCELLED.value

    # Auto-cancel active claims and notify recipient NGOs
    for claim in listing.claims:
        if claim.status in (
            ClaimStatus.REQUESTED.value,
            ClaimStatus.PENDING.value,
            ClaimStatus.APPROVED.value,
            ClaimStatus.ACCEPTED.value,
            ClaimStatus.READY_FOR_PICKUP.value,
        ):
            claim.status = ClaimStatus.CANCELLED.value
            claim.rejection_reason = f"Listing cancelled by donor: {reason or 'Inventory no longer available'}"
            create_notification(
                db=db,
                tenant_id=claim.ngo_tenant_id,
                user_id=claim.claimed_by_user_id,
                title="Donation Reservation Cancelled",
                message=f"Surplus listing '{listing.title}' was cancelled by the donor.",
                notification_type="CLAIM_CANCELLED",
                reference_id=claim.id,
            )

    # Auto-cancel any active pickup schedules
    for schedule in listing.pickup_schedules:
        if schedule.status in (
            PickupScheduleStatus.SCHEDULED.value,
            PickupScheduleStatus.RESCHEDULED.value,
            PickupScheduleStatus.READY_FOR_COLLECTION.value,
        ):
            schedule.status = PickupScheduleStatus.CANCELLED.value
            schedule.cancellation_reason = f"Listing cancelled by donor: {reason or 'Inventory no longer available'}"

    record_audit(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_LISTING_CANCEL,
        resource_type="SurplusListing",
        resource_id=listing.id,
        payload={"reason": reason},
    )

    db.commit()
    db.refresh(listing)
    return listing


def get_surplus_listing_by_id(
    db: Session,
    listing_id: str,
    requesting_tenant_id: Optional[str] = None,
    is_ngo: bool = False,
) -> SurplusListing:
    """
    Fetches a surplus listing with full item and category data.
    Cross-tenant rules:
      - Donor business users can view their own listings in any state.
      - NGO users can view any active or public listing (AVAILABLE, RESERVED, COMPLETED).
    """
    listing = (
        db.execute(
            select(SurplusListing)
            .options(
                joinedload(SurplusListing.item).joinedload(InventoryItem.category),
                joinedload(SurplusListing.claims).joinedload(SurplusClaim.ngo_tenant),
            )
            .where(SurplusListing.id == listing_id)
        )
        .scalars()
        .first()
    )
    if not listing:
        raise ListingNotFoundError(f"Surplus listing '{listing_id}' not found")

    if not is_ngo and requesting_tenant_id and listing.tenant_id != requesting_tenant_id:
        raise ListingNotFoundError(f"Surplus listing '{listing_id}' not found")

    return listing


def list_surplus_listings(
    db: Session,
    tenant_id: Optional[str] = None,
    is_ngo: bool = False,
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    storage_requirement: Optional[str] = None,
    min_days_to_expiry: Optional[float] = None,
    page: int = 1,
    size: int = 50,
) -> Tuple[List[SurplusListing], int]:
    """
    Lists surplus items with tenant-aware scoping.
    Donor businesses see their own inventory listings.
    NGO users browse all available platform donation listings.
    """
    query = select(SurplusListing).options(
        joinedload(SurplusListing.item).joinedload(InventoryItem.category),
        joinedload(SurplusListing.claims),
    )

    if not is_ngo and tenant_id:
        # Donor Business view: tenant's own listings
        query = query.where(SurplusListing.tenant_id == tenant_id)
        if status:
            query = query.where(SurplusListing.status == status.upper())
    else:
        # NGO Marketplace view: eligible active listings
        if status:
            query = query.where(SurplusListing.status == status.upper())
        else:
            query = query.where(
                SurplusListing.status.in_([
                    SurplusStatus.AVAILABLE.value,
                    SurplusStatus.RESERVED.value,
                ])
            )

    if category_id:
        query = query.join(SurplusListing.item).where(InventoryItem.category_id == category_id)

    if storage_requirement:
        query = query.where(
            SurplusListing.storage_requirement == storage_requirement.upper()
        )

    # Expiry window filter
    if min_days_to_expiry is not None:
        today = datetime.now(timezone.utc).date()
        target_date = today + timedelta(days=int(min_days_to_expiry))
        query = query.where(SurplusListing.expiry_date >= target_date)

    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar_one()

    # Sort: earliest expiring first
    query = query.order_by(SurplusListing.expiry_date.asc(), SurplusListing.created_at.desc())
    offset = (page - 1) * size
    items = db.execute(query.offset(offset).limit(size)).scalars().unique().all()

    return list(items), total


def serialize_listing_response(listing: SurplusListing, db: Session) -> SurplusListingResponse:
    """Helper to convert a SurplusListing model to SurplusListingResponse with remaining quantity."""
    item = listing.item
    category = item.category if item else None

    # Calculate remaining claimable quantity
    claimed_qty = calculate_claimed_quantity_for_listing(db, listing.id)
    remaining_qty = max(0.0, float(listing.quantity) - claimed_qty)

    days_to_exp = calculate_days_to_expiry(listing.expiry_date)

    return SurplusListingResponse(
        id=listing.id,
        tenant_id=listing.tenant_id,
        item_id=listing.item_id,
        title=listing.title or (item.name if item else "Surplus Food Item"),
        product_name=item.name if item else "Unknown Product",
        category_name=category.name if category else "Uncategorized",
        category_id=category.id if category else "",
        sku=item.sku if item else None,
        quantity=float(listing.quantity),
        remaining_claimable_quantity=round(remaining_qty, 2),
        unit=listing.unit,
        expiry_date=listing.expiry_date,
        days_to_expiry=days_to_exp,
        storage_requirement=listing.storage_requirement,
        status=listing.status,
        pickup_address=listing.pickup_address,
        pickup_instructions=listing.pickup_instructions,
        description=listing.description,
        available_from=listing.available_from,
        available_until=listing.available_until,
        claimed_by_tenant_id=listing.claimed_by_tenant_id,
        created_by_user_id=listing.created_by_user_id,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
        claims_count=len(listing.claims) if listing.claims else 0,
    )


# -----------------------------------------------------------------------------
# Claim & Reservation Workflow
# -----------------------------------------------------------------------------

def create_surplus_claim(
    db: Session,
    ngo_tenant_id: str,
    user_id: str,
    claim_in: SurplusClaimCreate,
) -> SurplusClaim:
    """
    Creates an NGO claim against an available surplus listing.
    Verifies that claimed quantity does not exceed remaining claimable balance.
    """
    listing = (
        db.execute(
            select(SurplusListing)
            .options(
                joinedload(SurplusListing.item),
                joinedload(SurplusListing.tenant),
            )
            .where(SurplusListing.id == claim_in.listing_id)
        )
        .scalars()
        .first()
    )
    if not listing:
        raise ListingNotFoundError(f"Surplus listing '{claim_in.listing_id}' not found")

    if listing.status != SurplusStatus.AVAILABLE.value:
        raise InvalidListingStateError(
            f"Listing is not currently available for claim (status: {listing.status})"
        )

    # Check remaining claimable balance
    already_claimed = calculate_claimed_quantity_for_listing(db, listing.id)
    remaining_qty = float(listing.quantity) - already_claimed

    if claim_in.claimed_quantity > remaining_qty:
        raise ExcessiveClaimError(
            f"Claim quantity ({claim_in.claimed_quantity:.2f} {listing.unit}) exceeds "
            f"remaining available quantity ({remaining_qty:.2f} {listing.unit})."
        )

    # Create Claim
    claim = SurplusClaim(
        listing_id=listing.id,
        ngo_tenant_id=ngo_tenant_id,
        claimed_by_user_id=user_id,
        claimed_quantity=claim_in.claimed_quantity,
        unit=listing.unit,
        status=ClaimStatus.REQUESTED.value,
        pickup_time=claim_in.pickup_time or claim_in.pickup_start_time,
        notes=claim_in.notes,
    )
    db.add(claim)
    db.flush()

    # Optional initial logistics pickup schedule proposal
    if claim_in.pickup_date and claim_in.pickup_start_time and claim_in.pickup_end_time:
        validate_pickup_window(claim_in.pickup_start_time, claim_in.pickup_end_time, listing)
        schedule = PickupSchedule(
            claim_id=claim.id,
            listing_id=listing.id,
            donor_tenant_id=listing.tenant_id,
            ngo_tenant_id=ngo_tenant_id,
            pickup_date=claim_in.pickup_date,
            pickup_start_time=claim_in.pickup_start_time,
            pickup_end_time=claim_in.pickup_end_time,
            pickup_location=listing.pickup_address,
            pickup_instructions=listing.pickup_instructions,
            vehicle_type=claim_in.vehicle_type,
            driver_name=claim_in.driver_name,
            driver_phone=claim_in.driver_phone,
            status=PickupScheduleStatus.SCHEDULED.value,
            scheduled_by_user_id=user_id,
        )
        db.add(schedule)

    # Notify donor business tenant
    ngo_tenant = db.execute(select(Tenant).where(Tenant.id == ngo_tenant_id)).scalar_one_or_none()
    ngo_name = ngo_tenant.name if ngo_tenant else "An NGO"

    create_notification(
        db=db,
        tenant_id=listing.tenant_id,
        user_id=listing.created_by_user_id,
        title="New Surplus Food Claim Request",
        message=f"{ngo_name} requested {claim.claimed_quantity:.1f} {claim.unit} of '{listing.title}'.",
        notification_type="CLAIM_REQUESTED",
        reference_id=claim.id,
    )

    record_audit(
        db=db,
        tenant_id=ngo_tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_CLAIM_REQUEST,
        resource_type="SurplusClaim",
        resource_id=claim.id,
        payload={
            "listing_id": listing.id,
            "claimed_quantity": claim.claimed_quantity,
            "unit": claim.unit,
            "donor_tenant_id": listing.tenant_id,
        },
    )

    db.commit()
    db.refresh(claim)
    return claim


def review_surplus_claim(
    db: Session,
    donor_tenant_id: str,
    reviewer_user_id: str,
    claim_id: str,
    action: str,  # 'APPROVE' or 'REJECT'
    rejection_reason: Optional[str] = None,
) -> SurplusClaim:
    """
    Donor business reviews an incoming claim request.
    On approval: transitions claim to APPROVED, and sets listing to RESERVED if fully allocated.
    On rejection: frees the allocation.
    """
    claim = (
        db.execute(
            select(SurplusClaim)
            .options(
                joinedload(SurplusClaim.listing).joinedload(SurplusListing.item),
                joinedload(SurplusClaim.ngo_tenant),
            )
            .where(SurplusClaim.id == claim_id)
        )
        .scalars()
        .first()
    )
    if not claim:
        raise ClaimNotFoundError(f"Surplus claim '{claim_id}' not found")

    listing = claim.listing
    if listing.tenant_id != donor_tenant_id:
        raise ClaimNotFoundError(f"Unauthorized review: claim does not belong to your organization")

    if claim.status not in (ClaimStatus.REQUESTED.value, ClaimStatus.PENDING.value):
        raise InvalidListingStateError(
            f"Cannot review claim with status '{claim.status}' (must be REQUESTED or PENDING)"
        )

    action_upper = action.upper().strip()

    if action_upper in ("APPROVE", "ACCEPT"):
        claim.status = ClaimStatus.APPROVED.value
        claim.reviewed_by_user_id = reviewer_user_id

        # Check total approved/requested quantity
        total_locked = calculate_claimed_quantity_for_listing(db, listing.id)
        if total_locked >= float(listing.quantity):
            listing.status = SurplusStatus.RESERVED.value
            listing.claimed_by_tenant_id = claim.ngo_tenant_id

        create_notification(
            db=db,
            tenant_id=claim.ngo_tenant_id,
            user_id=claim.claimed_by_user_id,
            title="Claim Request Approved!",
            message=f"Your claim for {claim.claimed_quantity:.1f} {claim.unit} of '{listing.title}' was approved. Please prepare for collection.",
            notification_type="CLAIM_APPROVED",
            reference_id=claim.id,
        )

        record_audit(
            db=db,
            tenant_id=donor_tenant_id,
            user_id=reviewer_user_id,
            event_type=AuditEventType.SURPLUS_CLAIM_APPROVE,
            resource_type="SurplusClaim",
            resource_id=claim.id,
            payload={"listing_id": listing.id, "claimed_quantity": claim.claimed_quantity},
        )

    elif action_upper == "REJECT":
        claim.status = ClaimStatus.REJECTED.value
        claim.rejection_reason = rejection_reason or "Declined by food donor"
        claim.reviewed_by_user_id = reviewer_user_id

        # If listing was RESERVED, reopen to AVAILABLE
        if listing.status == SurplusStatus.RESERVED.value:
            listing.status = SurplusStatus.AVAILABLE.value

        create_notification(
            db=db,
            tenant_id=claim.ngo_tenant_id,
            user_id=claim.claimed_by_user_id,
            title="Claim Request Declined",
            message=f"Your claim for '{listing.title}' was declined: {claim.rejection_reason}",
            notification_type="CLAIM_REJECTED",
            reference_id=claim.id,
        )

        record_audit(
            db=db,
            tenant_id=donor_tenant_id,
            user_id=reviewer_user_id,
            event_type=AuditEventType.SURPLUS_CLAIM_REJECT,
            resource_type="SurplusClaim",
            resource_id=claim.id,
            payload={"listing_id": listing.id, "rejection_reason": claim.rejection_reason},
        )
    else:
        raise ValueError("Invalid review action. Must be 'APPROVE' or 'REJECT'")

    db.commit()
    db.refresh(claim)
    return claim


def complete_surplus_transfer(
    db: Session,
    donor_tenant_id: str,
    user_id: str,
    claim_id: str,
) -> Tuple[SurplusClaim, InventoryItem]:
    """
    Executes physical donation pickup:
      1. Marks claim as COMPLETED.
      2. Automatically deducts inventory via adjust_stock_quantity with DONATION_DISPATCH.
      3. Verifies if entire listing is completed.
      4. Dispatches confirmation notifications and logs audit trail.
    """
    claim = (
        db.execute(
            select(SurplusClaim)
            .options(
                joinedload(SurplusClaim.listing).joinedload(SurplusListing.item),
                joinedload(SurplusClaim.ngo_tenant),
            )
            .where(SurplusClaim.id == claim_id)
        )
        .scalars()
        .first()
    )
    if not claim:
        raise ClaimNotFoundError(f"Surplus claim '{claim_id}' not found")

    listing = claim.listing
    if listing.tenant_id != donor_tenant_id:
        raise ClaimNotFoundError("Unauthorized: claim does not belong to your organization")

    if claim.status not in (
        ClaimStatus.APPROVED.value,
        ClaimStatus.ACCEPTED.value,
        ClaimStatus.READY_FOR_PICKUP.value,
        ClaimStatus.PICKED_UP.value,
        ClaimStatus.REQUESTED.value,
        ClaimStatus.PENDING.value,
    ):
        raise InvalidListingStateError(
            f"Cannot complete transfer for claim in state '{claim.status}'"
        )

    # Deduct physical inventory
    item = listing.item
    adj_request = StockAdjustmentRequest(
        quantity_delta=-float(claim.claimed_quantity),
        adjustment_type=TransactionType.DONATION_DISPATCH.value,
        reason=f"Surplus donation transfer to {claim.ngo_tenant.name if claim.ngo_tenant else 'NGO'}",
        reference_type=ReferenceType.DONATION_LISTING.value,
        reference_id=f"CLAIM:{claim.id}",
        idempotency_key=f"DISPATCH_{claim.id}",
    )

    updated_item, stock_tx = adjust_stock_quantity(
        db=db,
        tenant_id=donor_tenant_id,
        user_id=user_id,
        item_id=item.id,
        adj=adj_request,
    )

    # Update claim status
    claim.status = ClaimStatus.COMPLETED.value

    # Update linked pickup schedule if present
    schedule = (
        db.execute(select(PickupSchedule).where(PickupSchedule.claim_id == claim.id))
        .scalars()
        .first()
    )
    if schedule:
        schedule.status = PickupScheduleStatus.COMPLETED.value
        schedule.completed_at = datetime.now(timezone.utc)

    # Check if all listing claims are complete or if entire batch is handed over
    completed_qty = (
        db.execute(
            select(func.coalesce(func.sum(SurplusClaim.claimed_quantity), 0.0)).where(
                SurplusClaim.listing_id == listing.id,
                SurplusClaim.status == ClaimStatus.COMPLETED.value,
            )
        ).scalar_one()
    )

    if float(completed_qty) >= float(listing.quantity):
        listing.status = SurplusStatus.COMPLETED.value

    create_notification(
        db=db,
        tenant_id=claim.ngo_tenant_id,
        user_id=claim.claimed_by_user_id,
        title="Donation Handover Complete",
        message=f"Pickup confirmed for {claim.claimed_quantity:.1f} {claim.unit} of '{listing.title}'. Thank you for rescuing surplus food!",
        notification_type="DONATION_DISPATCHED",
        reference_id=claim.id,
    )

    record_audit(
        db=db,
        tenant_id=donor_tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_TRANSFER_COMPLETE,
        resource_type="SurplusClaim",
        resource_id=claim.id,
        payload={
            "listing_id": listing.id,
            "claimed_quantity": claim.claimed_quantity,
            "stock_transaction_id": stock_tx.id,
            "remaining_item_quantity": float(updated_item.current_quantity),
        },
    )

    db.commit()
    db.refresh(claim)
    return claim, updated_item


def cancel_surplus_claim(
    db: Session,
    requesting_tenant_id: str,
    user_id: str,
    claim_id: str,
    reason: Optional[str] = None,
) -> SurplusClaim:
    """Cancels a pending claim request and releases allocation."""
    claim = (
        db.execute(
            select(SurplusClaim)
            .options(joinedload(SurplusClaim.listing))
            .where(SurplusClaim.id == claim_id)
        )
        .scalars()
        .first()
    )
    if not claim:
        raise ClaimNotFoundError(f"Surplus claim '{claim_id}' not found")

    listing = claim.listing
    is_ngo_owner = claim.ngo_tenant_id == requesting_tenant_id
    is_donor_owner = listing.tenant_id == requesting_tenant_id

    if not (is_ngo_owner or is_donor_owner):
        raise ClaimNotFoundError("Unauthorized claim cancellation")

    if claim.status in (ClaimStatus.COMPLETED.value, ClaimStatus.CANCELLED.value):
        raise InvalidListingStateError(f"Claim is already {claim.status}")

    claim.status = ClaimStatus.CANCELLED.value
    claim.rejection_reason = reason or "Cancelled by user"

    # Auto-cancel linked pickup schedule
    schedule = (
        db.execute(select(PickupSchedule).where(PickupSchedule.claim_id == claim.id))
        .scalars()
        .first()
    )
    if schedule and schedule.status not in (
        PickupScheduleStatus.COMPLETED.value,
        PickupScheduleStatus.CANCELLED.value,
    ):
        schedule.status = PickupScheduleStatus.CANCELLED.value
        schedule.cancellation_reason = f"Claim cancelled: {claim.rejection_reason}"

    # If listing was RESERVED, reopen to AVAILABLE
    if listing.status == SurplusStatus.RESERVED.value:
        listing.status = SurplusStatus.AVAILABLE.value

    # Notify counterpart
    target_tenant_id = listing.tenant_id if is_ngo_owner else claim.ngo_tenant_id
    create_notification(
        db=db,
        tenant_id=target_tenant_id,
        user_id=None,
        title="Surplus Claim Cancelled",
        message=f"Claim on '{listing.title}' was cancelled: {claim.rejection_reason}",
        notification_type="CLAIM_CANCELLED",
        reference_id=claim.id,
    )

    record_audit(
        db=db,
        tenant_id=requesting_tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_CLAIM_CANCEL,
        resource_type="SurplusClaim",
        resource_id=claim.id,
        payload={"reason": claim.rejection_reason},
    )

    db.commit()
    db.refresh(claim)
    return claim


def list_claims_for_listing(
    db: Session,
    donor_tenant_id: str,
    listing_id: str,
) -> List[SurplusClaim]:
    """Lists all claims made against a donor's listing."""
    listing = (
        db.execute(
            select(SurplusListing).where(
                SurplusListing.id == listing_id,
                SurplusListing.tenant_id == donor_tenant_id,
            )
        )
        .scalars()
        .first()
    )
    if not listing:
        raise ListingNotFoundError(f"Listing '{listing_id}' not found")

    claims = (
        db.execute(
            select(SurplusClaim)
            .options(
                joinedload(SurplusClaim.ngo_tenant),
                joinedload(SurplusClaim.claimed_by_user),
                joinedload(SurplusClaim.listing),
                joinedload(SurplusClaim.pickup_schedule).joinedload(PickupSchedule.donor_tenant),
                joinedload(SurplusClaim.pickup_schedule).joinedload(PickupSchedule.ngo_tenant),
                joinedload(SurplusClaim.pickup_schedule).joinedload(PickupSchedule.scheduled_by_user),
            )
            .where(SurplusClaim.listing_id == listing_id)
            .order_by(SurplusClaim.created_at.desc())
        )
        .scalars()
        .all()
    )
    return list(claims)


def list_claims_for_ngo(
    db: Session,
    ngo_tenant_id: str,
    status: Optional[str] = None,
) -> List[SurplusClaim]:
    """Lists all claims made by an NGO organization."""
    query = (
        select(SurplusClaim)
        .options(
            joinedload(SurplusClaim.listing).joinedload(SurplusListing.item),
            joinedload(SurplusClaim.ngo_tenant),
            joinedload(SurplusClaim.claimed_by_user),
            joinedload(SurplusClaim.pickup_schedule).joinedload(PickupSchedule.donor_tenant),
            joinedload(SurplusClaim.pickup_schedule).joinedload(PickupSchedule.ngo_tenant),
            joinedload(SurplusClaim.pickup_schedule).joinedload(PickupSchedule.scheduled_by_user),
        )
        .where(SurplusClaim.ngo_tenant_id == ngo_tenant_id)
    )
    if status:
        query = query.where(SurplusClaim.status == status.upper())

    query = query.order_by(SurplusClaim.created_at.desc())
    claims = db.execute(query).scalars().all()
    return list(claims)


def serialize_pickup_schedule_response(schedule: PickupSchedule) -> PickupScheduleResponse:
    """Helper to convert PickupSchedule model to PickupScheduleResponse."""
    listing_title = schedule.listing.title if schedule.listing else "Surplus Food Item"
    donor_name = schedule.donor_tenant.name if schedule.donor_tenant else "Donor"
    ngo_name = schedule.ngo_tenant.name if schedule.ngo_tenant else "NGO"
    user_name = schedule.scheduled_by_user.full_name if schedule.scheduled_by_user else "User"

    return PickupScheduleResponse(
        id=schedule.id,
        claim_id=schedule.claim_id,
        listing_id=schedule.listing_id,
        listing_title=listing_title,
        donor_tenant_id=schedule.donor_tenant_id,
        donor_name=donor_name,
        ngo_tenant_id=schedule.ngo_tenant_id,
        ngo_name=ngo_name,
        pickup_date=schedule.pickup_date,
        pickup_start_time=schedule.pickup_start_time,
        pickup_end_time=schedule.pickup_end_time,
        pickup_location=schedule.pickup_location,
        pickup_instructions=schedule.pickup_instructions,
        vehicle_type=schedule.vehicle_type,
        driver_name=schedule.driver_name,
        driver_phone=schedule.driver_phone,
        status=schedule.status,
        scheduled_by_user_id=schedule.scheduled_by_user_id,
        scheduled_by_user_name=user_name,
        rescheduled_count=schedule.rescheduled_count,
        rescheduled_reason=schedule.rescheduled_reason,
        cancellation_reason=schedule.cancellation_reason,
        ready_at=schedule.ready_at,
        collected_at=schedule.collected_at,
        completed_at=schedule.completed_at,
        missed_at=schedule.missed_at,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def serialize_claim_response(claim: SurplusClaim) -> SurplusClaimResponse:
    """Helper to convert SurplusClaim to SurplusClaimResponse."""
    listing_title = claim.listing.title if claim.listing else "Food Surplus"
    ngo_name = claim.ngo_tenant.name if claim.ngo_tenant else "NGO"
    user_name = claim.claimed_by_user.full_name if claim.claimed_by_user else "Staff"

    schedule_resp = None
    if claim.pickup_schedule:
        schedule_resp = serialize_pickup_schedule_response(claim.pickup_schedule)

    return SurplusClaimResponse(
        id=claim.id,
        listing_id=claim.listing_id,
        listing_title=listing_title,
        ngo_tenant_id=claim.ngo_tenant_id,
        ngo_name=ngo_name,
        claimed_by_user_id=claim.claimed_by_user_id,
        claimed_by_user_name=user_name,
        claimed_quantity=float(claim.claimed_quantity),
        unit=claim.unit,
        status=claim.status,
        pickup_time=claim.pickup_time,
        notes=claim.notes,
        rejection_reason=claim.rejection_reason,
        reviewed_by_user_id=claim.reviewed_by_user_id,
        pickup_schedule=schedule_resp,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )


# -----------------------------------------------------------------------------
# NGO Profiles & Notifications
# -----------------------------------------------------------------------------

def get_or_create_ngo_profile(
    db: Session,
    tenant_id: str,
    defaults: Optional[NgoProfileCreate] = None,
) -> NgoProfile:
    """Retrieves an existing NGO profile or seeds a default initialized one."""
    profile = (
        db.execute(select(NgoProfile).where(NgoProfile.tenant_id == tenant_id))
        .scalars()
        .first()
    )
    if profile:
        return profile

    tenant = db.execute(select(Tenant).where(Tenant.id == tenant_id)).scalar_one_or_none()
    if not tenant:
        raise SurplusServiceError(f"Tenant '{tenant_id}' not found")

    if defaults:
        profile = NgoProfile(
            tenant_id=tenant_id,
            organization_type=defaults.organization_type,
            contact_person=defaults.contact_person,
            contact_phone=defaults.contact_phone,
            contact_email=defaults.contact_email,
            address=defaults.address,
            latitude=defaults.latitude,
            longitude=defaults.longitude,
            service_radius_km=defaults.service_radius_km,
            accepted_categories=json.dumps(defaults.accepted_categories),
            storage_facilities=json.dumps(defaults.storage_facilities),
            max_capacity_units=defaults.max_capacity_units,
            operating_hours=defaults.operating_hours,
        )
    else:
        profile = NgoProfile(
            tenant_id=tenant_id,
            organization_type=OrganizationType.FOOD_BANK.value,
            contact_person=tenant.name,
            contact_phone=tenant.phone or "Not provided",
            contact_email=tenant.contact_email,
            address=tenant.address or "Community Address",
            service_radius_km=25.0,
            accepted_categories=json.dumps(["ALL"]),
            storage_facilities=json.dumps(["AMBIENT"]),
            max_capacity_units=500.0,
            operating_hours="09:00 - 18:00",
        )

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_ngo_profile(
    db: Session,
    tenant_id: str,
    update_in: NgoProfileUpdate,
) -> NgoProfile:
    """Updates operational capabilities of an NGO profile."""
    profile = get_or_create_ngo_profile(db, tenant_id)

    if update_in.organization_type is not None:
        profile.organization_type = update_in.organization_type
    if update_in.contact_person is not None:
        profile.contact_person = update_in.contact_person
    if update_in.contact_phone is not None:
        profile.contact_phone = update_in.contact_phone
    if update_in.contact_email is not None:
        profile.contact_email = update_in.contact_email
    if update_in.address is not None:
        profile.address = update_in.address
    if update_in.latitude is not None:
        profile.latitude = update_in.latitude
    if update_in.longitude is not None:
        profile.longitude = update_in.longitude
    if update_in.service_radius_km is not None:
        profile.service_radius_km = update_in.service_radius_km
    if update_in.accepted_categories is not None:
        profile.accepted_categories = json.dumps(update_in.accepted_categories)
    if update_in.storage_facilities is not None:
        profile.storage_facilities = json.dumps(update_in.storage_facilities)
    if update_in.max_capacity_units is not None:
        profile.max_capacity_units = update_in.max_capacity_units
    if update_in.operating_hours is not None:
        profile.operating_hours = update_in.operating_hours

    db.commit()
    db.refresh(profile)
    return profile


def serialize_ngo_profile_response(profile: NgoProfile, tenant_name: str) -> NgoProfileResponse:
    """Helper to convert NgoProfile to NgoProfileResponse."""
    def parse_list(val: str) -> List[str]:
        try:
            p = json.loads(val)
            if isinstance(p, list):
                return p
        except Exception:
            pass
        return [val] if val else []

    return NgoProfileResponse(
        id=profile.id,
        tenant_id=profile.tenant_id,
        organization_name=tenant_name,
        organization_type=profile.organization_type,
        is_verified=profile.is_verified,
        verification_date=profile.verification_date,
        contact_person=profile.contact_person,
        contact_phone=profile.contact_phone,
        contact_email=profile.contact_email,
        address=profile.address,
        latitude=float(profile.latitude) if profile.latitude is not None else None,
        longitude=float(profile.longitude) if profile.longitude is not None else None,
        service_radius_km=float(profile.service_radius_km),
        accepted_categories=parse_list(profile.accepted_categories),
        storage_facilities=parse_list(profile.storage_facilities),
        max_capacity_units=float(profile.max_capacity_units),
        operating_hours=profile.operating_hours,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def list_surplus_notifications(
    db: Session,
    tenant_id: str,
    unread_only: bool = False,
    limit: int = 50,
) -> List[SurplusNotificationResponse]:
    """Retrieves in-app notifications for surplus and claim events."""
    query = select(SurplusNotification).where(SurplusNotification.tenant_id == tenant_id)
    if unread_only:
        query = query.where(SurplusNotification.is_read == False)
    query = query.order_by(SurplusNotification.created_at.desc()).limit(limit)

    notifs = db.execute(query).scalars().all()
    return [
        SurplusNotificationResponse(
            id=n.id,
            tenant_id=n.tenant_id,
            user_id=n.user_id,
            title=n.title,
            message=n.message,
            notification_type=n.notification_type,
            reference_id=n.reference_id,
            is_read=n.is_read,
            created_at=n.created_at,
        )
        for n in notifs
    ]


def mark_notification_read(
    db: Session,
    tenant_id: str,
    notification_id: str,
) -> bool:
    """Marks an in-app notification as read."""
    notif = (
        db.execute(
            select(SurplusNotification).where(
                SurplusNotification.id == notification_id,
                SurplusNotification.tenant_id == tenant_id,
            )
        )
        .scalars()
        .first()
    )
    if notif:
        notif.is_read = True
        db.commit()
        return True
    return False


def mark_all_notifications_read(
    db: Session,
    tenant_id: str,
) -> int:
    """Marks all unread notifications for a tenant as read."""
    notifs = (
        db.execute(
            select(SurplusNotification).where(
                SurplusNotification.tenant_id == tenant_id,
                SurplusNotification.is_read == False,
            )
        )
        .scalars()
        .all()
    )
    count = len(notifs)
    for n in notifs:
        n.is_read = True
    db.commit()
    return count


# -----------------------------------------------------------------------------
# Pickup Logistics & Handover Management (Milestone 3 - Phase 2)
# -----------------------------------------------------------------------------

def create_or_schedule_pickup(
    db: Session,
    requesting_tenant_id: str,
    user_id: str,
    schedule_in: PickupScheduleCreate,
) -> PickupSchedule:
    """
    Schedules or proposes a pickup window for an approved/requested claim.
    Both donor businesses and recipient NGOs are authorized to coordinate pickup.
    """
    claim = (
        db.execute(
            select(SurplusClaim)
            .options(
                joinedload(SurplusClaim.listing).joinedload(SurplusListing.tenant),
                joinedload(SurplusClaim.ngo_tenant),
                joinedload(SurplusClaim.pickup_schedule),
            )
            .where(SurplusClaim.id == schedule_in.claim_id)
        )
        .scalars()
        .first()
    )
    if not claim:
        raise ClaimNotFoundError(f"Surplus claim '{schedule_in.claim_id}' not found")

    listing = claim.listing
    is_ngo = claim.ngo_tenant_id == requesting_tenant_id
    is_donor = listing.tenant_id == requesting_tenant_id

    if not (is_ngo or is_donor):
        raise ClaimNotFoundError("Unauthorized to schedule pickup for this claim")

    if claim.status in (ClaimStatus.REJECTED.value, ClaimStatus.CANCELLED.value, ClaimStatus.EXPIRED.value):
        raise InvalidListingStateError(f"Cannot schedule pickup for claim in '{claim.status}' state")

    validate_pickup_window(schedule_in.pickup_start_time, schedule_in.pickup_end_time, listing)

    location = schedule_in.pickup_location or listing.pickup_address or "Donor Facility"
    instructions = schedule_in.pickup_instructions or listing.pickup_instructions

    # If an existing schedule is active
    schedule = claim.pickup_schedule
    if schedule:
        if schedule.status in (
            PickupScheduleStatus.COMPLETED.value,
            PickupScheduleStatus.CANCELLED.value,
            PickupScheduleStatus.MISSED.value,
        ):
            # Reactivate or update terminal/missed schedule
            schedule.status = PickupScheduleStatus.SCHEDULED.value
            schedule.pickup_date = schedule_in.pickup_date
            schedule.pickup_start_time = schedule_in.pickup_start_time
            schedule.pickup_end_time = schedule_in.pickup_end_time
            schedule.pickup_location = location
            schedule.pickup_instructions = instructions
            schedule.vehicle_type = schedule_in.vehicle_type
            schedule.driver_name = schedule_in.driver_name
            schedule.driver_phone = schedule_in.driver_phone
            schedule.scheduled_by_user_id = user_id
            schedule.cancellation_reason = None
            schedule.missed_at = None
        else:
            raise InvalidPickupScheduleStateError(
                f"Pickup is already scheduled for claim '{claim.id}'. Use reschedule endpoint to update window."
            )
    else:
        schedule = PickupSchedule(
            claim_id=claim.id,
            listing_id=listing.id,
            donor_tenant_id=listing.tenant_id,
            ngo_tenant_id=claim.ngo_tenant_id,
            pickup_date=schedule_in.pickup_date,
            pickup_start_time=schedule_in.pickup_start_time,
            pickup_end_time=schedule_in.pickup_end_time,
            pickup_location=location,
            pickup_instructions=instructions,
            vehicle_type=schedule_in.vehicle_type,
            driver_name=schedule_in.driver_name,
            driver_phone=schedule_in.driver_phone,
            status=PickupScheduleStatus.SCHEDULED.value,
            scheduled_by_user_id=user_id,
        )
        db.add(schedule)
    db.flush()

    # Sync claim pickup_time
    claim.pickup_time = schedule_in.pickup_start_time

    # If claim was requested, donor scheduling automatically moves it to accepted/approved
    if is_donor and claim.status in (ClaimStatus.REQUESTED.value, ClaimStatus.PENDING.value):
        claim.status = ClaimStatus.APPROVED.value
        claim.reviewed_by_user_id = user_id

    # Notify counterpart
    target_tenant_id = listing.tenant_id if is_ngo else claim.ngo_tenant_id
    target_user_id = listing.created_by_user_id if is_ngo else claim.claimed_by_user_id
    scheduler_role = "Recipient NGO" if is_ngo else "Donor Business"

    create_notification(
        db=db,
        tenant_id=target_tenant_id,
        user_id=target_user_id,
        title="Pickup Scheduled",
        message=f"{scheduler_role} scheduled pickup for '{listing.title}' on {schedule_in.pickup_date.isoformat()} between {schedule_in.pickup_start_time.strftime('%H:%M')} and {schedule_in.pickup_end_time.strftime('%H:%M')}.",
        notification_type="PICKUP_SCHEDULED",
        reference_id=claim.id,
    )

    record_audit(
        db=db,
        tenant_id=requesting_tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_PICKUP_SCHEDULE,
        resource_type="PickupSchedule",
        resource_id=schedule.id,
        payload={
            "claim_id": claim.id,
            "listing_id": listing.id,
            "pickup_date": schedule_in.pickup_date.isoformat(),
            "pickup_start_time": schedule_in.pickup_start_time.isoformat(),
            "pickup_end_time": schedule_in.pickup_end_time.isoformat(),
        },
    )

    db.commit()
    db.refresh(schedule)
    return schedule


def reschedule_pickup(
    db: Session,
    requesting_tenant_id: str,
    user_id: str,
    claim_id: str,
    reschedule_in: PickupScheduleReschedule,
) -> PickupSchedule:
    """
    Reschedules an active pickup window with documented reason and audit trail.
    """
    schedule = (
        db.execute(
            select(PickupSchedule)
            .options(
                joinedload(PickupSchedule.claim),
                joinedload(PickupSchedule.listing),
                joinedload(PickupSchedule.donor_tenant),
                joinedload(PickupSchedule.ngo_tenant),
                joinedload(PickupSchedule.scheduled_by_user),
            )
            .where(PickupSchedule.claim_id == claim_id)
        )
        .scalars()
        .first()
    )
    if not schedule:
        raise PickupScheduleNotFoundError(f"No pickup schedule found for claim '{claim_id}'")

    is_ngo = schedule.ngo_tenant_id == requesting_tenant_id
    is_donor = schedule.donor_tenant_id == requesting_tenant_id
    if not (is_ngo or is_donor):
        raise PickupScheduleNotFoundError("Unauthorized to reschedule this pickup")

    if schedule.status in (
        PickupScheduleStatus.COLLECTED.value,
        PickupScheduleStatus.COMPLETED.value,
        PickupScheduleStatus.CANCELLED.value,
    ):
        raise InvalidPickupScheduleStateError(
            f"Cannot reschedule pickup in '{schedule.status}' status"
        )

    validate_pickup_window(reschedule_in.pickup_start_time, reschedule_in.pickup_end_time, schedule.listing)

    old_window = f"{schedule.pickup_date.isoformat()} {schedule.pickup_start_time.strftime('%H:%M')}-{schedule.pickup_end_time.strftime('%H:%M')}"

    schedule.pickup_date = reschedule_in.pickup_date
    schedule.pickup_start_time = reschedule_in.pickup_start_time
    schedule.pickup_end_time = reschedule_in.pickup_end_time
    schedule.rescheduled_count += 1
    schedule.rescheduled_reason = reschedule_in.rescheduled_reason
    schedule.status = PickupScheduleStatus.RESCHEDULED.value
    schedule.missed_at = None

    if reschedule_in.pickup_location:
        schedule.pickup_location = reschedule_in.pickup_location
    if reschedule_in.pickup_instructions:
        schedule.pickup_instructions = reschedule_in.pickup_instructions
    if reschedule_in.vehicle_type:
        schedule.vehicle_type = reschedule_in.vehicle_type
    if reschedule_in.driver_name:
        schedule.driver_name = reschedule_in.driver_name
    if reschedule_in.driver_phone:
        schedule.driver_phone = reschedule_in.driver_phone

    # Sync claim
    if schedule.claim:
        schedule.claim.pickup_time = reschedule_in.pickup_start_time

    # Notify counterpart
    target_tenant_id = schedule.donor_tenant_id if is_ngo else schedule.ngo_tenant_id
    rescheduler = "NGO" if is_ngo else "Donor Business"
    create_notification(
        db=db,
        tenant_id=target_tenant_id,
        user_id=None,
        title="Pickup Window Rescheduled",
        message=f"{rescheduler} rescheduled pickup for '{schedule.listing.title}' to {reschedule_in.pickup_date.isoformat()} ({reschedule_in.rescheduled_reason}).",
        notification_type="PICKUP_RESCHEDULED",
        reference_id=schedule.claim_id,
    )

    record_audit(
        db=db,
        tenant_id=requesting_tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_PICKUP_RESCHEDULE,
        resource_type="PickupSchedule",
        resource_id=schedule.id,
        payload={
            "claim_id": schedule.claim_id,
            "old_window": old_window,
            "new_date": reschedule_in.pickup_date.isoformat(),
            "new_start": reschedule_in.pickup_start_time.isoformat(),
            "new_end": reschedule_in.pickup_end_time.isoformat(),
            "rescheduled_reason": reschedule_in.rescheduled_reason,
            "rescheduled_count": schedule.rescheduled_count,
        },
    )

    db.commit()
    db.refresh(schedule)
    return schedule


def mark_pickup_ready(
    db: Session,
    donor_tenant_id: str,
    user_id: str,
    claim_id: str,
) -> PickupSchedule:
    """
    Donor marks the surplus donation packaged and ready for collection.
    Transitions schedule to READY_FOR_COLLECTION and claim to READY_FOR_PICKUP.
    """
    schedule = (
        db.execute(
            select(PickupSchedule)
            .options(
                joinedload(PickupSchedule.claim),
                joinedload(PickupSchedule.listing),
                joinedload(PickupSchedule.donor_tenant),
                joinedload(PickupSchedule.ngo_tenant),
                joinedload(PickupSchedule.scheduled_by_user),
            )
            .where(PickupSchedule.claim_id == claim_id)
        )
        .scalars()
        .first()
    )
    if not schedule:
        raise PickupScheduleNotFoundError(f"No pickup schedule found for claim '{claim_id}'")

    if schedule.donor_tenant_id != donor_tenant_id:
        raise PickupScheduleNotFoundError("Unauthorized: pickup schedule belongs to another business")

    if schedule.status not in (
        PickupScheduleStatus.SCHEDULED.value,
        PickupScheduleStatus.RESCHEDULED.value,
    ):
        raise InvalidPickupScheduleStateError(
            f"Cannot mark ready from status '{schedule.status}'"
        )

    now = datetime.now(timezone.utc)
    schedule.status = PickupScheduleStatus.READY_FOR_COLLECTION.value
    schedule.ready_at = now

    if schedule.claim:
        schedule.claim.status = ClaimStatus.READY_FOR_PICKUP.value

    create_notification(
        db=db,
        tenant_id=schedule.ngo_tenant_id,
        user_id=schedule.claim.claimed_by_user_id if schedule.claim else None,
        title="Donation Ready for Collection",
        message=f"Food donation for '{schedule.listing.title}' is packaged and ready for pickup at {schedule.pickup_location}.",
        notification_type="PICKUP_READY",
        reference_id=schedule.claim_id,
    )

    record_audit(
        db=db,
        tenant_id=donor_tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_PICKUP_READY,
        resource_type="PickupSchedule",
        resource_id=schedule.id,
        payload={"claim_id": schedule.claim_id, "ready_at": now.isoformat()},
    )

    db.commit()
    db.refresh(schedule)
    return schedule


def confirm_pickup_collection(
    db: Session,
    requesting_tenant_id: str,
    user_id: str,
    claim_id: str,
) -> PickupSchedule:
    """
    Marks physical collection in-progress / collected at donor premise.
    Transitions schedule to COLLECTED and claim to PICKED_UP.
    """
    schedule = (
        db.execute(
            select(PickupSchedule)
            .options(
                joinedload(PickupSchedule.claim),
                joinedload(PickupSchedule.listing),
                joinedload(PickupSchedule.donor_tenant),
                joinedload(PickupSchedule.ngo_tenant),
                joinedload(PickupSchedule.scheduled_by_user),
            )
            .where(PickupSchedule.claim_id == claim_id)
        )
        .scalars()
        .first()
    )
    if not schedule:
        raise PickupScheduleNotFoundError(f"No pickup schedule found for claim '{claim_id}'")

    is_ngo = schedule.ngo_tenant_id == requesting_tenant_id
    is_donor = schedule.donor_tenant_id == requesting_tenant_id
    if not (is_ngo or is_donor):
        raise PickupScheduleNotFoundError("Unauthorized to confirm collection for this pickup")

    if schedule.status not in (
        PickupScheduleStatus.READY_FOR_COLLECTION.value,
        PickupScheduleStatus.SCHEDULED.value,
        PickupScheduleStatus.RESCHEDULED.value,
    ):
        raise InvalidPickupScheduleStateError(
            f"Cannot mark collected from status '{schedule.status}'"
        )

    now = datetime.now(timezone.utc)
    schedule.status = PickupScheduleStatus.COLLECTED.value
    schedule.collected_at = now

    if schedule.claim:
        schedule.claim.status = ClaimStatus.PICKED_UP.value

    # Notify counterpart
    target_tenant_id = schedule.donor_tenant_id if is_ngo else schedule.ngo_tenant_id
    create_notification(
        db=db,
        tenant_id=target_tenant_id,
        user_id=None,
        title="Donation Collected",
        message=f"Pickup for '{schedule.listing.title}' has been collected and is in transit.",
        notification_type="PICKUP_COLLECTED",
        reference_id=schedule.claim_id,
    )

    record_audit(
        db=db,
        tenant_id=requesting_tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_PICKUP_COLLECT,
        resource_type="PickupSchedule",
        resource_id=schedule.id,
        payload={"claim_id": schedule.claim_id, "collected_at": now.isoformat()},
    )

    db.commit()
    db.refresh(schedule)
    return schedule


def mark_pickup_missed(
    db: Session,
    donor_tenant_id: str,
    user_id: str,
    claim_id: str,
    reason: Optional[str] = None,
) -> PickupSchedule:
    """
    Donor flags that recipient did not arrive during the scheduled pickup window.
    Transitions schedule to MISSED.
    """
    schedule = (
        db.execute(
            select(PickupSchedule)
            .options(
                joinedload(PickupSchedule.claim),
                joinedload(PickupSchedule.listing),
                joinedload(PickupSchedule.donor_tenant),
                joinedload(PickupSchedule.ngo_tenant),
                joinedload(PickupSchedule.scheduled_by_user),
            )
            .where(PickupSchedule.claim_id == claim_id)
        )
        .scalars()
        .first()
    )
    if not schedule:
        raise PickupScheduleNotFoundError(f"No pickup schedule found for claim '{claim_id}'")

    if schedule.donor_tenant_id != donor_tenant_id:
        raise PickupScheduleNotFoundError("Unauthorized: pickup schedule belongs to another business")

    if schedule.status in (
        PickupScheduleStatus.COMPLETED.value,
        PickupScheduleStatus.COLLECTED.value,
        PickupScheduleStatus.CANCELLED.value,
    ):
        raise InvalidPickupScheduleStateError(f"Cannot mark pickup as missed from status '{schedule.status}'")

    now = datetime.now(timezone.utc)
    schedule.status = PickupScheduleStatus.MISSED.value
    schedule.missed_at = now
    schedule.cancellation_reason = reason or "Volunteer did not arrive within pickup window"

    create_notification(
        db=db,
        tenant_id=schedule.ngo_tenant_id,
        user_id=schedule.claim.claimed_by_user_id if schedule.claim else None,
        title="Pickup Window Missed",
        message=f"Pickup for '{schedule.listing.title}' was marked as missed: {schedule.cancellation_reason}. Please reschedule immediately.",
        notification_type="PICKUP_MISSED",
        reference_id=schedule.claim_id,
    )

    record_audit(
        db=db,
        tenant_id=donor_tenant_id,
        user_id=user_id,
        event_type=AuditEventType.SURPLUS_PICKUP_MISSED,
        resource_type="PickupSchedule",
        resource_id=schedule.id,
        payload={"claim_id": schedule.claim_id, "reason": schedule.cancellation_reason},
    )

    db.commit()
    db.refresh(schedule)
    return schedule


def list_pickup_schedules(
    db: Session,
    tenant_id: str,
    is_ngo: bool,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    size: int = 50,
) -> Tuple[List[PickupSchedule], int]:
    """
    Lists pickup schedules filtered by tenant ownership, status, and date range.
    """
    query = select(PickupSchedule).options(
        joinedload(PickupSchedule.claim),
        joinedload(PickupSchedule.listing),
        joinedload(PickupSchedule.donor_tenant),
        joinedload(PickupSchedule.ngo_tenant),
        joinedload(PickupSchedule.scheduled_by_user),
    )

    if is_ngo:
        query = query.where(PickupSchedule.ngo_tenant_id == tenant_id)
    else:
        query = query.where(PickupSchedule.donor_tenant_id == tenant_id)

    if status:
        query = query.where(PickupSchedule.status == status.upper())

    if date_from:
        query = query.where(PickupSchedule.pickup_date >= date_from)

    if date_to:
        query = query.where(PickupSchedule.pickup_date <= date_to)

    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar_one()

    query = query.order_by(PickupSchedule.pickup_date.asc(), PickupSchedule.pickup_start_time.asc())
    offset = (page - 1) * size
    schedules = db.execute(query.offset(offset).limit(size)).scalars().unique().all()
    return list(schedules), total


def get_pickup_schedule_by_claim_id(
    db: Session,
    claim_id: str,
    tenant_id: str,
) -> PickupSchedule:
    """Retrieves pickup schedule for a claim with tenant isolation check."""
    schedule = (
        db.execute(
            select(PickupSchedule)
            .options(
                joinedload(PickupSchedule.claim),
                joinedload(PickupSchedule.listing),
                joinedload(PickupSchedule.donor_tenant),
                joinedload(PickupSchedule.ngo_tenant),
                joinedload(PickupSchedule.scheduled_by_user),
            )
            .where(PickupSchedule.claim_id == claim_id)
        )
        .scalars()
        .first()
    )
    if not schedule:
        raise PickupScheduleNotFoundError(f"No pickup schedule found for claim '{claim_id}'")

    if schedule.donor_tenant_id != tenant_id and schedule.ngo_tenant_id != tenant_id:
        raise PickupScheduleNotFoundError(f"No pickup schedule found for claim '{claim_id}'")

    return schedule
