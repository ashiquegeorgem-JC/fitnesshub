import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.audit import AuditLog
    from app.models.invoice import Invoice
    from app.models.membership import MembershipRecord
    from app.models.notification import Notification
    from app.models.payment import Payment, PaymentRefund


class Owner(Base):
    """
    Administrator accounts for gym owners.
    Both co-owners possess identical root-level system permissions.
    """

    __tablename__ = "owners"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    account_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    notification_preferences: Mapped[
        Optional["OwnerNotificationPreference"]
    ] = relationship(
        "OwnerNotificationPreference",
        back_populates="owner",
        uselist=False,
        cascade="all, delete-orphan",
    )
    device_push_subscriptions: Mapped[
        List["OwnerDevicePushSubscription"]
    ] = relationship(
        "OwnerDevicePushSubscription",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    password_reset_otps: Mapped[
        List["OwnerPasswordResetOTP"]
    ] = relationship(
        "OwnerPasswordResetOTP",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[List["OwnerSession"]] = relationship(
        "OwnerSession",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        back_populates="recipient_owner",
        cascade="all, delete-orphan",
    )


class OwnerNotificationPreference(Base):
    """
    Granular push, WhatsApp, and in-app notification topic subscriptions per owner.
    """

    __tablename__ = "owner_notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    notify_new_application: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notify_new_enquiry: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notify_new_visit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notify_payment_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notify_upcoming_expiry: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notify_overdue_dues: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notify_daily_report_9am: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    channel_in_app: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    channel_whatsapp: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    channel_push: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship
    owner: Mapped["Owner"] = relationship(
        "Owner", back_populates="notification_preferences"
    )


class OwnerDevicePushSubscription(Base):
    """
    Manages multiple active push device endpoints (smartphones, tablets, PCs) per owner.
    """

    __tablename__ = "owner_device_push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auth_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    device_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationship
    owner: Mapped["Owner"] = relationship(
        "Owner", back_populates="device_push_subscriptions"
    )


class OwnerPasswordResetOTP(Base):
    """
    Server-secret-keyed HMAC hashed, single-use recovery OTP tokens.
    """

    __tablename__ = "owner_password_reset_otps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    otp_hmac: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cooldown_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationship
    owner: Mapped["Owner"] = relationship(
        "Owner", back_populates="password_reset_otps"
    )


class OwnerSession(Base):
    """
    Active owner authentication sessions and refresh tokens (stored as SHA-256 hashes).
    """

    __tablename__ = "owner_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    device_info: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationship
    owner: Mapped["Owner"] = relationship(
        "Owner", back_populates="sessions"
    )
