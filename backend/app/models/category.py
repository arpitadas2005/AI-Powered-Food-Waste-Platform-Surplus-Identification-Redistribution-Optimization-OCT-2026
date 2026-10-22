"""Food Categories & Storage Taxonomy Model."""

from datetime import datetime
from enum import Enum
from typing import List, TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, generate_uuid, utc_now

if TYPE_CHECKING:
    from backend.app.models.inventory import InventoryItem


class PerishabilityTier(str, Enum):
    CRITICAL = "CRITICAL"  # 1-2 days
    HIGH = "HIGH"          # 3-5 days
    MEDIUM = "MEDIUM"      # 1-2 weeks
    LOW = "LOW"            # months / non-perishable


class StorageRequirement(str, Enum):
    AMBIENT = "AMBIENT"
    REFRIGERATED = "REFRIGERATED"
    FROZEN = "FROZEN"
    DRY_PANTRY = "DRY_PANTRY"
    CLIMATE_CONTROLLED = "CLIMATE_CONTROLLED"


class Category(Base):
    """
    Standardized food taxonomy and baseline storage conditions.
    Supports system-wide global categories (tenant_id is NULL) and custom tenant categories.
    """
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    perishability_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    recommended_storage: Mapped[str] = mapped_column(String(30), nullable=False)
    temp_min_celsius: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    temp_max_celsius: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    humidity_min_pct: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    humidity_max_pct: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    default_shelf_life_days: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    # Relationships
    inventory_items: Mapped[List["InventoryItem"]] = relationship("InventoryItem", back_populates="category")

    __table_args__ = (
        Index("idx_categories_perishability", "perishability_tier"),
        Index("idx_categories_slug_tenant", "slug", "tenant_id", unique=True),
    )
