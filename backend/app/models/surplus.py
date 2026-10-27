"""Surplus Donation Listing, NGO Profiles, and Claim Allocation Models (Milestone 3)."""

from datetime import date, datetime
from enum import Enum
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid, utc_now

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant
    from backend.app.models.inventory import InventoryItem
    from backend.app.models.user import User


class SurplusStatus(str, Enum):
    DRAFT = "DRAFT"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    PICKED_UP = "PICKED_UP"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class OrganizationType(str, Enum):
    FOOD_BANK = "FOOD_BANK"
    SOUP_KITCHEN = "SOUP_KITCHEN"
    HOMELESS_SHELTER = "HOMELESS_SHELTER"
    COMMUNITY_PANTRY = "COMMUNITY_PANTRY"
    CHARITY_RECIPIENT = "CHARITY_RECIPIENT"


class ClaimStatus(str, Enum):
    REQUESTED = "REQUESTED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    PICKED_UP = "PICKED_UP"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PickupScheduleStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    RESCHEDULED = "RESCHEDULED"
    READY_FOR_COLLECTION = "READY_FOR_COLLECTION"
    COLLECTED = "COLLECTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    MISSED = "MISSED"


class SurplusListing(Base, TimestampMixin):
    """
    Tracks inventory batches earmarked as surplus available for NGO donation collection.
    """
    __tablename__ = "surplus_listings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    storage_requirement: Mapped[str] = mapped_column(String(30), nullable=False, default="AMBIENT")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SurplusStatus.AVAILABLE.value, index=True
    )
    pickup_address: Mapped[str] = mapped_column(Text, nullable=False)
    pickup_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_by_tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant", foreign_keys=[tenant_id], back_populates="surplus_listings"
    )
    claimed_by_tenant: Mapped["Tenant | None"] = relationship(
        "Tenant", foreign_keys=[claimed_by_tenant_id]
    )
    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="surplus_listings")
    user: Mapped["User"] = relationship("User", foreign_keys=[created_by_user_id])
    claims: Mapped[List["SurplusClaim"]] = relationship(
        "SurplusClaim", back_populates="listing", cascade="all, delete-orphan"
    )
    pickup_schedules: Mapped[List["PickupSchedule"]] = relationship(
        "PickupSchedule", back_populates="listing", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_surplus_qty_positive"),
        CheckConstraint("available_until > available_from", name="chk_surplus_window"),
        Index("idx_surplus_tenant_status", "tenant_id", "status"),
        Index("idx_surplus_window_status", "status", "available_until"),
    )


class NgoProfile(Base, TimestampMixin):
    """
    Operational profile for recipient NGOs, community kitchens, shelters, and food banks.
    Enables intelligent matching based on accepted food categories, cold-chain capacity, and location.
    """
    __tablename__ = "ngo_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    organization_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=OrganizationType.FOOD_BANK.value
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_person: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    service_radius_km: Mapped[float] = mapped_column(Numeric(6, 2), default=25.0, nullable=False)
    accepted_categories: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    storage_facilities: Mapped[str] = mapped_column(Text, nullable=False, default="[\"AMBIENT\"]")
    max_capacity_units: Mapped[float] = mapped_column(Numeric(10, 2), default=500.0, nullable=False)
    operating_hours: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="ngo_profile")


class SurplusClaim(Base, TimestampMixin):
    """
    Represents an NGO claim or allocation request against an active surplus listing.
    """
    __tablename__ = "surplus_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    listing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("surplus_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ngo_tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claimed_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    claimed_quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ClaimStatus.REQUESTED.value, index=True
    )
    pickup_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    listing: Mapped["SurplusListing"] = relationship("SurplusListing", back_populates="claims")
    ngo_tenant: Mapped["Tenant"] = relationship(
        "Tenant", foreign_keys=[ngo_tenant_id], back_populates="claimed_surplus"
    )
    claimed_by_user: Mapped["User"] = relationship("User", foreign_keys=[claimed_by_user_id])
    reviewed_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_user_id])
    pickup_schedule: Mapped[Optional["PickupSchedule"]] = relationship(
        "PickupSchedule", back_populates="claim", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("claimed_quantity > 0", name="chk_claim_qty_positive"),
        Index("idx_claims_listing_status", "listing_id", "status"),
        Index("idx_claims_ngo_status", "ngo_tenant_id", "status"),
    )


class PickupSchedule(Base, TimestampMixin):
    """
    Tracks logistics, time windows, and physical handover checkpoints for approved surplus claims.
    """
    __tablename__ = "pickup_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    claim_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("surplus_claims.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    listing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("surplus_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    donor_tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ngo_tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pickup_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    pickup_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pickup_end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pickup_location: Mapped[str] = mapped_column(Text, nullable=False)
    pickup_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    vehicle_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    driver_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=PickupScheduleStatus.SCHEDULED.value, index=True
    )
    scheduled_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    rescheduled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rescheduled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    missed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    claim: Mapped["SurplusClaim"] = relationship("SurplusClaim", back_populates="pickup_schedule")
    listing: Mapped["SurplusListing"] = relationship("SurplusListing", back_populates="pickup_schedules")
    donor_tenant: Mapped["Tenant"] = relationship("Tenant", foreign_keys=[donor_tenant_id])
    ngo_tenant: Mapped["Tenant"] = relationship("Tenant", foreign_keys=[ngo_tenant_id])
    scheduled_by_user: Mapped["User"] = relationship("User", foreign_keys=[scheduled_by_user_id])

    __table_args__ = (
        CheckConstraint("pickup_end_time > pickup_start_time", name="chk_pickup_time_window"),
        Index("idx_pickup_donor_status", "donor_tenant_id", "status"),
        Index("idx_pickup_ngo_status", "ngo_tenant_id", "status"),
        Index("idx_pickup_date_status", "pickup_date", "status"),
    )


class SurplusNotification(Base):
    """
    In-app notification for surplus match events, claim requests, approvals, and dispatches.
    """
    __tablename__ = "surplus_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    user: Mapped["User | None"] = relationship("User")
