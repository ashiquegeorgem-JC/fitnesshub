import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.exceptions import UnauthorizedException

# Argon2id password hasher with standard secure parameters
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using Argon2id.
    """
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against an Argon2id hash.
    Returns True if matches, False otherwise. Never throws on mismatch.
    """
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> Optional[str]:
    """
    Validate that a password meets the full Regal Fitness complexity policy:
      - Minimum 8 characters
      - At least 1 uppercase letter (A-Z)
      - At least 1 lowercase letter (a-z)
      - At least 1 digit (0-9)
      - At least 1 special character (!@#$%^&*(),.?":{}|<>-_+=[]\\;'`~)
    Returns an error message string if invalid, or None if the password is valid.
    """
    import re
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter (A-Z)."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter (a-z)."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit (0-9)."
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>?/\\|`~]', password):
        return "Password must contain at least one special character (e.g. !@#$%^&*)."
    return None


def generate_numeric_otp(length: int = 6) -> str:
    """
    Generate a cryptographically secure numeric OTP of the specified length.
    """
    return "".join(secrets.choice("0123456789") for _ in range(length))


def compute_otp_hmac(otp: str, secret: Optional[str] = None) -> str:
    """
    Compute the HMAC-SHA256 representation of a raw OTP using the server secret.
    The raw OTP must never be stored in the database.
    """
    key = (secret or settings.OTP_HMAC_SECRET).encode("utf-8")
    return hmac.new(key, otp.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp_hmac(
    otp: str, expected_hmac: str, secret: Optional[str] = None
) -> bool:
    """
    Verify an entered OTP against the stored HMAC using constant-time comparison.
    """
    computed = compute_otp_hmac(otp, secret)
    return hmac.compare_digest(computed, expected_hmac)


def hash_refresh_token(token: str) -> str:
    """
    Compute the SHA-256 hash of a refresh token for storage in owner_sessions.
    Raw refresh tokens are never persisted in the database.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.
    Payload includes owner_id (sub), session_id, token_type ('access'), and expiration.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(owner_id),
        "session_id": str(session_id),
        "type": "access",
        "jti": secrets.token_hex(16),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT refresh token with unique jti for rotation tracking.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub": str(owner_id),
        "session_id": str(session_id),
        "type": "refresh",
        "jti": secrets.token_hex(16),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_password_reset_token(
    owner_id: uuid.UUID,
    otp_id: uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a short-lived token issued only after successful OTP verification,
    permitting the owner to set a new password.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(owner_id),
        "otp_id": str(otp_id),
        "type": "password_reset",
        "jti": secrets.token_hex(16),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(
    token: str, expected_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Decode, verify signature, and validate token expiration and type.
    Raises UnauthorizedException on expired, malformed, or mismatched tokens.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedException(detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise UnauthorizedException(detail="Invalid or malformed token.")

    if expected_type and payload.get("type") != expected_type:
        raise UnauthorizedException(
            detail=f"Invalid token type. Expected '{expected_type}'."
        )

    return payload
