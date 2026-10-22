"""Tenant Isolation and Security Access Control Service."""

from dataclasses import dataclass
from typing import Any, Optional, Type, TypeVar
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.models.tenant import Tenant
from backend.app.models.user import User, UserRole

ModelType = TypeVar("ModelType")


class TenantIsolationError(Exception):
    """Base exception for tenant boundary violations."""
    pass


class TenantNotFoundError(TenantIsolationError):
    """Raised when tenant is inactive or not found."""
    pass


class CrossTenantAccessError(TenantIsolationError):
    """
    Raised when an operation attempts to access or mutate a record
    belonging to another tenant.
    """
    pass


@dataclass(frozen=True)
class TenantContext:
    """
    Immutable representation of the authenticated security principal and tenant context.
    Built strictly from verified JWT claims and database records.
    """
    tenant_id: str
    user_id: str
    role: str
    business_name: str
    timezone: str


def resolve_tenant_context(
    session: Session,
    user_id: str,
    claim_tenant_id: Optional[str],
) -> TenantContext:
    """
    Resolves and verifies tenant membership against the database.
    Never trusts client input; verifies that:
    1. User exists and is active.
    2. User's database tenant_id matches the claim (for non-system admins).
    3. The tenant organization exists and is active.
    """
    user = session.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    ).scalar_one_or_none()

    if not user:
        raise TenantNotFoundError("Authenticated user does not exist or is inactive")

    # System admin override (can operate across tenants if explicitly targeted)
    if user.role == UserRole.SYSTEM_ADMIN.value:
        target_tenant_id = claim_tenant_id or user.tenant_id
        if not target_tenant_id:
            return TenantContext(
                tenant_id="",
                user_id=user.id,
                role=user.role,
                business_name="System Administrator",
                timezone="UTC",
            )
        tenant = session.execute(
            select(Tenant).where(Tenant.id == target_tenant_id, Tenant.is_active == True)
        ).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundError("Targeted tenant does not exist or is inactive")
        return TenantContext(
            tenant_id=tenant.id,
            user_id=user.id,
            role=user.role,
            business_name=tenant.name,
            timezone=tenant.timezone,
        )

    # Standard tenant users MUST belong to a valid tenant
    if not user.tenant_id:
        raise TenantNotFoundError("User is not associated with any tenant organization")

    # Prevent token claim spoofing
    if claim_tenant_id and claim_tenant_id != user.tenant_id:
        raise CrossTenantAccessError("Token tenant claim does not match user database record")

    tenant = session.execute(
        select(Tenant).where(Tenant.id == user.tenant_id, Tenant.is_active == True)
    ).scalar_one_or_none()

    if not tenant:
        raise TenantNotFoundError("Tenant organization does not exist or has been deactivated")

    return TenantContext(
        tenant_id=tenant.id,
        user_id=user.id,
        role=user.role,
        business_name=tenant.name,
        timezone=tenant.timezone,
    )


def scope_query(
    stmt: Select,
    model_cls: Type[Any],
    tenant_id: str,
) -> Select:
    """
    Automatically append tenant_id filtering to any SQLAlchemy query statement.
    Ensures queries cannot return records outside the specified tenant boundary.
    """
    if hasattr(model_cls, "tenant_id"):
        return stmt.where(model_cls.tenant_id == tenant_id)
    return stmt


def verify_tenant_ownership(
    record: Any,
    tenant_id: str,
    resource_name: str = "Resource",
) -> None:
    """
    Verify that an existing model instance belongs to the authenticated tenant.
    Raises CrossTenantAccessError if ownership is mismatched.
    """
    if record is None:
        return

    record_tenant_id = getattr(record, "tenant_id", None)
    if record_tenant_id != tenant_id:
        raise CrossTenantAccessError(
            f"{resource_name} does not belong to the active tenant"
        )


def enforce_tenant_ownership(
    record: Any,
    tenant_id: str,
) -> None:
    """
    Explicitly assign the verified tenant_id to a new record,
    overwriting any user-supplied or spoofed tenant value.
    """
    setattr(record, "tenant_id", tenant_id)


def get_postgresql_rls_ddl() -> str:
    """
    Returns SQL DDL statements to configure PostgreSQL Row-Level Security (RLS)
    for all tenant-scoped tables as layer-2 defense-in-depth.
    """
    tables = [
        "inventory_items",
        "stock_transactions",
        "tenant_alert_configs",
        "expiry_alert_history",
        "csv_import_jobs",
        "csv_import_row_errors",
        "pos_integrations",
        "surplus_listings",
    ]

    ddl_statements = []
    for table in tables:
        ddl_statements.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        ddl_statements.append(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')) "
            f"WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));"
        )

    return "\n".join(ddl_statements)
