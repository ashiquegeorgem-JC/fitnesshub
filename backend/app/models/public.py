import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
    from app.models.member import Member
    from app.models.owner import Owner
    from app.models.plan import MembershipPlan


class JoiningApplication(Base):
    """
    Public website member application intake (Developer 1 boundary).
    Approval does not automatically activate paid membership; requires explicit owner actions.
    """

    __tablename__ = "joining_applications"
    __table_args__ = (
        CheckConstraint(
            "age IS NULL OR age > 0",
            name="ck_joining_apps_age",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    applicant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("membership_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    wants_visit_first: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    preferred_visit_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True
    )
    preferred_visit_time_slot: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="submitted", index=True
    )
    handling_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    converted_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        unique=True,
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
    selected_plan: Mapped[Optional["MembershipPlan"]] = relationship(
        "MembershipPlan"
    )
    handling_owner: Mapped[Optional["Owner"]] = relationship("Owner")
    converted_member: Mapped[Optional["Member"]] = relationship(
        "Member", back_populates="joining_application"
    )


class GeneralEnquiry(Base):
    """
    Public website general contact form submissions (Developer 1 boundary).
    """

    __tablename__ = "general_enquiries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    assigned_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="SET NULL"),
        nullable=True,
    )
    response_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    assigned_owner: Mapped[Optional["Owner"]] = relationship("Owner")


class GymVisitRequest(Base):
    """
    Prospective member gym facility inspection tour requests (Developer 1 boundary).
    """

    __tablename__ = "gym_visit_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    visitor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    preferred_date: Mapped[date] = mapped_column(Date, nullable=False)
    preferred_time_slot: Mapped[str] = mapped_column(String(50), nullable=False)
    suggested_alternative_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True
    )
    suggested_alternative_time_slot: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    handling_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="SET NULL"),
        nullable=True,
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
    handling_owner: Mapped[Optional["Owner"]] = relationship("Owner")
