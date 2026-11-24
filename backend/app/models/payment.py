import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.member import Member
    from app.models.membership import MembershipDueSchedule, MembershipRecord
    from app.models.owner import Owner


class Payment(Base):
    """
    Immutable financial transaction ledger.
    Every confirmed payment has its own permanent, non-overwritten record and triggers a receipt.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0.00", name="ck_payments_amount_positive"),
        Index("idx_payments_membership_id", "membership_record_id", "status"),
        Index("idx_payments_confirmation_date", "payment_date", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_number: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    membership_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("membership_records.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    due_schedule_installment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("membership_due_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="full"
    )
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    transaction_reference: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    payment_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date(), index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    confirmed_by_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=True,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128), unique=True, nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    member: Mapped["Member"] = relationship("Member", back_populates="payments")
    membership_record: Mapped[Optional["MembershipRecord"]] = relationship(
        "MembershipRecord", back_populates="payments"
    )
    due_schedule_installment: Mapped[
        Optional["MembershipDueSchedule"]
    ] = relationship("MembershipDueSchedule", back_populates="payments")
    confirmed_by_owner: Mapped[Optional["Owner"]] = relationship("Owner")
    invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice", back_populates="payment", uselist=False
    )
    refunds: Mapped[List["PaymentRefund"]] = relationship(
        "PaymentRefund", back_populates="original_payment"
    )


class PaymentRefund(Base):
    """
    Explicit correction and refund transaction records.
    Confirmed payments are never modified in-place; adjustments occur via this ledger.
    """

    __tablename__ = "payment_refunds"
    __table_args__ = (
        CheckConstraint("amount > 0.00", name="ck_refunds_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    refund_number: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    original_payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    refund_reason: Mapped[str] = mapped_column(Text, nullable=False)
    refund_method: Mapped[str] = mapped_column(String(30), nullable=False)
    transaction_reference: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="processed"
    )
    processed_by_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    original_payment: Mapped["Payment"] = relationship(
        "Payment", back_populates="refunds"
    )
    member: Mapped["Member"] = relationship("Member", back_populates="refunds")
    processed_by_owner: Mapped["Owner"] = relationship("Owner")
