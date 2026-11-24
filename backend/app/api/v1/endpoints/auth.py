import uuid
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_owner,
    get_current_owner_and_session,
    get_db,
)
from app.models.owner import Owner, OwnerSession
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OwnerProfileResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SessionResponse,
    TokenResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.services.auth import (
    authenticate_owner,
    list_owner_sessions,
    logout_all_sessions,
    logout_session,
    refresh_token_pair,
    request_password_reset_otp,
    reset_owner_password,
    verify_password_reset_otp,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _extract_request_metadata(request: Request) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract the resolved client IP address and User-Agent from the request.

    Trusted Proxy IP Resolution (H2 fix):
    - X-Forwarded-For is ONLY honoured when the direct TCP peer
      (request.client.host) is listed in TRUSTED_PROXY_IPS.
    - If the direct peer is not a trusted proxy, X-Forwarded-For is ignored
      and the direct TCP connection address is used instead.
    - This prevents clients from spoofing their IP by injecting arbitrary
      X-Forwarded-For headers, which would otherwise bypass per-IP rate limiting
      and corrupt audit log forensic records.

    Reverse-proxy configuration requirements:
    - Set TRUSTED_PROXY_IPS to the comma-separated list of your reverse-proxy
      IP addresses (e.g. "10.0.0.1,172.16.0.1").
    - Your reverse proxy MUST be configured to set X-Forwarded-For to the
      real client IP and strip any client-supplied X-Forwarded-For headers.
    - If TRUSTED_PROXY_IPS is empty (default), X-Forwarded-For is never trusted.
    """
    from app.core.config import settings

    direct_peer = request.client.host if request.client else None
    trusted_proxies = settings.trusted_proxy_ip_set

    x_forwarded = request.headers.get("x-forwarded-for")
    if x_forwarded and direct_peer and direct_peer in trusted_proxies:
        # Trust the leftmost (original client) IP from the XFF chain
        ip = x_forwarded.split(",")[0].strip()
    else:
        # Ignore XFF — use the direct TCP connection IP
        ip = direct_peer

    user_agent = request.headers.get("user-agent")
    return ip, user_agent


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Owner Login",
    description="Authenticate an owner using their registered mobile phone number and password.",
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ip, ua = _extract_request_metadata(request)
    return authenticate_owner(
        db=db,
        phone_number=payload.phone_number,
        password=payload.password,
        device_info=payload.device_info or ua,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate Refresh Token",
    description="Exchange a valid refresh token for a new access token and rotated refresh token.",
)
def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ip, ua = _extract_request_metadata(request)
    return refresh_token_pair(
        db=db,
        refresh_token=payload.refresh_token,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout Current Session",
    description="Revoke the authenticated owner's current session.",
)
def logout(
    request: Request,
    auth_data: Tuple[Owner, OwnerSession] = Depends(get_current_owner_and_session),
    db: Session = Depends(get_db),
) -> MessageResponse:
    owner, session = auth_data
    ip, ua = _extract_request_metadata(request)
    return logout_session(
        db=db,
        session_id=session.id,
        owner_id=owner.id,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Logout All Sessions",
    description="Revoke all active sessions for the authenticated owner.",
)
def logout_all(
    request: Request,
    owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MessageResponse:
    ip, ua = _extract_request_metadata(request)
    return logout_all_sessions(
        db=db,
        owner_id=owner.id,
        ip_address=ip,
        user_agent=ua,
    )


@router.get(
    "/me",
    response_model=OwnerProfileResponse,
    summary="Get Authenticated Owner Profile",
    description="Retrieve the profile of the currently logged-in gym owner.",
)
def get_profile(
    owner: Owner = Depends(get_current_owner),
) -> OwnerProfileResponse:
    return OwnerProfileResponse.model_validate(owner)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request Password Recovery OTP",
    description="Dispatch a 6-digit numeric recovery code via SMS. Rate-limited with 60-second cooldown.",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> MessageResponse:
    ip, ua = _extract_request_metadata(request)
    return request_password_reset_otp(
        db=db,
        phone_number=payload.phone_number,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/verify-otp",
    response_model=VerifyOTPResponse,
    summary="Verify Password Recovery OTP",
    description="Verify the single-use recovery code. Returns a password reset token on success.",
)
def verify_otp(
    payload: VerifyOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> VerifyOTPResponse:
    ip, ua = _extract_request_metadata(request)
    return verify_password_reset_otp(
        db=db,
        phone_number=payload.phone_number,
        otp=payload.otp,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset Password",
    description="Set a new password using the reset token issued by verify-otp. Revokes all active sessions.",
)
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> MessageResponse:
    ip, ua = _extract_request_metadata(request)
    return reset_owner_password(
        db=db,
        reset_token=payload.reset_token,
        new_password=payload.new_password,
        ip_address=ip,
        user_agent=ua,
    )


@router.get(
    "/sessions",
    response_model=List[SessionResponse],
    summary="List Owner Sessions",
    description="Retrieve all sessions for the authenticated owner, highlighting the current session.",
)
def get_sessions(
    auth_data: Tuple[Owner, OwnerSession] = Depends(get_current_owner_and_session),
    db: Session = Depends(get_db),
) -> List[SessionResponse]:
    owner, session = auth_data
    sessions_data = list_owner_sessions(
        db=db, owner_id=owner.id, current_session_id=session.id
    )
    return [SessionResponse(**s) for s in sessions_data]


@router.delete(
    "/sessions/{session_id}",
    response_model=MessageResponse,
    summary="Revoke Specific Session",
    description="Revoke a specific session belonging to the authenticated owner.",
)
def revoke_specific_session(
    session_id: uuid.UUID,
    request: Request,
    owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MessageResponse:
    ip, ua = _extract_request_metadata(request)
    return logout_session(
        db=db,
        session_id=session_id,
        owner_id=owner.id,
        ip_address=ip,
        user_agent=ua,
    )
