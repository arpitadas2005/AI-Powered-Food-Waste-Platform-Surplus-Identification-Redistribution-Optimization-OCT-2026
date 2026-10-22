"""User and Authentication Model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.tenant import Tenant


class UserRole(str, Enum):
    BUSINESS_OWNER = "BUSINESS_OWNER"
    STORE_MANAGER = "STORE_MANAGER"
    INVENTORY_STAFF = "INVENTORY_STAFF"
    RECIPIENT_NGO = "RECIPIENT_NGO"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class User(Base, TimestampMixin):
    """
    Authenticated user account. Linked to a tenant organization
    except for platform system administrators.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=UserRole.STORE_MANAGER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="users")

    __table_args__ = (
        Index("idx_users_tenant_role", "tenant_id", "role"),
    )
