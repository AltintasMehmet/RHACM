import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SubscriberCreate(BaseModel):
    msisdn: str = Field(..., max_length=15, description="Phone number (E.164)")
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    email: str = Field(..., max_length=255)
    plan_id: uuid.UUID | None = None
    address_city: str | None = Field(None, max_length=100)
    address_postal_code: str | None = Field(None, max_length=10)


class SubscriberUpdate(BaseModel):
    msisdn: str | None = Field(None, max_length=15)
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=255)
    plan_id: uuid.UUID | None = None
    address_city: str | None = Field(None, max_length=100)
    address_postal_code: str | None = Field(None, max_length=10)
    status: str | None = Field(None, max_length=20)


class StatusUpdate(BaseModel):
    status: Literal["active", "suspended", "terminated"]


class SubscriberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    msisdn: str
    first_name: str
    last_name: str
    email: str
    plan_id: uuid.UUID | None = None
    status: str
    activation_date: datetime
    address_city: str | None = None
    address_postal_code: str | None = None
    created_at: datetime
    updated_at: datetime


class SubscriberListResponse(BaseModel):
    count: int
    subscribers: list[SubscriberResponse]
