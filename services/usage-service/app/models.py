import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    usage_type: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # data / voice / sms
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )  # MB for data, minutes for voice, count for sms
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    billing_period: Mapped[str] = mapped_column(
        String(7), nullable=False
    )  # e.g. "2026-07"

    __table_args__ = (
        Index(
            "ix_usage_subscriber_period",
            "subscriber_id",
            "billing_period",
        ),
    )
