import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.owner import Owner


class GalleryImage(Base):
    """
    Metadata, CDN paths, and ordering for gym facility photos rendered on Developer 1's website.
    """

    __tablename__ = "gallery_images"
    __table_args__ = (
        CheckConstraint(
            "file_size_bytes > 0", name="ck_gallery_file_size_positive"
        ),
        Index(
            "idx_uq_gallery_single_cover",
            "is_cover_image",
            unique=True,
            postgresql_where=text("is_cover_image = true AND is_active = true"),
            sqlite_where=text("is_cover_image = 1 AND is_active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(150), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, index=True
    )
    is_cover_image: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    uploaded_by_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
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
    uploaded_by_owner: Mapped[Optional["Owner"]] = relationship("Owner")
