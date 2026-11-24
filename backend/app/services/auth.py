import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    RateLimitExceededException,
    ResourceNotFoundException,
    UnauthorizedException,
)
from app.core.logging import logger
from app.core.rate_limit import limiter
from app.core.security import (
    compute_otp_hmac,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    generate_numeric_otp,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_otp_hmac,
    verify_password,
)
from app.models.owner import Owner, OwnerPasswordResetOTP, OwnerSession
from app.schemas.auth import (
    MessageResponse,
    TokenResponse,
    VerifyOTPResponse,
)
from app.services.audit import log_audit_event
from app.services.sms import get_sms_provider


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware in UTC (normalizes SQLite naive datetimes)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def authenticate_owner(
    db: Session,
    phone_number: str,
    password: str,
    device_info: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> TokenResponse:
    """
    Authenticate an owner using phone number and password.
    Enforces login attempt rate limiting and Argon2id verification.
    Issues JWT access token and refresh token, recorded in owner_sessions.
    """
    # Rate limit check per phone number and per IP address
    rate_key_phone = f"login:phone:{phone_number}"
    rate_key_ip = f"login:ip:{ip_address or 'unknown'}"

    limiter.check_or_raise(
        rate_key_phone,
        max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        action_name="login attempts",
    )
    limiter.check_or_raise(
        rate_key_ip,
        max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS * 3,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        action_name="login requests",
    )

    owner = db.execute(
        select(Owner).where(Owner.phone_number == phone_number)
    ).scalar_one_or_none()

    if not owner or owner.account_status != "active":
        # Audit failed login attempt without revealing account existence
        nil_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        log_audit_event(
            db=db,
            action="LOGIN_FAILED",
            entity_type="owner",
            entity_id=owner.id if owner else nil_id,
            owner_id=owner.id if owner else None,
            new_values={"reason": "invalid_credentials"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise UnauthorizedException(
            detail="Invalid phone number or password."
        )

    if not verify_password(password, owner.password_hash):
        log_audit_event(
            db=db,
            action="LOGIN_FAILED",
            entity_type="owner",
            entity_id=owner.id,
            owner_id=owner.id,
            new_values={"reason": "invalid_credentials"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise UnauthorizedException(
            detail="Invalid phone number or password."
        )

    # Authentication successful — clear rate limit
    limiter.reset(rate_key_phone)

    # Create session record
    session_id = uuid.uuid4()
    access_token = create_access_token(owner.id, session_id)
    refresh_token = create_refresh_token(owner.id, session_id)
    rf_hash = hash_refresh_token(refresh_token)

    now = datetime.now(timezone.utc)
    session_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    clean_device = device_info[:255] if device_info else None
    clean_ip = ip_address[:45] if ip_address else None

    session = OwnerSession(
        id=session_id,
        owner_id=owner.id,
        refresh_token_hash=rf_hash,
        device_info=clean_device,
        ip_address=clean_ip,
        is_revoked=False,
        expires_at=session_expires,
    )
    db.add(session)

    # Update owner last login timestamp
    owner.last_login_at = now

    # Record successful login in audit log
    log_audit_event(
        db=db,
        action="LOGIN_SUCCESS",
        entity_type="owner_session",
        entity_id=session_id,
        owner_id=owner.id,
        new_values={"device_info": clean_device},
        ip_address=clean_ip,
        user_agent=user_agent,
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def refresh_token_pair(
    db: Session,
    refresh_token: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> TokenResponse:
    """
    Rotate a refresh token and issue a new access/refresh token pair.

    Concurrency safety (C1):
    - The session row is locked with SELECT FOR UPDATE before the hash is
      compared and before the new hash is written.
    - Under PostgreSQL, two concurrent requests carrying the same token will
      race for the row lock. The second request will read the already-rotated
      hash after the first transaction commits, triggering reuse detection and
      revoking all sessions.
    - SQLite (used in tests) does not support SELECT FOR UPDATE; the .with_for_update()
      call is silently ignored. Concurrency correctness under real load therefore
      requires PostgreSQL and must be verified with integration tests against a
      live PostgreSQL instance (see CONCURRENCY_NOTES.md).

    Reuse detection:
    - If an already-rotated or revoked refresh token is presented, all sessions
      for that owner are immediately revoked as a security response.
    """
    payload = decode_token(refresh_token, expected_type="refresh")
    owner_id = uuid.UUID(payload["sub"])
    session_id = uuid.UUID(payload["session_id"])

    provided_hash = hash_refresh_token(refresh_token)

    # --- C1 FIX: Acquire an exclusive row lock before reading or modifying ---
    # This prevents two concurrent requests with the same refresh token from
    # both passing the hash comparison and both issuing new token pairs.
    # On PostgreSQL this serialises concurrent refresh operations for this session.
    # On SQLite (tests) with_for_update() is a no-op — see docstring.
    session = db.execute(
        select(OwnerSession)
        .where(OwnerSession.id == session_id)
        .with_for_update()
    ).scalar_one_or_none()

    if not session:
        raise UnauthorizedException(detail="Session not found or expired.")

    # Replay/Reuse Detection:
    # 1. Session is already revoked
    # 2. Token hash doesn't match current session hash (old token replayed)
    if session.is_revoked or session.refresh_token_hash != provided_hash:
        logger.warning(
            f"Security Alert: Refresh token reuse detected for owner {owner_id}, "
            f"session {session_id}. Revoking all sessions."
        )
        # Revoke all active sessions for this owner as a security measure
        active_sessions = db.execute(
            select(OwnerSession).where(
                OwnerSession.owner_id == owner_id,
                OwnerSession.is_revoked.is_(False),
            )
        ).scalars().all()
        for s in active_sessions:
            s.is_revoked = True

        log_audit_event(
            db=db,
            action="REFRESH_TOKEN_REUSE_DETECTED",
            entity_type="owner_session",
            entity_id=session.id,
            owner_id=owner_id,
            new_values={
                "reason": "token_replay_detected",
                "sessions_revoked": len(active_sessions),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise UnauthorizedException(
            detail="Token reuse detected. All active sessions have been revoked for your security."
        )

    # Check session expiration
    now = datetime.now(timezone.utc)
    session_exp = _ensure_utc(session.expires_at)
    if session_exp and session_exp < now:
        session.is_revoked = True
        db.commit()
        raise UnauthorizedException(
            detail="Session has expired. Please log in again."
        )

    # Issue rotated token pair
    new_access_token = create_access_token(owner_id, session_id)
    new_refresh_token = create_refresh_token(owner_id, session_id)
    new_hash = hash_refresh_token(new_refresh_token)

    # Atomically update session with rotated token hash
    session.refresh_token_hash = new_hash
    if ip_address:
        session.ip_address = ip_address[:45]

    log_audit_event(
        db=db,
        action="TOKEN_REFRESH",
        entity_type="owner_session",
        entity_id=session.id,
        owner_id=owner_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def logout_session(
    db: Session,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> MessageResponse:
    """
    Revoke a single active owner session.
    """
    session = db.execute(
        select(OwnerSession).where(
            OwnerSession.id == session_id,
            OwnerSession.owner_id == owner_id,
        )
    ).scalar_one_or_none()

    if not session:
        raise ResourceNotFoundException(resource="Session", identifier=str(session_id))

    session.is_revoked = True
    log_audit_event(
        db=db,
        action="LOGOUT",
        entity_type="owner_session",
        entity_id=session_id,
        owner_id=owner_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return MessageResponse(message="Successfully logged out.")


def logout_all_sessions(
    db: Session,
    owner_id: uuid.UUID,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> MessageResponse:
    """
    Revoke all active sessions for an owner.
    """
    active_sessions = db.execute(
        select(OwnerSession).where(
            OwnerSession.owner_id == owner_id,
            OwnerSession.is_revoked.is_(False),
        )
    ).scalars().all()

    count = len(active_sessions)
    for s in active_sessions:
        s.is_revoked = True

    log_audit_event(
        db=db,
        action="LOGOUT_ALL_SESSIONS",
        entity_type="owner",
        entity_id=owner_id,
        owner_id=owner_id,
        new_values={"revoked_count": count},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return MessageResponse(
        message=f"Successfully revoked all {count} active session(s)."
    )


def list_owner_sessions(
    db: Session, owner_id: uuid.UUID, current_session_id: uuid.UUID
) -> List[dict]:
    """
    Retrieve all sessions belonging to the owner.
    """
    sessions = db.execute(
        select(OwnerSession)
        .where(OwnerSession.owner_id == owner_id)
        .order_by(OwnerSession.created_at.desc())
    ).scalars().all()

    return [
        {
            "id": s.id,
            "device_info": s.device_info,
            "ip_address": s.ip_address,
            "is_revoked": s.is_revoked,
            "expires_at": s.expires_at,
            "created_at": s.created_at,
            "is_current": s.id == current_session_id,
        }
        for s in sessions
    ]


def request_password_reset_otp(
    db: Session,
    phone_number: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> MessageResponse:
    """
    Generate and dispatch a 6-digit numeric recovery OTP via configured SMS provider.
    Enforces cooldown and never reveals account existence for unknown numbers.
    """
    # Rate limit OTP generation per phone and IP
    rate_key_phone = f"otp_request:{phone_number}"
    rate_key_ip = f"otp_request:ip:{ip_address or 'unknown'}"
    limiter.check_or_raise(
        rate_key_phone,
        max_attempts=3,
        window_seconds=900,  # 3 attempts per 15 minutes
        action_name="OTP requests",
    )
    limiter.check_or_raise(
        rate_key_ip,
        max_attempts=10,
        window_seconds=900,  # 10 attempts per 15 minutes per IP
        action_name="OTP requests",
    )

    owner = db.execute(
        select(Owner).where(Owner.phone_number == phone_number)
    ).scalar_one_or_none()

    generic_msg = (
        "If this mobile number is registered with Regal Fitness, "
        "a verification code has been dispatched via SMS."
    )

    if not owner or owner.account_status != "active":
        # Silently return generic response to prevent phone enumeration
        return MessageResponse(message=generic_msg)

    # Check cooldown on existing OTPs
    now = datetime.now(timezone.utc)
    latest_otp = db.execute(
        select(OwnerPasswordResetOTP)
        .where(
            OwnerPasswordResetOTP.owner_id == owner.id,
            OwnerPasswordResetOTP.is_used.is_(False),
        )
        .order_by(OwnerPasswordResetOTP.created_at.desc())
    ).scalars().first()

    if latest_otp:
        cooldown_dt = _ensure_utc(latest_otp.cooldown_until)
        if cooldown_dt and cooldown_dt > now:
            retry_after = int((cooldown_dt - now).total_seconds()) + 1
            raise RateLimitExceededException(
                detail=f"Please wait {retry_after} seconds before requesting a new OTP.",
                retry_after=retry_after,
            )

    # Generate cryptographically secure OTP
    otp = generate_numeric_otp(6)
    otp_hmac = compute_otp_hmac(otp)

    expiry = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    cooldown = now + timedelta(seconds=settings.OTP_COOLDOWN_SECONDS)

    otp_record = OwnerPasswordResetOTP(
        id=uuid.uuid4(),
        owner_id=owner.id,
        otp_hmac=otp_hmac,
        attempts_count=0,
        is_used=False,
        cooldown_until=cooldown,
        expires_at=expiry,
    )
    db.add(otp_record)

    # Dispatch OTP through SMS provider adapter
    sms_provider = get_sms_provider()
    sms_provider.send_otp(phone_number, otp)

    log_audit_event(
        db=db,
        action="PASSWORD_RESET_REQUESTED",
        entity_type="owner_password_reset_otp",
        entity_id=otp_record.id,
        owner_id=owner.id,
        new_values={"expires_at": expiry.isoformat()},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()

    return MessageResponse(message=generic_msg)


def verify_password_reset_otp(
    db: Session,
    phone_number: str,
    otp: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> VerifyOTPResponse:
    """
    Verify an entered OTP against HMAC storage with attempt counting (max 3).
    Issues a short-lived single-use reset_token on successful verification.

    Concurrency safety (C2, H1):
    - The OTP record is locked with SELECT FOR UPDATE before the attempt counter
      is read and before is_used is checked. This prevents:
      (a) Two concurrent correct-OTP requests both receiving a reset token.
      (b) Two concurrent wrong-OTP requests both reading the same attempts_count
          and both writing back the same incremented value, allowing bypass of
          the 3-attempt limit.
    - On PostgreSQL, concurrent requests serialize on the row lock. The second
      request will see the updated is_used=True flag after the first commits.
    - On SQLite (tests) with_for_update() is a no-op — see authenticate_owner
      docstring for the testing caveat.

    Single-use enforcement (C2):
    - is_used is set to True BEFORE returning the reset_token. Any further
      verification attempt for this OTP record is immediately rejected.
    """
    # M1 FIX: HTTP-layer rate limit on OTP verification per phone and IP
    rate_key_phone = f"otp_verify:phone:{phone_number}"
    rate_key_ip = f"otp_verify:ip:{ip_address or 'unknown'}"

    limiter.check_or_raise(
        rate_key_phone,
        max_attempts=settings.OTP_VERIFY_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds=settings.OTP_VERIFY_RATE_LIMIT_WINDOW_SECONDS,
        action_name="OTP verification attempts",
    )
    limiter.check_or_raise(
        rate_key_ip,
        max_attempts=settings.OTP_VERIFY_RATE_LIMIT_MAX_ATTEMPTS * 2,
        window_seconds=settings.OTP_VERIFY_RATE_LIMIT_WINDOW_SECONDS,
        action_name="OTP verification attempts",
    )

    owner = db.execute(
        select(Owner).where(Owner.phone_number == phone_number)
    ).scalar_one_or_none()

    if not owner:
        raise BadRequestException(detail="Invalid or expired verification code.")

    # Find active unexpired OTP
    now = datetime.now(timezone.utc)

    # --- C2 + H1 FIX: Lock the OTP row before reading or modifying any state ---
    # Fetch the latest OTP record for this owner (regardless of is_used) to
    # distinguish attempt exhaustion from already-used or non-existent requests.
    otp_record = db.execute(
        select(OwnerPasswordResetOTP)
        .where(OwnerPasswordResetOTP.owner_id == owner.id)
        .order_by(OwnerPasswordResetOTP.created_at.desc())
        .with_for_update()
    ).scalars().first()

    if not otp_record:
        raise BadRequestException(
            detail="No active password reset request found. Please request a new code."
        )

    # If attempts are already exhausted, block immediately with specific message
    if otp_record.attempts_count >= settings.OTP_MAX_ATTEMPTS:
        raise BadRequestException(
            detail="Maximum verification attempts exceeded. Please request a new code."
        )

    # If already successfully used, block immediately
    if otp_record.is_used:
        raise BadRequestException(
            detail="Verification code has already been used. Please request a new code."
        )

    otp_exp = _ensure_utc(otp_record.expires_at)
    if otp_exp and otp_exp < now:
        raise BadRequestException(
            detail="Verification code has expired. Please request a new code."
        )

    # Increment verification attempt count atomically (inside the lock)
    otp_record.attempts_count += 1

    if not verify_otp_hmac(otp, otp_record.otp_hmac):
        # If this was the last allowed attempt, invalidate the OTP immediately
        if otp_record.attempts_count >= settings.OTP_MAX_ATTEMPTS:
            otp_record.is_used = True

        remaining = max(0, settings.OTP_MAX_ATTEMPTS - otp_record.attempts_count)
        log_audit_event(
            db=db,
            action="OTP_VERIFICATION_FAILED",
            entity_type="owner_password_reset_otp",
            entity_id=otp_record.id,
            owner_id=owner.id,
            new_values={"attempts_count": otp_record.attempts_count},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        if remaining == 0:
            raise BadRequestException(
                detail="Maximum verification attempts exceeded. Please request a new code."
            )
        raise BadRequestException(
            detail=f"Invalid verification code. {remaining} attempt(s) remaining."
        )

    # C2 FIX: Mark the OTP as used BEFORE returning the reset token.
    # Any subsequent verification attempt against this OTP record is immediately
    # rejected by the is_used check above.
    otp_record.is_used = True

    log_audit_event(
        db=db,
        action="OTP_VERIFICATION_SUCCESS",
        entity_type="owner_password_reset_otp",
        entity_id=otp_record.id,
        owner_id=owner.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()

    # Generate single-use reset token (otp_id embedded for double-verification in reset step)
    reset_token = create_password_reset_token(owner.id, otp_record.id)
    return VerifyOTPResponse(reset_token=reset_token)


def reset_owner_password(
    db: Session,
    reset_token: str,
    new_password: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> MessageResponse:
    """
    Set a new password after verifying the reset_token issued by verify_password_reset_otp.
    Enforces password complexity, updates Argon2id hash, invalidates OTP,
    and revokes all active owner sessions.

    Single-use enforcement (independent secondary layer):
    - The otp_id embedded in the reset JWT is used to look up the OTP record.
    - If otp_record.is_used is False, the token is invalid (OTP was never verified).
    - If otp_record.expires_at is already in the past, the token has either expired
      or has already been consumed by a prior password reset.
    - Upon successful password reset, otp_record.expires_at is set to the past
      (now - 1 second) and attempts_count is set to OTP_MAX_ATTEMPTS, ensuring
      that any replay attempt with the same reset token is permanently rejected.
    """
    # Rate limit password reset requests per IP to mitigate DoS/brute-force against Argon2id
    rate_key_ip = f"password_reset:ip:{ip_address or 'unknown'}"
    limiter.check_or_raise(
        rate_key_ip,
        max_attempts=10,
        window_seconds=300,  # 10 attempts per 5 minutes per IP
        action_name="password reset attempts",
    )

    payload = decode_token(reset_token, expected_type="password_reset")
    owner_id = uuid.UUID(payload["sub"])
    otp_id = uuid.UUID(payload["otp_id"])

    owner = db.execute(
        select(Owner).where(Owner.id == owner_id)
    ).scalar_one_or_none()
    if not owner:
        raise UnauthorizedException(detail="Owner account not found.")

    otp_record = db.execute(
        select(OwnerPasswordResetOTP).where(
            OwnerPasswordResetOTP.id == otp_id,
            OwnerPasswordResetOTP.owner_id == owner_id,
        ).with_for_update()
    ).scalar_one_or_none()

    if not otp_record or not otp_record.is_used:
        raise BadRequestException(
            detail="Password reset token is invalid. Please complete OTP verification first."
        )

    now = datetime.now(timezone.utc)
    otp_exp = _ensure_utc(otp_record.expires_at)
    if not otp_exp or otp_exp < now:
        raise BadRequestException(
            detail="Password reset token has already been used or has expired."
        )

    # Validate password complexity
    pwd_err = validate_password_strength(new_password)
    if pwd_err:
        raise BadRequestException(detail=pwd_err)

    # Hash new password with Argon2id
    new_hash = hash_password(new_password)
    owner.password_hash = new_hash

    # Invalidate OTP record so this reset token cannot be used again
    otp_record.expires_at = now - timedelta(seconds=1)
    otp_record.attempts_count = settings.OTP_MAX_ATTEMPTS

    # Revoke all existing sessions for this owner (security requirement)
    sessions = db.execute(
        select(OwnerSession).where(
            OwnerSession.owner_id == owner.id,
            OwnerSession.is_revoked.is_(False),
        )
    ).scalars().all()
    for s in sessions:
        s.is_revoked = True

    log_audit_event(
        db=db,
        action="PASSWORD_RESET_SUCCESS",
        entity_type="owner",
        entity_id=owner.id,
        owner_id=owner.id,
        new_values={"sessions_revoked": len(sessions)},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()

    return MessageResponse(
        message="Password has been reset successfully. Please log in with your new credentials."
    )
