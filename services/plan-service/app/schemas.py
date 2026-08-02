from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- PlanFeature ----------


class PlanFeatureCreate(BaseModel):
    feature_name: str = Field(..., max_length=100)
    feature_value: str = Field(..., max_length=255)


class PlanFeatureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feature_name: str
    feature_value: str


# ---------- Plan ----------


class PlanCreate(BaseModel):
    name: str = Field(..., max_length=100)
    plan_type: str = Field(..., max_length=20)
    data_limit_mb: int | None = None
    voice_minutes: int | None = None
    sms_limit: int | None = None
    monthly_price_eur: Decimal = Field(..., max_digits=10, decimal_places=2)
    speed_mbps: int | None = None
    is_active: bool = True
    features: list[PlanFeatureCreate] | None = None


class PlanUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    plan_type: str | None = Field(None, max_length=20)
    data_limit_mb: int | None = None
    voice_minutes: int | None = None
    sms_limit: int | None = None
    monthly_price_eur: Decimal | None = Field(
        None, max_digits=10, decimal_places=2
    )
    speed_mbps: int | None = None
    is_active: bool | None = None
    features: list[PlanFeatureCreate] | None = None


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    plan_type: str
    data_limit_mb: int | None = None
    voice_minutes: int | None = None
    sms_limit: int | None = None
    monthly_price_eur: Decimal
    speed_mbps: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    features: list[PlanFeatureResponse] = []


class PlanListResponse(BaseModel):
    count: int
    plans: list[PlanResponse]
