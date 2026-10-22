"""Tenant Model for Food Businesses and Recipient Organizations."""

from enum import Enum
from typing import List, TYPE_CHECKING
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.user import User
    from backend.app.models.inventory import InventoryItem
    from backend.app.models.transaction import StockTransaction
    from backend.app.models.alert import TenantAlertConfig, ExpiryAlertHistory
    from backend.app.models.pos import PosIntegration
    from backend.app.models.surplus import SurplusListing


class BusinessType(str, Enum):
    SUPERMARKET = "SUPERMARKET"
    RESTAURANT = "RESTAURANT"
    BAKERY = "BAKERY"
    HOTEL = "HOTEL"
    WHOLESALER = "WHOLESALER"
    NGO_RECIPIENT = "NGO_RECIPIENT"


class Tenant(Base, TimestampMixin):
    """
    Represents an isolated organizational boundary (a food business or recipient NGO).
    Every business inventory record and transaction must map to a Tenant.
    """
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    business_type: Mapped[str] = mapped_column(String(50), nullable=False, default=BusinessType.SUPERMARKET.value)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships with cascade delete on tenant removal
    users: Mapped[List["User"]] = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    inventory_items: Mapped[List["InventoryItem"]] = relationship("InventoryItem", back_populates="tenant", cascade="all, delete-orphan")
    stock_transactions: Mapped[List["StockTransaction"]] = relationship("StockTransaction", back_populates="tenant", cascade="all, delete-orphan")
    alert_config: Mapped["TenantAlertConfig | None"] = relationship("TenantAlertConfig", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    alert_history: Mapped[List["ExpiryAlertHistory"]] = relationship("ExpiryAlertHistory", back_populates="tenant", cascade="all, delete-orphan")
    pos_integrations: Mapped[List["PosIntegration"]] = relationship("PosIntegration", back_populates="tenant", cascade="all, delete-orphan")
    surplus_listings: Mapped[List["SurplusListing"]] = relationship("SurplusListing", foreign_keys="SurplusListing.tenant_id", back_populates="tenant", cascade="all, delete-orphan")
