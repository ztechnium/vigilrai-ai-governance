"""Database connection and session management."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from rai_gateway.core.config import settings

# Database engine with connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,  # Verify connections before use
    echo=False,  # Set to True for SQL query logging in development
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Verify database connectivity at startup.

    Schema is managed exclusively by Alembic migrations — never create_all().
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


@contextmanager
def get_db_session() -> Generator:
    """Get database session with automatic cleanup."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator:
    """Dependency for FastAPI to get database session.

    Commits on successful request completion. Rollbacks on error.
    Matches ``get_db_session`` so flush-only service methods persist.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
