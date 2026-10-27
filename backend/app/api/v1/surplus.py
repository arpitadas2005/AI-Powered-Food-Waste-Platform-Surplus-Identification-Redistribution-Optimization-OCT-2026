"""Surplus Listings, NGO Matching, and Claim Allocation API Endpoints (Milestone 3)."""

import math
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_tenant_context, require_roles
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.tenant import BusinessType
from backend.app.models.user import UserRole
from backend.app.schemas.common import PaginatedResponse, PaginationMeta, SuccessEnvelope
from backend.app.schemas.surplus import (
    NgoProfileCreate,
    NgoProfileResponse,
    NgoProfileUpdate,
    PickupMilestoneUpdate,
    PickupScheduleBase,
    PickupScheduleCreate,
    PickupScheduleReschedule,
    PickupScheduleResponse,
    SurplusClaimCreate,
    SurplusClaimResponse,
    SurplusClaimReview,
    SurplusListingCreate,
    SurplusListingResponse,
    SurplusListingUpdate,
    SurplusMatchesResponse,
    SurplusNotificationResponse,
)
from backend.app.services.matching_service import calculate_ngo_matches
from backend.app.services.surplus_service import (
    ClaimNotFoundError,
    ExcessiveClaimError,
    FoodSafetyValidationError,
    InsufficientSurplusStockError,
    InvalidListingStateError,
    InvalidPickupScheduleStateError,
    InvalidPickupWindowError,
    ListingNotFoundError,
    PickupScheduleNotFoundError,
    SurplusServiceError,
    cancel_surplus_claim,
    cancel_surplus_listing,
    complete_surplus_transfer,
    confirm_pickup_collection,
    create_or_schedule_pickup,
    create_surplus_claim,
    create_surplus_listing,
    get_or_create_ngo_profile,
    get_pickup_schedule_by_claim_id,
    get_surplus_listing_by_id,
    list_claims_for_listing,
    list_claims_for_ngo,
    list_pickup_schedules,
    list_surplus_listings,
    list_surplus_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    mark_pickup_missed,
    mark_pickup_ready,
    reschedule_pickup,
    review_surplus_claim,
    serialize_claim_response,
    serialize_listing_response,
    serialize_ngo_profile_response,
    serialize_pickup_schedule_response,
    update_ngo_profile,
    update_surplus_listing,
)

router = APIRouter(prefix="/surplus", tags=["surplus"])


