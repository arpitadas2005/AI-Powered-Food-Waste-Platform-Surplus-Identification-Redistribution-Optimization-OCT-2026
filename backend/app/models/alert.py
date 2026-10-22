"""Expiry Alert Configuration and History Models."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TenantScopedMixin, generate_uuid, utc_now

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant
    from backend.app.models.inventory import InventoryItem
    from backend.app.models.user import User


class AlertLevel(str, Enum):
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EXPIRED = "EXPIRED"


class AlertAction(str, Enum):
    DISCOUNTED_FOR_SALE = "DISCOUNTED_FOR_SALE"
    MARKED_FOR_DONATION = "MARKED_FOR_DONATION"
    DISCARDED = "DISCARDED"
    SNOOZED = "SNOOZED"


class TenantAlertConfig(Base, TenantScopedMixin):
    """
    Per-tenant customizable alert thresholds for inventory expiration monitoring.
    """
    __tablename__ = "tenant_alert_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    critical_threshold_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    warning_threshold_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    notice_threshold_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    auto_flag_for_donation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    webhook_notification_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="alert_config")

    __table_args__ = (
        CheckConstraint("critical_threshold_hours > 0", name="chk_alert_critical_hours"),
        CheckConstraint("warning_threshold_days > 0", name="chk_alert_warning_days"),
        CheckConstraint("notice_threshold_days > warning_threshold_days", name="chk_alert_notice_days"),
        Index("idx_alert_config_tenant", "tenant_id", unique=True),
    )


class ExpiryAlertHistory(Base, TenantScopedMixin):
    """
    Log of generated alerts and operational acknowledgment actions taken by staff.
    """
    __tablename__ = "expiry_alert_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_level: Mapped[str] = mapped_column(String(20), nullable=False)
    days_remaining: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="alert_history")
    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="alert_history")
    user: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        Index("idx_alerts_tenant_active", "tenant_id", "acknowledged", "alert_level"),
        Index("idx_alerts_tenant_item", "tenant_id", "item_id", "created_at"),
    )
