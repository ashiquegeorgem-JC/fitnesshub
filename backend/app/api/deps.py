import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token
from app.database.session import get_db
from app.models.owner import Owner, OwnerSession

security_bearer = HTTPBearer(auto_error=True)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware in UTC (normalizes SQLite naive datetimes)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_current_owner_and_session(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> Tuple[Owner, OwnerSession]:
    """
    Validate the incoming JWT access token and verify that the corresponding
    owner session is active, valid, and not revoked.
    """
    token = credentials.credentials
    payload = decode_token(token, expected_type="access")

    owner_id_str = payload.get("sub")
    session_id_str = payload.get("session_id")

    if not owner_id_str or not session_id_str:
        raise UnauthorizedException(detail="Token payload is missing required claims.")

    try:
        owner_id = uuid.UUID(owner_id_str)
        session_id = uuid.UUID(session_id_str)
    except ValueError:
        raise UnauthorizedException(detail="Malformed token claims.")

    # Verify session in database
    session = db.execute(
        select(OwnerSession).where(
            OwnerSession.id == session_id,
            OwnerSession.owner_id == owner_id,
        )
    ).scalar_one_or_none()

    if not session or session.is_revoked:
        raise UnauthorizedException(
            detail="Session has been revoked or is invalid. Please log in again."
        )

    expires_at_utc = _ensure_utc(session.expires_at)
    if expires_at_utc and expires_at_utc < datetime.now(timezone.utc):
        session.is_revoked = True
        db.commit()
        raise UnauthorizedException(
            detail="Session has expired. Please log in again."
        )

    # Verify owner account
    owner = db.execute(
        select(Owner).where(Owner.id == owner_id)
    ).scalar_one_or_none()

    if not owner or owner.account_status != "active":
        raise UnauthorizedException(
            detail="Owner account is disabled or does not exist."
        )

    return owner, session


def get_current_owner(
    auth_data: Tuple[Owner, OwnerSession] = Depends(get_current_owner_and_session),
) -> Owner:
    """
    Dependency providing the currently authenticated Owner entity.
    Both owners have equal permissions.
    """
    owner, _ = auth_data
    return owner


def get_current_session(
    auth_data: Tuple[Owner, OwnerSession] = Depends(get_current_owner_and_session),
) -> OwnerSession:
    """
    Dependency providing the active OwnerSession entity.
    """
    _, session = auth_data
    return session
