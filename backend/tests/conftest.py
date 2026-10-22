"""Pytest fixtures for Database & Security Testing."""

from datetime import date, datetime, timedelta, timezone
from typing import Generator
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from backend.app.core.security import create_access_token, get_password_hash
from backend.app.db.base import Base
from backend.app.db.seeds import seed_standard_categories
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.tenant import BusinessType, Tenant
from backend.app.models.user import User, UserRole
from backend.app.models.alert import TenantAlertConfig


@pytest.fixture(scope="function")
def engine():
    """Create an isolated in-memory SQLite engine with StaticPool and active foreign keys."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.close()

    # Create all schema tables
    Base.metadata.create_all(bind=test_engine)

    yield test_engine

    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Provide a session bound to the function-scoped isolated engine."""
    session = Session(bind=engine, autocommit=False, autoflush=False)

    # Seed global categories for tests
    seed_standard_categories(session)

    yield session

    session.close()


@pytest.fixture
def tenant_a(db_session: Session) -> Tenant:
    """Fixture creating primary test business tenant A."""
    tenant = Tenant(
        name="Green Grocer Downtown",
        slug="green-grocer-downtown",
        business_type=BusinessType.SUPERMARKET.value,
        contact_email="owner@greengrocer.example",
        timezone="America/New_York",
        currency="USD",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()

    config = TenantAlertConfig(
        tenant_id=tenant.id,
        critical_threshold_hours=24,
        warning_threshold_days=3,
        notice_threshold_days=7,
        auto_flag_for_donation=True,
    )
    db_session.add(config)
    db_session.flush()
    db_session.commit()
    return tenant


@pytest.fixture
def tenant_b(db_session: Session) -> Tenant:
    """Fixture creating secondary isolated business tenant B."""
    tenant = Tenant(
        name="Artisan Bakery Uptown",
        slug="artisan-bakery-uptown",
        business_type=BusinessType.BAKERY.value,
        contact_email="baker@artisanbakery.example",
        timezone="America/Los_Angeles",
        currency="USD",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()

    config = TenantAlertConfig(
        tenant_id=tenant.id,
        critical_threshold_hours=12,
        warning_threshold_days=2,
        notice_threshold_days=5,
        auto_flag_for_donation=False,
    )
    db_session.add(config)
    db_session.flush()
    db_session.commit()
    return tenant


@pytest.fixture
def user_a_owner(db_session: Session, tenant_a: Tenant) -> User:
    """Fixture creating owner user for Tenant A."""
    user = User(
        tenant_id=tenant_a.id,
        email="alice@greengrocer.example",
        hashed_password=get_password_hash("SecurePassword123!"),
        full_name="Alice Owner",
        role=UserRole.BUSINESS_OWNER.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def user_a_staff(db_session: Session, tenant_a: Tenant) -> User:
    """Fixture creating inventory staff user for Tenant A."""
    user = User(
        tenant_id=tenant_a.id,
        email="bob.staff@greengrocer.example",
        hashed_password=get_password_hash("StaffPassword123!"),
        full_name="Bob Staff",
        role=UserRole.INVENTORY_STAFF.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def user_b_owner(db_session: Session, tenant_b: Tenant) -> User:
    """Fixture creating owner user for Tenant B."""
    user = User(
        tenant_id=tenant_b.id,
        email="charlie@artisanbakery.example",
        hashed_password=get_password_hash("BakerPassword123!"),
        full_name="Charlie Baker",
        role=UserRole.BUSINESS_OWNER.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def token_a_owner(tenant_a: Tenant, user_a_owner: User) -> str:
    """Bearer access token for Tenant A Owner."""
    return create_access_token(
        subject=user_a_owner.id,
        tenant_id=tenant_a.id,
        role=user_a_owner.role,
    )


@pytest.fixture
def token_a_staff(tenant_a: Tenant, user_a_staff: User) -> str:
    """Bearer access token for Tenant A Staff."""
    return create_access_token(
        subject=user_a_staff.id,
        tenant_id=tenant_a.id,
        role=user_a_staff.role,
    )


@pytest.fixture
def token_b_owner(tenant_b: Tenant, user_b_owner: User) -> str:
    """Bearer access token for Tenant B Owner."""
    return create_access_token(
        subject=user_b_owner.id,
        tenant_id=tenant_b.id,
        role=user_b_owner.role,
    )


@pytest.fixture
def client(db_session: Session):
    """FastAPI TestClient with isolated test database session override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
