import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.membership import MembershipRecord
    from app.models.owner import Owner


class MembershipPlan(Base):
    """
    Catalog of membership tiers, durations, and standard fees.
    Modifications never alter previously purchased membership contract snapshots.
    """

    __tablename__ = "membership_plans"
    __table_args__ = (
        CheckConstraint(
            "duration_days > 0", name="ck_plans_duration_positive"
        ),
        CheckConstraint(
            "base_price >= 0.00", name="ck_plans_price_non_negative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_months: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    base_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_personal_training: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_custom_offer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
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
        "MembershipRecord", back_populates="plan"
    )
