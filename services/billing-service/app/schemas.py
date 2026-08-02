from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ---------- Line Items ----------


class InvoiceLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    quantity: Decimal
    unit_price_eur: Decimal
    total_eur: Decimal


# ---------- Invoice ----------


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscriber_id: UUID
    billing_period: str
    plan_base_amount_eur: Decimal
    overage_amount_eur: Decimal
    tax_amount_eur: Decimal
    total_amount_eur: Decimal
    status: str
    issued_at: datetime | None = None
    due_date: date | None = None
    created_at: datetime
    line_items: list[InvoiceLineItemResponse] = []


class InvoiceListResponse(BaseModel):
    count: int
    invoices: list[InvoiceResponse]


class InvoiceStatusUpdate(BaseModel):
    status: Literal["draft", "issued", "paid", "overdue"]


# ---------- Revenue ----------


class RevenueSummary(BaseModel):
    billing_period: str
    total_revenue_eur: Decimal
    invoice_count: int
    paid_count: int
    outstanding_count: int
