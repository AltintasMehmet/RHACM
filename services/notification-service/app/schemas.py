import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreate(BaseModel):
    subscriber_id: uuid.UUID
    notification_type: Literal[
        "welcome", "usage_warning", "invoice", "outage", "status_change"
    ]
    channel: Literal["email", "sms", "push"] = "email"
    subject: str = Field(..., max_length=255)
    body: str


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscriber_id: uuid.UUID
    notification_type: str
    channel: str
    subject: str
    body: str
    status: str
    sent_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    count: int
    notifications: list[NotificationResponse]
