import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.membership import MembershipDueSchedule, MembershipRecord
    from app.models.owner import Owner
    from app.models.payment import Payment, PaymentRefund
    from app.models.public import JoiningApplication
    from app.models.whatsapp import WhatsAppMessageLog


class Member(Base):
    """
    Core gym member directory.
    Maintains full member lifecycle, emergency contacts, and soft-archive history.
    """

    __tablename__ = "members"
    __table_args__ = (
        CheckConstraint(
            "age IS NULL OR age > 0",
            name="ck_members_age_range",
        ),
        Index(
            "idx_uq_members_active_phone",
            "phone_number",
            unique=True,
            postgresql_where=text("is_archived = false"),
            sqlite_where=text("is_archived = 0"),
        ),
        Index("idx_members_search_name", "full_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_code: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    joining_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    profile_photo_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archive_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="SET NULL"),
        nullable=True,
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
    created_by_owner: Mapped[Optional["Owner"]] = relationship("Owner")
    membership_records: Mapped[List["MembershipRecord"]] = relationship(
        "MembershipRecord", back_populates="member"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", back_populates="member"
    )
    refunds: Mapped[List["PaymentRefund"]] = relationship(
        "PaymentRefund", back_populates="member"
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice", back_populates="member"
    )
    due_schedules: Mapped[List["MembershipDueSchedule"]] = relationship(
        "MembershipDueSchedule", back_populates="member"
    )
    joining_application: Mapped[Optional["JoiningApplication"]] = relationship(
        "JoiningApplication",
        back_populates="converted_member",
        uselist=False,
    )
    whatsapp_logs: Mapped[List["WhatsAppMessageLog"]] = relationship(
        "WhatsAppMessageLog", back_populates="member"
    )
