import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageRecord

logger = logging.getLogger(__name__)

# Fixed subscriber IDs — these match across services for the demo
SUBSCRIBER_IDS = [
    uuid.UUID("a1b2c3d4-0001-4000-8000-000000000001"),  # Luc Janssens
    uuid.UUID("a1b2c3d4-0002-4000-8000-000000000002"),  # Sophie Peeters
    uuid.UUID("a1b2c3d4-0003-4000-8000-000000000003"),  # Thomas Maes
    uuid.UUID("a1b2c3d4-0004-4000-8000-000000000004"),  # Emma Claes
]


def _current_billing_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _build_seed_records() -> list[dict]:
    """Generate ~20 sample usage records for the current billing period."""
    bp = _current_billing_period()
    luc, sophie, thomas, emma = SUBSCRIBER_IDS

    return [
        # Luc — moderate data user
        {"subscriber_id": luc, "usage_type": "data", "quantity": Decimal("512.50"), "billing_period": bp},
        {"subscriber_id": luc, "usage_type": "data", "quantity": Decimal("1024.00"), "billing_period": bp},
        {"subscriber_id": luc, "usage_type": "voice", "quantity": Decimal("45.00"), "billing_period": bp},
        {"subscriber_id": luc, "usage_type": "sms", "quantity": Decimal("12.00"), "billing_period": bp},
        {"subscriber_id": luc, "usage_type": "data", "quantity": Decimal("256.75"), "billing_period": bp},
        # Sophie — heavy data user
        {"subscriber_id": sophie, "usage_type": "data", "quantity": Decimal("2048.00"), "billing_period": bp},
        {"subscriber_id": sophie, "usage_type": "data", "quantity": Decimal("3072.00"), "billing_period": bp},
        {"subscriber_id": sophie, "usage_type": "data", "quantity": Decimal("1500.00"), "billing_period": bp},
        {"subscriber_id": sophie, "usage_type": "voice", "quantity": Decimal("120.50"), "billing_period": bp},
        {"subscriber_id": sophie, "usage_type": "sms", "quantity": Decimal("85.00"), "billing_period": bp},
        # Thomas — voice-heavy user
        {"subscriber_id": thomas, "usage_type": "data", "quantity": Decimal("350.00"), "billing_period": bp},
        {"subscriber_id": thomas, "usage_type": "voice", "quantity": Decimal("180.00"), "billing_period": bp},
        {"subscriber_id": thomas, "usage_type": "voice", "quantity": Decimal("95.50"), "billing_period": bp},
        {"subscriber_id": thomas, "usage_type": "voice", "quantity": Decimal("60.00"), "billing_period": bp},
        {"subscriber_id": thomas, "usage_type": "sms", "quantity": Decimal("200.00"), "billing_period": bp},
        {"subscriber_id": thomas, "usage_type": "sms", "quantity": Decimal("150.00"), "billing_period": bp},
        # Emma — low usage (suspended subscriber)
        {"subscriber_id": emma, "usage_type": "data", "quantity": Decimal("100.00"), "billing_period": bp},
        {"subscriber_id": emma, "usage_type": "voice", "quantity": Decimal("10.00"), "billing_period": bp},
        {"subscriber_id": emma, "usage_type": "sms", "quantity": Decimal("5.00"), "billing_period": bp},
        {"subscriber_id": emma, "usage_type": "data", "quantity": Decimal("50.25"), "billing_period": bp},
    ]


async def seed_usage(session: AsyncSession) -> None:
    """Insert sample usage records if the table is empty."""
    count = (
        await session.execute(select(func.count()).select_from(UsageRecord))
    ).scalar()
    if count and count > 0:
        logger.info(
            "Usage table already has %d rows — skipping seed", count
        )
        return

    records = _build_seed_records()
    for data in records:
        session.add(UsageRecord(**data))

    await session.commit()
    logger.info("Seeded %d sample usage records", len(records))
