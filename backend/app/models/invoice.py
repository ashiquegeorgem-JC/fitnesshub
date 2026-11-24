import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.member import Member
    from app.models.membership import MembershipRecord
    from app.models.owner import Owner
    from app.models.payment import Payment


class Invoice(Base):
    """
    Formal financial receipt issued to members.
    Every confirmed payment generates an immutable receipt. Subsequent installments
    generate new receipts; previously issued receipts are never overwritten or altered.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "contract_total_fee >= 0.00 AND payment_amount > 0.00 AND remaining_balance_after_payment >= 0.00",
            name="ck_invoices_balances_valid",
        ),
        Index("idx_invoices_payment_id", "payment_id"),
        Index("idx_invoices_contract_id", "membership_record_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_number: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )
    membership_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("membership_records.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    contract_total_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    payment_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    cumulative_paid_to_date: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    remaining_balance_after_payment: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    pdf_storage_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    pdf_file_name: Mapped[Optional[str]] = mapped_column(
        String(150), nullable=True
    )
    pdf_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_via_whatsapp: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    payment: Mapped["Payment"] = relationship("Payment", back_populates="invoice")
    membership_record: Mapped["MembershipRecord"] = relationship(
        "MembershipRecord", back_populates="invoices"
    )
    member: Mapped["Member"] = relationship("Member", back_populates="invoices")
    created_by_owner: Mapped["Owner"] = relationship("Owner")
