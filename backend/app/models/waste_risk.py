"""
Milestone 2 — Phase 4: Waste Risk Assessment and Smart Reorder Persistence Models.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant
    from backend.app.models.inventory import InventoryItem


class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReorderStatus(str, Enum):
    RECOMMENDED = "RECOMMENDED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DISMISSED = "DISMISSED"


class WasteRiskAssessmentRecord(Base, TimestampMixin):
    """
    Historical log of SKU/lot level waste risk evaluations based on
    forecast demand vs physical inventory before expiry.
    """
    __tablename__ = "waste_risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    current_stock: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    days_to_expiry: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    predicted_demand_to_expiry: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    expected_surplus_units: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    surplus_ratio: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    value_at_risk: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    recommended_action: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    item: Mapped["InventoryItem"] = relationship("InventoryItem")

    __table_args__ = (
        CheckConstraint("current_stock >= 0", name="chk_risk_stock_non_negative"),
        CheckConstraint("expected_surplus_units >= 0", name="chk_risk_surplus_non_negative"),
        CheckConstraint("value_at_risk >= 0", name="chk_risk_var_non_negative"),
        Index("idx_waste_risk_tenant_tier", "tenant_id", "risk_tier"),
        Index("idx_waste_risk_tenant_time", "tenant_id", "assessed_at"),
    )


class SmartReorderRecord(Base, TimestampMixin):
    """
    Dynamic replenishment recommendations generated from lead-time demand,
    safety stock, storage constraints, and surplus risk guards.
    """
    __tablename__ = "smart_reorder_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    current_stock: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    predicted_daily_demand: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    safety_stock: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    reorder_point: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    recommended_reorder_quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ReorderStatus.RECOMMENDED.value, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    is_blocked_by_expiry_risk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    item: Mapped["InventoryItem"] = relationship("InventoryItem")

    __table_args__ = (
        CheckConstraint("current_stock >= 0", name="chk_reorder_stock_non_negative"),
        CheckConstraint("recommended_reorder_quantity >= 0", name="chk_reorder_qty_non_negative"),
        Index("idx_reorder_tenant_status", "tenant_id", "status"),
    )
