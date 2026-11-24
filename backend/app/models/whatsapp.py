import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
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


class WhatsAppMessageLog(Base):
    """
    Audit ledger tracking outbound WhatsApp message dispatches, WAMID references, and delivery callbacks.
    """

    __tablename__ = "whatsapp_message_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient_phone: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    related_entity_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    related_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    provider_message_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    delivery_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", index=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
    member: Mapped[Optional["Member"]] = relationship(
        "Member", back_populates="whatsapp_logs"
    )
