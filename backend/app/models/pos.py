"""POS Integration Model without Plaintext Secrets."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TenantScopedMixin, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant


class PosProvider(str, Enum):
    SQUARE = "SQUARE"
    CLOVER = "CLOVER"
    TOAST = "TOAST"
    LIGHTSPEED = "LIGHTSPEED"
    GENERIC_REST = "GENERIC_REST"


class PosIntegration(Base, TimestampMixin, TenantScopedMixin):
    """
    Stores point-of-sale integration settings.
    Secrets are never stored in plaintext; only one-way cryptographic SHA-256 hashes are stored.
    """
    __tablename__ = "pos_integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    integration_name: Mapped[str] = mapped_column(String(100), nullable=False)
    webhook_slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    webhook_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="pos_integrations")

    __table_args__ = (
        Index("idx_pos_tenant_active", "tenant_id", "is_active"),
    )
