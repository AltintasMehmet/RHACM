import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UsageCreate(BaseModel):
    subscriber_id: uuid.UUID
    usage_type: Literal["data", "voice", "sms"]
    quantity: Decimal = Field(..., gt=0, decimal_places=2)


class UsageBatchCreate(BaseModel):
    records: list[UsageCreate]


class UsageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscriber_id: uuid.UUID
    usage_type: str
    quantity: Decimal
    recorded_at: datetime
    billing_period: str


class UsageSummary(BaseModel):
    subscriber_id: uuid.UUID
    billing_period: str
    data_used_mb: Decimal = Decimal("0")
    voice_used_minutes: Decimal = Decimal("0")
    sms_used_count: Decimal = Decimal("0")


class CurrentUsageResponse(BaseModel):
    subscriber_id: uuid.UUID
    billing_period: str
    data_used_mb: Decimal = Decimal("0")
    voice_used_minutes: Decimal = Decimal("0")
    sms_used_count: Decimal = Decimal("0")
    source: Literal["redis", "database"]
