"""Security & Operational Audit Event Model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, generate_uuid, utc_now

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant
    from backend.app.models.user import User


class AuditEventType(str, Enum):
    AUTH_LOGIN = "AUTH_LOGIN"
    AUTH_LOGOUT = "AUTH_LOGOUT"
    INVENTORY_CREATE = "INVENTORY_CREATE"
    INVENTORY_UPDATE = "INVENTORY_UPDATE"
    INVENTORY_DELETE = "INVENTORY_DELETE"
    CSV_IMPORT = "CSV_IMPORT"
    POS_WEBHOOK = "POS_WEBHOOK"
    ALERT_ACKNOWLEDGE = "ALERT_ACKNOWLEDGE"
    CONFIG_UPDATE = "CONFIG_UPDATE"
    SURPLUS_LISTING_CREATE = "SURPLUS_LISTING_CREATE"
    SURPLUS_LISTING_UPDATE = "SURPLUS_LISTING_UPDATE"
    SURPLUS_LISTING_CANCEL = "SURPLUS_LISTING_CANCEL"
    SURPLUS_CLAIM_REQUEST = "SURPLUS_CLAIM_REQUEST"
    SURPLUS_CLAIM_APPROVE = "SURPLUS_CLAIM_APPROVE"
    SURPLUS_CLAIM_REJECT = "SURPLUS_CLAIM_REJECT"
    SURPLUS_CLAIM_CANCEL = "SURPLUS_CLAIM_CANCEL"
    SURPLUS_TRANSFER_COMPLETE = "SURPLUS_TRANSFER_COMPLETE"
    SURPLUS_PICKUP_SCHEDULE = "SURPLUS_PICKUP_SCHEDULE"
    SURPLUS_PICKUP_RESCHEDULE = "SURPLUS_PICKUP_RESCHEDULE"
    SURPLUS_PICKUP_READY = "SURPLUS_PICKUP_READY"
    SURPLUS_PICKUP_COLLECT = "SURPLUS_PICKUP_COLLECT"
    SURPLUS_PICKUP_MISSED = "SURPLUS_PICKUP_MISSED"


class AuditEvent(Base):
    """
    Immutable audit log recording security, operational, and configuration events.
    """
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant | None"] = relationship("Tenant")
    user: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        Index("idx_audit_tenant_time", "tenant_id", "created_at"),
    )
