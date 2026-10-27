"""Pydantic Schemas for Surplus Listings, NGO Profiles, Matching Engine, and Claims."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# -----------------------------------------------------------------------------
# Surplus Listing Schemas
# -----------------------------------------------------------------------------

class SurplusListingBase(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    quantity: float = Field(..., gt=0, description="Quantity available for donation")
    unit: str = Field(..., min_length=1, max_length=20)
    expiry_date: date
    storage_requirement: str = Field(default="AMBIENT", max_length=30)
    pickup_address: str = Field(..., min_length=3)
    pickup_instructions: Optional[str] = None
    description: Optional[str] = None
    available_from: datetime
    available_until: datetime
    status: str = Field(default="AVAILABLE")

    @field_validator("available_until")
    @classmethod
    def validate_window(cls, v: datetime, info: Any) -> datetime:
        from_time = info.data.get("available_from")
        if from_time and v <= from_time:
            raise ValueError("available_until must be strictly after available_from")
        return v


class SurplusListingCreate(BaseModel):
    item_id: str = Field(..., description="Inventory item ID being earmarked")
    title: Optional[str] = Field(None, max_length=255)
    quantity: float = Field(..., gt=0)
    unit: Optional[str] = None
    expiry_date: Optional[date] = None
    storage_requirement: Optional[str] = None
    pickup_address: str = Field(..., min_length=3)
    pickup_instructions: Optional[str] = None
    description: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: datetime
    status: Optional[str] = "AVAILABLE"


class SurplusListingUpdate(BaseModel):
    title: Optional[str] = None
    quantity: Optional[float] = Field(None, gt=0)
    pickup_address: Optional[str] = None
    pickup_instructions: Optional[str] = None
    description: Optional[str] = None
    available_until: Optional[datetime] = None
    status: Optional[str] = None


class SurplusListingResponse(BaseModel):
    id: str
    tenant_id: str
    item_id: str
    title: Optional[str]
    product_name: str
    category_name: str
    category_id: str
    sku: Optional[str]
    quantity: float
    remaining_claimable_quantity: float
    unit: str
    expiry_date: date
    days_to_expiry: float
    storage_requirement: str
    status: str
    pickup_address: str
    pickup_instructions: Optional[str]
    description: Optional[str]
    available_from: datetime
    available_until: datetime
    claimed_by_tenant_id: Optional[str]
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime
    claims_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# -----------------------------------------------------------------------------
# NGO Profile Schemas
# -----------------------------------------------------------------------------

class NgoProfileBase(BaseModel):
    organization_type: str = Field(default="FOOD_BANK")
    contact_person: str = Field(..., min_length=2, max_length=255)
    contact_phone: str = Field(..., min_length=5, max_length=50)
    contact_email: str = Field(..., min_length=5, max_length=255)
    address: str = Field(..., min_length=3)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    service_radius_km: float = Field(default=25.0, gt=0)
    accepted_categories: List[str] = Field(default_factory=list)
    storage_facilities: List[str] = Field(default_factory=lambda: ["AMBIENT"])
    max_capacity_units: float = Field(default=500.0, gt=0)
    operating_hours: Optional[str] = None


class NgoProfileCreate(NgoProfileBase):
    pass


class NgoProfileUpdate(BaseModel):
    organization_type: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    service_radius_km: Optional[float] = None
    accepted_categories: Optional[List[str]] = None
    storage_facilities: Optional[List[str]] = None
    max_capacity_units: Optional[float] = None
    operating_hours: Optional[str] = None


class NgoProfileResponse(BaseModel):
    id: str
    tenant_id: str
    organization_name: str
    organization_type: str
    is_verified: bool
    verification_date: Optional[datetime]
    contact_person: str
    contact_phone: str
    contact_email: str
    address: str
    latitude: Optional[float]
    longitude: Optional[float]
    service_radius_km: float
    accepted_categories: List[str]
    storage_facilities: List[str]
    max_capacity_units: float
    operating_hours: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -----------------------------------------------------------------------------
# Pickup Scheduling Schemas (Milestone 3 - Phase 2)
# -----------------------------------------------------------------------------

class PickupScheduleBase(BaseModel):
    pickup_date: date
    pickup_start_time: datetime
    pickup_end_time: datetime
    pickup_location: Optional[str] = None
    pickup_instructions: Optional[str] = None
    vehicle_type: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None

    @field_validator("pickup_end_time")
    @classmethod
    def validate_window(cls, v: datetime, info: Any) -> datetime:
        start = info.data.get("pickup_start_time")
        if start and v <= start:
            raise ValueError("pickup_end_time must be strictly after pickup_start_time")
        return v


class PickupScheduleCreate(PickupScheduleBase):
    claim_id: str


class PickupScheduleReschedule(BaseModel):
    pickup_date: date
    pickup_start_time: datetime
    pickup_end_time: datetime
    rescheduled_reason: str = Field(..., min_length=3, max_length=255)
    pickup_location: Optional[str] = None
    pickup_instructions: Optional[str] = None
    vehicle_type: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None

    @field_validator("pickup_end_time")
    @classmethod
    def validate_window(cls, v: datetime, info: Any) -> datetime:
        start = info.data.get("pickup_start_time")
        if start and v <= start:
            raise ValueError("pickup_end_time must be strictly after pickup_start_time")
        return v


class PickupMilestoneUpdate(BaseModel):
    action: str = Field(..., description="'READY', 'COLLECTED', 'COMPLETE', 'MISSED', or 'CANCEL'")
    reason: Optional[str] = None


class PickupScheduleResponse(BaseModel):
    id: str
    claim_id: str
    listing_id: str
    listing_title: str
    donor_tenant_id: str
    donor_name: str
    ngo_tenant_id: str
    ngo_name: str
    pickup_date: date
    pickup_start_time: datetime
    pickup_end_time: datetime
    pickup_location: str
    pickup_instructions: Optional[str]
    vehicle_type: Optional[str]
    driver_name: Optional[str]
    driver_phone: Optional[str]
    status: str
    scheduled_by_user_id: str
    scheduled_by_user_name: str
    rescheduled_count: int
    rescheduled_reason: Optional[str]
    cancellation_reason: Optional[str]
    ready_at: Optional[datetime]
    collected_at: Optional[datetime]
    completed_at: Optional[datetime]
    missed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -----------------------------------------------------------------------------
# Surplus Claim Schemas
# -----------------------------------------------------------------------------

class SurplusClaimCreate(BaseModel):
    listing_id: str
    claimed_quantity: float = Field(..., gt=0)
    pickup_time: Optional[datetime] = None
    notes: Optional[str] = None
    # Optional initial scheduling proposal
    pickup_date: Optional[date] = None
    pickup_start_time: Optional[datetime] = None
    pickup_end_time: Optional[datetime] = None
    vehicle_type: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None


class SurplusClaimReview(BaseModel):
    action: str = Field(..., description="'APPROVE', 'ACCEPT', or 'REJECT'")
    rejection_reason: Optional[str] = None


class SurplusClaimResponse(BaseModel):
    id: str
    listing_id: str
    listing_title: str
    ngo_tenant_id: str
    ngo_name: str
    claimed_by_user_id: str
    claimed_by_user_name: str
    claimed_quantity: float
    unit: str
    status: str
    pickup_time: Optional[datetime]
    notes: Optional[str]
    rejection_reason: Optional[str]
    reviewed_by_user_id: Optional[str]
    pickup_schedule: Optional[PickupScheduleResponse] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -----------------------------------------------------------------------------
# NGO Matching Schemas
# -----------------------------------------------------------------------------

class NgoMatchRecommendation(BaseModel):
    ngo_tenant_id: str
    ngo_name: str
    organization_type: str
    is_verified: bool
    match_score: float = Field(..., ge=0.0, le=100.0)
    distance_km: Optional[float] = None
    max_capacity_units: float
    storage_facilities: List[str]
    match_reasons: List[str]


class SurplusMatchesResponse(BaseModel):
    listing_id: str
    product_name: str
    quantity: float
    unit: str
    storage_requirement: str
    days_to_expiry: float
    total_candidates_evaluated: int
    matching_recommendations: List[NgoMatchRecommendation]


# -----------------------------------------------------------------------------
# Notification Schemas
# -----------------------------------------------------------------------------

class SurplusNotificationResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: Optional[str]
    title: str
    message: str
    notification_type: str
    reference_id: Optional[str]
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
