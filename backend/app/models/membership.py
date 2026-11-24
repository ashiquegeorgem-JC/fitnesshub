import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.member import Member
    from app.models.owner import Owner
    from app.models.payment import Payment
    from app.models.plan import MembershipPlan


class MembershipRecord(Base):
    """
    Historical contract representing a gym membership term.
    Stores immutable plan snapshots at the moment of purchase and requires explicit owner activation.
    """

    __tablename__ = "membership_records"
    __table_args__ = (
        CheckConstraint(
            "expiry_date >= start_date", name="ck_membership_dates_valid"
        ),
        CheckConstraint(
            "total_fee >= 0.00", name="ck_membership_fee_positive"
        ),
        CheckConstraint(
            "discount_amount >= 0.00",
            name="ck_membership_discount_non_negative",
        ),
        CheckConstraint(
            "plan_snapshot_duration_days > 0",
            name="ck_membership_duration_positive",
        ),
        CheckConstraint(
            "plan_snapshot_base_price >= 0.00",
            name="ck_membership_base_price_non_negative",
        ),
        Index(
            "idx_membership_member_status",
            "member_id",
            "system_status",
            "is_manual_override",
        ),
        Index(
            "idx_membership_expiry_date",
            "expiry_date",
            "system_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("membership_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_snapshot_name: Mapped[str] = mapped_column(String(100), nullable=False)
    plan_snapshot_duration_days: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    plan_snapshot_base_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    plan_snapshot_is_pt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    total_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Status tracking (neither full nor partial payment auto-activates; explicit owner activation required)
    system_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending_activation", index=True
    )
    override_status: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )
    is_manual_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    override_by_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=True,
    )
    overridden_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Explicit owner activation audit
    activated_by_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=True,
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    membership_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="new"
    )
    previous_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("membership_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=False,
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
    member: Mapped["Member"] = relationship(
        "Member", back_populates="membership_records"
    )
    plan: Mapped["MembershipPlan"] = relationship(
        "MembershipPlan", back_populates="membership_records"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", back_populates="membership_record"
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice", back_populates="membership_record"
    )
    due_schedules: Mapped[List["MembershipDueSchedule"]] = relationship(
        "MembershipDueSchedule",
        back_populates="membership_record",
        cascade="all, delete-orphan",
    )
    created_by_owner: Mapped["Owner"] = relationship(
        "Owner", foreign_keys=[created_by_owner_id]
    )
    activated_by_owner: Mapped[Optional["Owner"]] = relationship(
        "Owner", foreign_keys=[activated_by_owner_id]
    )
    override_by_owner: Mapped[Optional["Owner"]] = relationship(
        "Owner", foreign_keys=[override_by_owner_id]
    )
    previous_membership: Mapped[Optional["MembershipRecord"]] = relationship(
        "MembershipRecord", remote_side=[id]
    )


class MembershipDueSchedule(Base):
    """
    Multi-installment balance scheduling.
    Supports single-balance dues and multi-installment schedules without database restructuring.
    """

    __tablename__ = "membership_due_schedules"
    __table_args__ = (
        UniqueConstraint(
            "membership_record_id",
            "installment_number",
            name="uq_due_schedules_installment",
        ),
        CheckConstraint(
            "installment_number > 0",
            name="ck_due_schedule_installment_positive",
        ),
        CheckConstraint(
            "due_amount > 0.00 AND paid_amount >= 0.00",
            name="ck_due_schedule_amount_positive",
        ),
        Index("idx_dues_schedule_overdue", "due_date", "is_waived"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    membership_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("membership_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    installment_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    due_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    is_waived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    waiver_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    waived_by_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=True,
    )
    waived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assigned_by_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=False,
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
    membership_record: Mapped["MembershipRecord"] = relationship(
        "MembershipRecord", back_populates="due_schedules"
    )
    member: Mapped["Member"] = relationship(
        "Member", back_populates="due_schedules"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", back_populates="due_schedule_installment"
    )
    assigned_by_owner: Mapped["Owner"] = relationship(
        "Owner", foreign_keys=[assigned_by_owner_id]
    )
    waived_by_owner: Mapped[Optional["Owner"]] = relationship(
        "Owner", foreign_keys=[waived_by_owner_id]
    )
