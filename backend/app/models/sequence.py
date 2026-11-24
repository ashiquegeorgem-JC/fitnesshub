from typing import Optional
from sqlalchemy import BigInteger, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

# Standalone PostgreSQL sequences for atomic, concurrency-safe, gap-resistant numbering
member_code_seq = Sequence("member_code_seq", start=1)
invoice_number_seq = Sequence("invoice_number_seq", start=1)
payment_number_seq = Sequence("payment_number_seq", start=1)
refund_number_seq = Sequence("refund_number_seq", start=1)


class SystemSequence(Base):
    """
    Registry table documenting and tracking concurrency-safe sequential code generators.
    """

    __tablename__ = "system_sequences"

    sequence_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    padding_digits: Mapped[int] = mapped_column(Integer, nullable=False)
    current_value: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
