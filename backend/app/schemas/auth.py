import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    """Owner login credentials."""

    phone_number: str = Field(..., description="Registered 10-digit mobile number")
    password: str = Field(..., description="Owner password")
    device_info: Optional[str] = Field(
        None, description="Client device description (e.g. Chrome on Windows)"
    )

    @field_validator("phone_number")
    @classmethod
    def clean_phone_number(cls, v: str) -> str:
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not cleaned:
            raise ValueError("Phone number cannot be empty.")
        return cleaned


class TokenResponse(BaseModel):
    """JWT Token pair returned upon successful login or token refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800,
            }
        }
    )


class RefreshTokenRequest(BaseModel):
    """Payload to exchange a refresh token for a new token pair."""

    refresh_token: str = Field(..., description="Valid refresh token")


class ForgotPasswordRequest(BaseModel):
    """Payload to initiate an SMS OTP recovery workflow."""

    phone_number: str = Field(..., description="Registered owner phone number")

    @field_validator("phone_number")
    @classmethod
    def clean_phone_number(cls, v: str) -> str:
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not cleaned:
            raise ValueError("Phone number cannot be empty.")
        return cleaned


class VerifyOTPRequest(BaseModel):
    """Payload to verify the single-use SMS recovery OTP."""

    phone_number: str = Field(..., description="Registered owner phone number")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit numeric OTP")

    @field_validator("phone_number")
    @classmethod
    def clean_phone_number(cls, v: str) -> str:
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not cleaned:
            raise ValueError("Phone number cannot be empty.")
        return cleaned

    @field_validator("otp")
    @classmethod
    def validate_numeric_otp(cls, v: str) -> str:
        v_clean = v.strip()
        if not v_clean.isdigit():
            raise ValueError("OTP must contain only numeric digits.")
        return v_clean


class VerifyOTPResponse(BaseModel):
    """Result of OTP verification containing the short-lived password reset token."""

    reset_token: str
    message: str = "OTP verified successfully. You may now reset your password."


class ResetPasswordRequest(BaseModel):
    """Payload to set a new password following OTP verification."""

    reset_token: str = Field(..., description="Single-use password reset token")
    new_password: str = Field(..., min_length=8, description="New password")
    confirm_password: str = Field(..., min_length=8, description="Password confirmation")

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("New password and confirmation password do not match.")
        return v


class OwnerProfileResponse(BaseModel):
    """Authenticated owner details."""

    id: uuid.UUID
    name: str
    phone_number: str
    email: str
    account_status: str
    last_login_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseModel):
    """Active owner session details."""

    id: uuid.UUID
    device_info: Optional[str] = None
    ip_address: Optional[str] = None
    is_revoked: bool
    expires_at: datetime
    created_at: datetime
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Generic status/message response."""

    message: str
