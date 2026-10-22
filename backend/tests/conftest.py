"""Pytest fixtures for Database & Security Testing."""

from datetime import date, datetime, timedelta, timezone
from typing import Generator
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.seeds import seed_standard_categories
from backend.app.models.tenant import Tenant, BusinessType
from backend.app.models.user import User, UserRole
from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus, ItemUnit
from backend.app.models.transaction import StockTransaction, TransactionType
from backend.app.models.alert import TenantAlertConfig
from backend.app.core.security import get_password_hash


@pytest.fixture(scope="session")
def engine():
    """Create an isolated in-memory SQLite engine with PRAGMA foreign_keys = ON."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
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


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Provide a transactional session rolled back after every test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autocommit=False, autoflush=False)

    # Seed global categories for tests
    seed_standard_categories(session)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


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

    # Create default alert config
    config = TenantAlertConfig(
        tenant_id=tenant.id,
        critical_threshold_hours=24,
        warning_threshold_days=3,
        notice_threshold_days=7,
        auto_flag_for_donation=True,
    )
    db_session.add(config)
    db_session.flush()
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
    db_session.flush()
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
    db_session.flush()
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
    db_session.flush()
    return user
