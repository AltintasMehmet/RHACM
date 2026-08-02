import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invoice, InvoiceLineItem

logger = logging.getLogger(__name__)

# Fixed subscriber UUIDs — same ones used by subscriber-service seed data.
# These are deterministic so that seeded invoices reference real subscribers
# once all services are running together.
SUB_LUC = uuid.UUID("00000000-0000-4000-a000-000000000001")
SUB_SOPHIE = uuid.UUID("00000000-0000-4000-a000-000000000002")
SUB_THOMAS = uuid.UUID("00000000-0000-4000-a000-000000000003")
SUB_PIETER = uuid.UUID("00000000-0000-4000-a000-000000000005")

SEED_INVOICES: list[dict] = [
    {
        "subscriber_id": SUB_LUC,
        "billing_period": "2026-06",
        "plan_base_amount_eur": Decimal("25.00"),
        "overage_amount_eur": Decimal("3.50"),
        "tax_amount_eur": Decimal("5.99"),
        "total_amount_eur": Decimal("34.49"),
        "status": "paid",
        "issued_at": datetime(2026, 7, 1, 8, 0, 0, tzinfo=timezone.utc),
        "due_date": date(2026, 7, 31),
        "line_items": [
            {
                "description": "Monthly plan: Telenet ONE 50",
                "quantity": Decimal("1"),
                "unit_price_eur": Decimal("25.0000"),
                "total_eur": Decimal("25.00"),
            },
            {
                "description": "Data overage",
                "quantity": Decimal("70.00"),
                "unit_price_eur": Decimal("0.0500"),
                "total_eur": Decimal("3.50"),
            },
            {
                "description": "VAT (21%)",
                "quantity": Decimal("1"),
                "unit_price_eur": Decimal("5.9900"),
                "total_eur": Decimal("5.99"),
            },
        ],
    },
    {
        "subscriber_id": SUB_SOPHIE,
        "billing_period": "2026-06",
        "plan_base_amount_eur": Decimal("40.00"),
        "overage_amount_eur": Decimal("0.00"),
        "tax_amount_eur": Decimal("8.40"),
        "total_amount_eur": Decimal("48.40"),
        "status": "issued",
        "issued_at": datetime(2026, 7, 1, 8, 0, 0, tzinfo=timezone.utc),
        "due_date": date(2026, 7, 31),
        "line_items": [
            {
                "description": "Monthly plan: Telenet ONE Unlimited",
                "quantity": Decimal("1"),
                "unit_price_eur": Decimal("40.0000"),
                "total_eur": Decimal("40.00"),
            },
            {
                "description": "VAT (21%)",
                "quantity": Decimal("1"),
                "unit_price_eur": Decimal("8.4000"),
                "total_eur": Decimal("8.40"),
            },
        ],
    },
    {
        "subscriber_id": SUB_THOMAS,
        "billing_period": "2026-06",
        "plan_base_amount_eur": Decimal("25.00"),
        "overage_amount_eur": Decimal("12.00"),
        "tax_amount_eur": Decimal("7.77"),
        "total_amount_eur": Decimal("44.77"),
        "status": "overdue",
        "issued_at": datetime(2026, 7, 1, 8, 0, 0, tzinfo=timezone.utc),
        "due_date": date(2026, 7, 31),
        "line_items": [
            {
                "description": "Monthly plan: Telenet ONE 50",
                "quantity": Decimal("1"),
                "unit_price_eur": Decimal("25.0000"),
                "total_eur": Decimal("25.00"),
            },
            {
                "description": "Voice overage",
                "quantity": Decimal("80.00"),
                "unit_price_eur": Decimal("0.1500"),
                "total_eur": Decimal("12.00"),
            },
            {
                "description": "VAT (21%)",
                "quantity": Decimal("1"),
                "unit_price_eur": Decimal("7.7700"),
                "total_eur": Decimal("7.77"),
            },
        ],
    },
    {
        "subscriber_id": SUB_PIETER,
        "billing_period": "2026-06",
        "plan_base_amount_eur": Decimal("55.00"),
        "overage_amount_eur": Decimal("0.00"),
        "tax_amount_eur": Decimal("11.55"),
        "total_amount_eur": Decimal("66.55"),
        "status": "paid",
        "issued_at": datetime(2026, 7, 1, 8, 0, 0, tzinfo=timezone.utc),
        "due_date": date(2026, 7, 31),
        "line_items": [
            {
                "description": "Monthly plan: Telenet Business Pro",
                "quantity": Decimal("1"),
                "unit_price_eur": Decimal("55.0000"),
                "total_eur": Decimal("55.00"),
            },
            {
                "description": "VAT (21%)",
                "quantity": Decimal("1"),
                "unit_price_eur": Decimal("11.5500"),
                "total_eur": Decimal("11.55"),
            },
        ],
    },
]


async def seed_invoices(session: AsyncSession) -> None:
    """Insert sample invoices if the table is empty."""
    result = await session.execute(select(Invoice).limit(1))
    if result.scalar_one_or_none() is not None:
        logger.info("Invoices table already populated — skipping seed")
        return

    for invoice_data in SEED_INVOICES:
        line_items_data = invoice_data.pop("line_items", [])
        invoice = Invoice(**invoice_data)
        for item in line_items_data:
            invoice.line_items.append(InvoiceLineItem(**item))
        session.add(invoice)

    await session.commit()
    logger.info("Seeded %d sample invoices into the database", len(SEED_INVOICES))
