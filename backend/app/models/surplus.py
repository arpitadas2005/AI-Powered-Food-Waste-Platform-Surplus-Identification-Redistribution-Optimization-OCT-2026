"""Surplus Donation Listing Foundation Model (Milestones 2 & 3 Support)."""

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant
    from backend.app.models.inventory import InventoryItem
    from backend.app.models.user import User


class SurplusStatus(str, Enum):
    DRAFT = "DRAFT"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    CLAIMED = "CLAIMED"
    PICKED_UP = "PICKED_UP"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


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
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SurplusStatus.AVAILABLE.value, index=True
    )
    pickup_address: Mapped[str] = mapped_column(Text, nullable=False)
    pickup_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_surplus_qty_positive"),
        CheckConstraint("available_until > available_from", name="chk_surplus_window"),
        Index("idx_surplus_tenant_status", "tenant_id", "status"),
        Index("idx_surplus_window_status", "status", "available_until"),
    )
