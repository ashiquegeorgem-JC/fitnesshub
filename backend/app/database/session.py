from typing import Dict, Generator
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import logger

# Database engine configured for PostgreSQL with pooling and health pre-ping
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a SQLAlchemy session per request
    and closing the connection upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connectivity() -> Dict[str, str]:
    """
    Probes database health by executing a lightweight query ('SELECT 1').
    Returns connection status and dialect information without raising exceptions.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "connected",
            "dialect": engine.dialect.name,
        }
    except SQLAlchemyError as exc:
        logger.warning(f"Database health check failed: {str(exc)}")
        return {
            "status": "disconnected",
            "dialect": engine.dialect.name,
            "message": "Database server is unreachable or offline",
        }
