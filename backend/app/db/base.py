"""SQLAlchemy Base and Model Mixins."""

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    """Generate a standard UUID4 string."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


class TimestampMixin:
    """Mixin adding created_at and updated_at UTC timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
        nullable=False,
    )


class TenantScopedMixin:
    """
    Mixin adding tenant ownership with strict foreign key cascading.
    Ensures that all business models explicitly declare multi-tenant tenancy.
    """
    @declared_attr
    def tenant_id(cls) -> Mapped[str]:
        return mapped_column(
            String(36),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