# -----------------------------------------------------------------------------
# Surplus Listing Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/listings",
    response_model=SuccessEnvelope[SurplusListingResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create surplus food listing",
)
def create_listing(
    listing_in: SurplusListingCreate,
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.INVENTORY_STAFF.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """
    Creates an earmarked surplus listing for an inventory item.
    Enforces food-safety shelf life checks and oversubscription limits.
    """
    try:
        listing = create_surplus_listing(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            listing_in=listing_in,
        )
        data = serialize_listing_response(listing, db)
        return SuccessEnvelope(data=data)
    except ListingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (FoodSafetyValidationError, InsufficientSurplusStockError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SurplusServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/listings",
    response_model=PaginatedResponse[SurplusListingResponse],
    summary="List surplus food listings",
)
def list_listings(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    storage_requirement: Optional[str] = Query(None),
    min_days_to_expiry: Optional[float] = Query(None),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Lists surplus items.
    For donor business users: returns their organization's listings.
    For NGO users: returns active available donations across the platform.
    """
    is_ngo = context.role == UserRole.RECIPIENT_NGO.value

    listings, total = list_surplus_listings(
        db=db,
        tenant_id=context.tenant_id,
        is_ngo=is_ngo,
        status=status,
        category_id=category_id,
        storage_requirement=storage_requirement,
        min_days_to_expiry=min_days_to_expiry,
        page=page,
        size=size,
    )

    data = [serialize_listing_response(l, db) for l in listings]
    total_pages = math.ceil(total / size) if size > 0 else 1

    return PaginatedResponse(
        data=data,
        pagination=PaginationMeta(
            page=page,
            size=size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get(
    "/listings/{listing_id}",
    response_model=SuccessEnvelope[SurplusListingResponse],
    summary="Get surplus listing details",
)
def get_listing(
    listing_id: str,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieves full details of a surplus listing."""
    is_ngo = context.role == UserRole.RECIPIENT_NGO.value
    try:
        listing = get_surplus_listing_by_id(
            db=db,
            listing_id=listing_id,
            requesting_tenant_id=context.tenant_id,
            is_ngo=is_ngo,
        )
        return SuccessEnvelope(data=serialize_listing_response(listing, db))
    except ListingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put(
    "/listings/{listing_id}",
    response_model=SuccessEnvelope[SurplusListingResponse],
    summary="Update surplus listing",
)
def update_listing(
    listing_id: str,
    update_in: SurplusListingUpdate,
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """Updates an active or draft surplus listing."""
    try:
        listing = update_surplus_listing(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            listing_id=listing_id,
            update_in=update_in,
        )
        return SuccessEnvelope(data=serialize_listing_response(listing, db))
    except ListingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InsufficientSurplusStockError, InvalidListingStateError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/listings/{listing_id}/cancel",
    response_model=SuccessEnvelope[SurplusListingResponse],
    summary="Cancel surplus listing",
)
def cancel_listing(
    listing_id: str,
    reason: Optional[str] = Query(None),
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """Cancels a surplus listing and releases held stock."""
    try:
        listing = cancel_surplus_listing(
            db=db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            listing_id=listing_id,
            reason=reason,
        )
        return SuccessEnvelope(data=serialize_listing_response(listing, db))
    except ListingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidListingStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -----------------------------------------------------------------------------
# NGO Matching Engine Endpoints
# -----------------------------------------------------------------------------

@router.get(
    "/listings/{listing_id}/matches",
    response_model=SuccessEnvelope[SurplusMatchesResponse],
    summary="Get ranked NGO matches for listing",
)
def get_matches_for_listing(
    listing_id: str,
    origin_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    origin_lon: Optional[float] = Query(None, ge=-180.0, le=180.0),
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.INVENTORY_STAFF.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """
    Runs the multi-factor NGO matching engine against an active listing.
    Calculates category, storage, capacity, proximity, and urgency scores with explainable reasons.
    """
    try:
        listing = get_surplus_listing_by_id(
            db=db,
            listing_id=listing_id,
            requesting_tenant_id=context.tenant_id,
        )
        matches = calculate_ngo_matches(
            db=db,
            listing=listing,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
        )
        return SuccessEnvelope(data=matches)
    except ListingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# -----------------------------------------------------------------------------
# Claims & Reservations Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/claims",
    response_model=SuccessEnvelope[SurplusClaimResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit claim request for surplus listing",
)
def create_claim(
    claim_in: SurplusClaimCreate,
    context: TenantContext = Depends(
        require_roles([
            UserRole.RECIPIENT_NGO.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """
    Submitted by an NGO to request/reserve quantity from an available listing.
    """
    try:
        claim = create_surplus_claim(
            db=db,
            ngo_tenant_id=context.tenant_id,
            user_id=context.user_id,
            claim_in=claim_in,
        )
        return SuccessEnvelope(data=serialize_claim_response(claim))
    except ListingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ExcessiveClaimError, InvalidListingStateError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/claims/my",
    response_model=SuccessEnvelope[List[SurplusClaimResponse]],
    summary="List NGO's own claims",
)
def get_my_claims(
    status: Optional[str] = Query(None),
    context: TenantContext = Depends(
        require_roles([
            UserRole.RECIPIENT_NGO.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """Retrieves all surplus food claims submitted by the authenticated NGO."""
    claims = list_claims_for_ngo(db=db, ngo_tenant_id=context.tenant_id, status=status)
    data = [serialize_claim_response(c) for c in claims]
    return SuccessEnvelope(data=data)


@router.get(
    "/listings/{listing_id}/claims",
    response_model=SuccessEnvelope[List[SurplusClaimResponse]],
    summary="List claims for donor listing",
)
def get_listing_claims(
    listing_id: str,
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """Retrieves all NGO claims received for a specific donor listing."""
    try:
        claims = list_claims_for_listing(
            db=db,
            donor_tenant_id=context.tenant_id,
            listing_id=listing_id,
        )
        data = [serialize_claim_response(c) for c in claims]
        return SuccessEnvelope(data=data)
    except ListingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/claims/{claim_id}/review",
    response_model=SuccessEnvelope[SurplusClaimResponse],
    summary="Approve or reject claim request",
)
def review_claim(
    claim_id: str,
    review_in: SurplusClaimReview,
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """Donor business approves or rejects an incoming claim from an NGO."""
    try:
        claim = review_surplus_claim(
            db=db,
            donor_tenant_id=context.tenant_id,
            reviewer_user_id=context.user_id,
            claim_id=claim_id,
            action=review_in.action,
            rejection_reason=review_in.rejection_reason,
        )
        return SuccessEnvelope(data=serialize_claim_response(claim))
    except ClaimNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidListingStateError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/claims/{claim_id}/complete",
    response_model=SuccessEnvelope[SurplusClaimResponse],
    summary="Confirm physical pickup and deduct stock",
)
def complete_transfer(
    claim_id: str,
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """
    Confirms food handover to NGO.
    Atomically marks claim COMPLETED and triggers DONATION_DISPATCH inventory deduction.
    """
    try:
        claim, _ = complete_surplus_transfer(
            db=db,
            donor_tenant_id=context.tenant_id,
            user_id=context.user_id,
            claim_id=claim_id,
        )
        return SuccessEnvelope(data=serialize_claim_response(claim))
    except ClaimNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidListingStateError, SurplusServiceError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/claims/{claim_id}/cancel",
    response_model=SuccessEnvelope[SurplusClaimResponse],
    summary="Cancel claim request",
)
def cancel_claim(
    claim_id: str,
    reason: Optional[str] = Query(None),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Cancels a surplus claim and releases the hold."""
    try:
        claim = cancel_surplus_claim(
            db=db,
            requesting_tenant_id=context.tenant_id,
            user_id=context.user_id,
            claim_id=claim_id,
            reason=reason,
        )
        return SuccessEnvelope(data=serialize_claim_response(claim))
    except ClaimNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidListingStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -----------------------------------------------------------------------------
# NGO Profile Endpoints
# -----------------------------------------------------------------------------

@router.get(
    "/ngo/profile",
    response_model=SuccessEnvelope[NgoProfileResponse],
    summary="Get NGO operational profile",
)
def get_ngo_profile(
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieves operational capabilities and preferences for the current organization."""
    profile = get_or_create_ngo_profile(db=db, tenant_id=context.tenant_id)
    return SuccessEnvelope(
        data=serialize_ngo_profile_response(profile, context.business_name)
    )


@router.put(
    "/ngo/profile",
    response_model=SuccessEnvelope[NgoProfileResponse],
    summary="Update NGO operational profile",
)
def update_profile(
    profile_in: NgoProfileUpdate,
    context: TenantContext = Depends(
        require_roles([
            UserRole.RECIPIENT_NGO.value,
            UserRole.BUSINESS_OWNER.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """Updates accepted categories, cold-chain capacity, and service radius."""
    profile = update_ngo_profile(
        db=db,
        tenant_id=context.tenant_id,
        update_in=profile_in,
    )
    return SuccessEnvelope(
        data=serialize_ngo_profile_response(profile, context.business_name)
    )


# -----------------------------------------------------------------------------
# Notification Endpoints
# -----------------------------------------------------------------------------

@router.get(
    "/notifications",
    response_model=SuccessEnvelope[List[SurplusNotificationResponse]],
    summary="Get in-app surplus notifications",
)
def get_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieves notifications for surplus matches, claims, and collection updates."""
    notifs = list_surplus_notifications(
        db=db,
        tenant_id=context.tenant_id,
        unread_only=unread_only,
        limit=limit,
    )
    return SuccessEnvelope(data=notifs)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=SuccessEnvelope[bool],
    summary="Mark notification as read",
)
def mark_read(
    notification_id: str,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Marks a surplus notification as read."""
    success = mark_notification_read(
        db=db,
        tenant_id=context.tenant_id,
        notification_id=notification_id,
    )
    return SuccessEnvelope(data=success)


@router.post(
    "/notifications/read-all",
    response_model=SuccessEnvelope[int],
    summary="Mark all notifications as read",
)
def mark_all_read(
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Marks all unread notifications for the current organization as read."""
    count = mark_all_notifications_read(db=db, tenant_id=context.tenant_id)
    return SuccessEnvelope(data=count)


# -----------------------------------------------------------------------------
# Pickup Scheduling & Logistics Endpoints (Milestone 3 - Phase 2)
# -----------------------------------------------------------------------------

@router.post(
    "/claims/{claim_id}/schedule",
    response_model=SuccessEnvelope[PickupScheduleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Schedule pickup window for surplus claim",
)
def schedule_pickup(
    claim_id: str,
    schedule_in: PickupScheduleBase,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Coordinates pickup logistics and time window between food business and NGO.
    Enforces food expiration safety check and operational windows.
    """
    try:
        create_payload = PickupScheduleCreate(
            claim_id=claim_id,
            **schedule_in.model_dump(),
        )
        schedule = create_or_schedule_pickup(
            db=db,
            requesting_tenant_id=context.tenant_id,
            user_id=context.user_id,
            schedule_in=create_payload,
        )
        return SuccessEnvelope(data=serialize_pickup_schedule_response(schedule))
    except (ClaimNotFoundError, PickupScheduleNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidPickupWindowError, InvalidPickupScheduleStateError, InvalidListingStateError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/claims/{claim_id}/reschedule",
    response_model=SuccessEnvelope[PickupScheduleResponse],
    summary="Reschedule pickup window",
)
def reschedule_claim_pickup(
    claim_id: str,
    reschedule_in: PickupScheduleReschedule,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Updates the scheduled pickup window with a documented reason.
    Both donor businesses and recipient NGOs are authorized to request rescheduling.
    """
    try:
        schedule = reschedule_pickup(
            db=db,
            requesting_tenant_id=context.tenant_id,
            user_id=context.user_id,
            claim_id=claim_id,
            reschedule_in=reschedule_in,
        )
        return SuccessEnvelope(data=serialize_pickup_schedule_response(schedule))
    except (ClaimNotFoundError, PickupScheduleNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidPickupWindowError, InvalidPickupScheduleStateError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/claims/{claim_id}/ready",
    response_model=SuccessEnvelope[PickupScheduleResponse],
    summary="Mark donation ready for pickup",
)
def mark_claim_ready(
    claim_id: str,
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.INVENTORY_STAFF.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """Donor marks the surplus donation packaged and ready for collection."""
    try:
        schedule = mark_pickup_ready(
            db=db,
            donor_tenant_id=context.tenant_id,
            user_id=context.user_id,
            claim_id=claim_id,
        )
        return SuccessEnvelope(data=serialize_pickup_schedule_response(schedule))
    except PickupScheduleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidPickupScheduleStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/claims/{claim_id}/collect",
    response_model=SuccessEnvelope[PickupScheduleResponse],
    summary="Confirm collection underway",
)
def collect_claim(
    claim_id: str,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Marks physical collection in progress or items collected at donor facility."""
    try:
        schedule = confirm_pickup_collection(
            db=db,
            requesting_tenant_id=context.tenant_id,
            user_id=context.user_id,
            claim_id=claim_id,
        )
        return SuccessEnvelope(data=serialize_pickup_schedule_response(schedule))
    except PickupScheduleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidPickupScheduleStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/claims/{claim_id}/missed",
    response_model=SuccessEnvelope[PickupScheduleResponse],
    summary="Mark scheduled pickup as missed",
)
def mark_missed(
    claim_id: str,
    reason: Optional[str] = Query(None),
    context: TenantContext = Depends(
        require_roles([
            UserRole.BUSINESS_OWNER.value,
            UserRole.STORE_MANAGER.value,
            UserRole.SYSTEM_ADMIN.value,
        ])
    ),
    db: Session = Depends(get_db),
):
    """Donor flags that recipient did not arrive during the scheduled pickup window."""
    try:
        schedule = mark_pickup_missed(
            db=db,
            donor_tenant_id=context.tenant_id,
            user_id=context.user_id,
            claim_id=claim_id,
            reason=reason,
        )
        return SuccessEnvelope(data=serialize_pickup_schedule_response(schedule))
    except PickupScheduleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidPickupScheduleStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/claims/{claim_id}/schedule",
    response_model=SuccessEnvelope[PickupScheduleResponse],
    summary="Get pickup schedule for a claim",
)
def get_claim_schedule(
    claim_id: str,
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieves pickup schedule details for a specific claim."""
    try:
        schedule = get_pickup_schedule_by_claim_id(
            db=db,
            claim_id=claim_id,
            tenant_id=context.tenant_id,
        )
        return SuccessEnvelope(data=serialize_pickup_schedule_response(schedule))
    except PickupScheduleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/pickups",
    response_model=PaginatedResponse[PickupScheduleResponse],
    summary="List scheduled pickups",
)
def get_pickups(
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Lists scheduled pickups scoped to authenticated organization:
    - Donors see pickups scheduled at their facilities.
    - NGOs see pickups scheduled for their claims.
    """
    is_ngo = context.role == UserRole.RECIPIENT_NGO.value
    schedules, total = list_pickup_schedules(
        db=db,
        tenant_id=context.tenant_id,
        is_ngo=is_ngo,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    items = [serialize_pickup_schedule_response(s) for s in schedules]
    total_pages = math.ceil(total / size) if size > 0 else 1

    return PaginatedResponse(
        data=items,
        pagination=PaginationMeta(
            page=page,
            size=size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )
