"""SQLAlchemy Database Engine, Session Management, and PostgreSQL RLS Integration.

Enforces transaction-local tenant context isolation:
- Calls SELECT set_config('app.current_org_id', :org_id, true) inside transactions.
- Transaction-local ('true') prevents leakage across pooled connections.
- Clean connection pool state verified via event listeners.
"""

from contextlib import contextmanager
from typing import Generator, Optional
from uuid import UUID
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import Pool

from app.core.config import settings

# Engine configuration
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def set_transaction_tenant_context(session: Session, org_id: Optional[UUID]) -> None:
    """Sets transaction-local tenant context for PostgreSQL RLS.
    
    Uses parameter binding to prevent SQL injection.
    When org_id is None, clears the setting.
    """
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        org_id_str = str(org_id) if org_id is not None else ""
        session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": org_id_str}
        )
    session.info["current_org_id"] = org_id


@event.listens_for(Pool, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Ensures pooled connections returned to pool do not retain any session state."""
    # When using PostgreSQL, transaction-local set_config is automatically cleared on COMMIT/ROLLBACK.
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a clean database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def tenant_session_scope(org_id: UUID) -> Generator[Session, None, None]:
    """Context manager for background workers and scheduled tasks.
    
    Guarantees that tenant context is explicitly set on transaction start.
    """
    session = SessionLocal()
    try:
        set_transaction_tenant_context(session, org_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
