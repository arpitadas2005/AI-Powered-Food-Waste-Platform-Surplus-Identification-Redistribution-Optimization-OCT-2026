"""Inventory Item Model."""

from datetime import date
from enum import Enum
from typing import List, TYPE_CHECKING
from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TenantScopedMixin, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant
    from backend.app.models.category import Category
    from backend.app.models.transaction import StockTransaction
    from backend.app.models.alert import ExpiryAlertHistory
    from backend.app.models.surplus import SurplusListing


class InventoryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"
    DEPLETED = "DEPLETED"
    DONATED = "DONATED"
    DISCARDED = "DISCARDED"


class ItemUnit(str, Enum):
    KG = "kg"
    G = "g"
    LITERS = "liters"
    ML = "ml"
    UNITS = "units"
    BOXES = "boxes"
    PACKS = "packs"


class InventoryItem(Base, TimestampMixin, TenantScopedMixin):
    """
    Central inventory item model. Tracks lot-level physical stock,
    expiration dates, and storage condition constraints under strict tenant ownership.
    """
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("categories.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    current_quantity: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0.00
    )
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default=ItemUnit.UNITS.value)
    cost_per_unit: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0.00
    )
    selling_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_requirement: Mapped[str] = mapped_column(String(30), nullable=False, default="AMBIENT")
    storage_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=InventoryStatus.ACTIVE.value, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="inventory_items")
    category: Mapped["Category"] = relationship("Category", back_populates="inventory_items")
    transactions: Mapped[List["StockTransaction"]] = relationship(
        "StockTransaction", back_populates="item", cascade="all, delete-orphan"
    )
    alert_history: Mapped[List["ExpiryAlertHistory"]] = relationship(
        "ExpiryAlertHistory", back_populates="item", cascade="all, delete-orphan"
    )
    surplus_listings: Mapped[List["SurplusListing"]] = relationship(
        "SurplusListing", back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("current_quantity >= 0", name="chk_inventory_qty_non_negative"),
        CheckConstraint("cost_per_unit >= 0", name="chk_inventory_cost_non_negative"),
        CheckConstraint("expiry_date >= purchase_date", name="chk_expiry_after_purchase"),
        Index("idx_inventory_tenant_sku", "tenant_id", "sku", unique=True),
        Index("idx_inventory_tenant_expiry", "tenant_id", "expiry_date"),
        Index("idx_inventory_tenant_barcode", "tenant_id", "barcode"),
        Index("idx_inventory_tenant_status", "tenant_id", "status"),
        Index("idx_inventory_tenant_category", "tenant_id", "category_id"),
    )
