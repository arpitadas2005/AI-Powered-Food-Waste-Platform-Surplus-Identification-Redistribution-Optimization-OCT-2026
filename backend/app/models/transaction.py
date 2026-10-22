"""Stock Transaction Immutable Audit Ledger Model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TenantScopedMixin, generate_uuid, utc_now

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant
    from backend.app.models.inventory import InventoryItem
    from backend.app.models.user import User


class TransactionType(str, Enum):
    INITIAL_COUNT = "INITIAL_COUNT"
    RESTOCK = "RESTOCK"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    POS_SALE = "POS_SALE"
    SPOILAGE_DISCARD = "SPOILAGE_DISCARD"
    DONATION_HOLD = "DONATION_HOLD"
    DONATION_DISPATCH = "DONATION_DISPATCH"
    CORRECTION = "CORRECTION"


class ReferenceType(str, Enum):
    POS_ORDER = "POS_ORDER"
    CSV_IMPORT_JOB = "CSV_IMPORT_JOB"
    DONATION_LISTING = "DONATION_LISTING"
    MANUAL_ENTRY = "MANUAL_ENTRY"


class StockTransaction(Base, TenantScopedMixin):
    """
    Immutable audit ledger for every stock change.
    Guarantees mathematical reconciliation: quantity_after = quantity_before + quantity_change.
    """
    __tablename__ = "stock_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity_change: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_before: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_after: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="stock_transactions")
    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="transactions")
    user: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        CheckConstraint("quantity_before >= 0", name="chk_tx_before_non_negative"),
        CheckConstraint("quantity_after >= 0", name="chk_tx_after_non_negative"),
        CheckConstraint("quantity_after = quantity_before + quantity_change", name="chk_tx_quantity_math"),
        Index("idx_tx_tenant_item_time", "tenant_id", "item_id", "created_at"),
        Index("idx_tx_tenant_ref", "tenant_id", "reference_type", "reference_id"),
    )
