"""Database Engine, Session Management, and Dialect Event Hooks."""

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import settings


def create_app_engine(database_url: str = settings.DATABASE_URL) -> Engine:
    """Create a configured SQLAlchemy engine with dialect-specific optimizations."""
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        echo=False,
    )

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """Enforce foreign key constraints and WAL mode in SQLite."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.close()

    return engine


engine = create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a managed database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_tenant_context(session: Session, tenant_id: str) -> None:
    """
    Hook to configure database-level tenant context when PostgreSQL RLS is enabled.
    In SQLite, this is a no-op as server-side ORM scoping enforces isolation.
    """
    bind = session.get_bind()
    if bind and bind.dialect.name == "postgresql":
        session.execute(
            f"SET LOCAL app.current_tenant_id = '{tenant_id}';"
        )
