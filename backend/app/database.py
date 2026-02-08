"""Database connection, session management, and table initialization.

Uses lazy initialization so importing this module does NOT trigger
Settings() or engine creation at import time — important for testing
and IDE import resolution.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


def build_engine(database_url: str, echo: bool = False):
    """Create a SQLAlchemy engine.

    Uses check_same_thread=False for SQLite to allow FastAPI's
    threaded request handling.
    """
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, echo=echo, connect_args=connect_args)


def build_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Lazy application-level singletons (created on first access, not at import)
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def _get_engine():
    """Return the application-level engine, creating it on first call."""
    global _engine
    if _engine is None:
        settings = Settings()
        _engine = build_engine(settings.database_url, echo=settings.debug)
    return _engine


def _get_session_factory():
    """Return the application-level session factory, creating it on first call."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = build_session_factory(_get_engine())
    return _SessionLocal


def get_db():
    """FastAPI dependency that yields a database session per request."""
    db = _get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables that don't exist yet."""
    # Import models so they register with Base.metadata
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=_get_engine())
