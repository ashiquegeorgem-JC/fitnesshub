import uuid
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.audit import AuditLog

# Keys that must never be recorded in audit JSON payloads
SENSITIVE_AUDIT_KEYS = {
    "password",
    "password_hash",
    "raw_password",
    "new_password",
    "otp",
    "otp_hmac",
    "token",
    "access_token",
    "refresh_token",
    "reset_token",
    "secret",
}


def sanitize_audit_payload(
    payload: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Recursively remove sensitive credentials, tokens, and hashes from audit logs.
    """
    if not payload:
        return None
    sanitized: Dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in SENSITIVE_AUDIT_KEYS:
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_audit_payload(v)
        else:
            sanitized[k] = v
    return sanitized


def log_audit_event(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    owner_id: Optional[uuid.UUID] = None,
    previous_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Record an append-only audit log entry in the audit_logs ledger.
    Never exposes passwords, OTPs, or authentication tokens.
    """
    clean_prev = sanitize_audit_payload(previous_values)
    clean_new = sanitize_audit_payload(new_values)

    # Truncate user-agent if longer than 255 chars
    clean_ua = user_agent[:255] if user_agent else None

    entry = AuditLog(
        id=uuid.uuid4(),
        owner_id=owner_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_values=clean_prev,
        new_values=clean_new,
        ip_address=ip_address,
        user_agent=clean_ua,
    )
    db.add(entry)
    db.flush()
    logger.info(
        f"AuditLog recorded: action='{action}', entity='{entity_type}:{entity_id}', owner='{owner_id}'"
    )
    return entry
