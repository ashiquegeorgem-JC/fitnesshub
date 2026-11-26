import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

IST = timezone(timedelta(hours=5, minutes=30))
ALLOWED_GENDERS = {"male", "female", "other", "prefer_not_to_say"}
_E164_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone_number(value: str) -> str:
    """
    Normalize phone numbers to canonical E.164 format.

    Supports:
    - 10-digit Indian mobile numbers (e.g. '9876543210' -> '+919876543210')
    - 11-digit Indian numbers with leading 0 (e.g. '09876543210' -> '+919876543210')
    - 12-digit Indian numbers starting with 91 (e.g. '919876543210' -> '+919876543210')
    - International E.164 numbers starting with '+' and 8-15 digits
    """
    if not isinstance(value, str):
        raise ValueError("Phone number must be a string.")

    cleaned = re.sub(r"[\s\-\(\)\.]+", "", value.strip())
    if not cleaned:
        raise ValueError("Phone number cannot be empty.")

    if cleaned.startswith("+"):
        digits = cleaned[1:]
        if not digits.isdigit():
            raise ValueError("Phone number must contain only digits after '+'.")
        if not _E164_REGEX.match(cleaned):
            raise ValueError("Phone number must be a valid E.164 number (8-15 digits).")
        return cleaned

    if not cleaned.isdigit():
        raise ValueError("Phone number must contain only digits.")

    if len(cleaned) == 10:
        return f"+91{cleaned}"
    if len(cleaned) == 11 and cleaned.startswith("0"):
        return f"+91{cleaned[1:]}"
    if len(cleaned) == 12 and cleaned.startswith("91"):
        return f"+{cleaned}"

    raise ValueError(
        "Invalid phone number format. Provide a 10-digit mobile number or E.164 format (+<country><number>)."
    )


def _normalize_gender(value: str) -> str:
    cleaned = value.strip().lower().replace(" ", "_")
    if cleaned not in ALLOWED_GENDERS:
        allowed = ", ".join(sorted(ALLOWED_GENDERS))
        raise ValueError(f"Gender must be one of: {allowed}.")
    return cleaned


def _validate_dob(value: Optional[date]) -> Optional[date]:
    if value is not None:
        today_ist = datetime.now(timezone.utc).astimezone(IST).date()
        if value > today_ist:
            raise ValueError("Date of birth cannot be in the future.")
    return value


class MemberCreate(BaseModel):
    """Request payload for creating a new gym member."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(..., min_length=2, max_length=100)
    phone_number: str = Field(..., min_length=8, max_length=20)
    date_of_birth: Optional[date] = None
    age: Optional[int] = Field(None, gt=0, le=120)
    gender: str = Field(..., min_length=1, max_length=20)
    address: Optional[str] = Field(None, max_length=1000)
    joining_date: Optional[date] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    profile_photo_url: Optional[str] = Field(None, max_length=500)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if len(cleaned) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return cleaned

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_number(v)

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        return normalize_phone_number(v)

    @field_validator("emergency_contact_name", "address", "profile_photo_url")
    @classmethod
    def clean_optional_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned if cleaned else None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        return _normalize_gender(v)

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, v: Optional[date]) -> Optional[date]:
        return _validate_dob(v)


class MemberUpdate(BaseModel):
    """
    Partial update payload for an existing member.
    Protected fields (member_code, is_archived, memberships, payments, etc.) are forbidden.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone_number: Optional[str] = Field(None, min_length=8, max_length=20)
    date_of_birth: Optional[date] = None
    age: Optional[int] = Field(None, gt=0, le=120)
    gender: Optional[str] = Field(None, min_length=1, max_length=20)
    address: Optional[str] = Field(None, max_length=1000)
    joining_date: Optional[date] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    profile_photo_url: Optional[str] = Field(None, max_length=500)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = " ".join(v.strip().split())
        if len(cleaned) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return cleaned

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return normalize_phone_number(v)

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        return normalize_phone_number(v)

    @field_validator("emergency_contact_name", "address", "profile_photo_url")
    @classmethod
    def clean_optional_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned if cleaned else None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _normalize_gender(v)

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, v: Optional[date]) -> Optional[date]:
        return _validate_dob(v)


class MemberArchiveRequest(BaseModel):
    """Optional payload when archiving a member."""

    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(None, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned if cleaned else None


class MemberResponse(BaseModel):
    """Public member profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_code: str
    full_name: str
    phone_number: str
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    gender: str
    address: Optional[str] = None
    joining_date: date
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    profile_photo_url: Optional[str] = None
    is_archived: bool
    archived_at: Optional[datetime] = None
    archive_reason: Optional[str] = None
    created_by_owner_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class MemberListResponse(BaseModel):
    """Paginated member directory response."""

    items: List[MemberResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class MemberMembershipHistoryItem(BaseModel):
    """Single historical membership record for a member."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    plan_snapshot_name: str
    plan_snapshot_duration_days: int
    plan_snapshot_base_price: Decimal
    plan_snapshot_is_pt: bool
    discount_amount: Decimal
    total_fee: Decimal
    start_date: date
    expiry_date: date
    system_status: str
    override_status: Optional[str] = None
    is_manual_override: bool
    override_reason: Optional[str] = None
    membership_type: str
    previous_membership_id: Optional[uuid.UUID] = None
    created_at: datetime


class MemberMembershipHistoryResponse(BaseModel):
    """Paginated membership history for a member."""

    member_id: uuid.UUID
    member_code: str
    items: List[MemberMembershipHistoryItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class MemberPaymentHistoryItem(BaseModel):
    """Single payment record for a member, including processed refund totals."""

    id: uuid.UUID
    payment_number: str
    membership_record_id: Optional[uuid.UUID] = None
    amount: Decimal
    payment_type: str
    payment_method: str
    transaction_reference: Optional[str] = None
    payment_date: date
    status: str
    notes: Optional[str] = None
    refunded_amount: Decimal = Decimal("0.00")
    has_refunds: bool = False
    created_at: datetime


class MemberPaymentHistoryResponse(BaseModel):
    """Paginated payment history for a member."""

    member_id: uuid.UUID
    member_code: str
    items: List[MemberPaymentHistoryItem]
    total: int
    page: int
    page_size: int
    total_pages: int


MemberSortField = Literal["created_at", "joining_date", "full_name", "member_code"]
SortOrder = Literal["asc", "desc"]
