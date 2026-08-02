import logging
import uuid

from sqlalchemy import func, select

from app.database import async_session_factory
from app.models import Notification

logger = logging.getLogger(__name__)

# Fixed subscriber UUIDs matching other services
SUB_LUC = uuid.UUID("00000000-0000-4000-a000-000000000001")
SUB_SOPHIE = uuid.UUID("00000000-0000-4000-a000-000000000002")
SUB_THOMAS = uuid.UUID("00000000-0000-4000-a000-000000000003")
SUB_EMMA = uuid.UUID("00000000-0000-4000-a000-000000000004")
SUB_PIETER = uuid.UUID("00000000-0000-4000-a000-000000000005")

SEED_NOTIFICATIONS: list[dict] = [
    {
        "subscriber_id": SUB_LUC,
        "notification_type": "welcome",
        "channel": "email",
        "subject": "Welcome to TelePortal!",
        "body": (
            "Welcome aboard, Luc! Your account has been created "
            "successfully. Enjoy our services."
        ),
        "status": "sent",
    },
    {
        "subscriber_id": SUB_SOPHIE,
        "notification_type": "welcome",
        "channel": "email",
        "subject": "Welcome to TelePortal!",
        "body": (
            "Welcome aboard, Sophie! Your account has been created "
            "successfully. Enjoy our services."
        ),
        "status": "sent",
    },
    {
        "subscriber_id": SUB_LUC,
        "notification_type": "usage_warning",
        "channel": "sms",
        "subject": "Data Usage Warning",
        "body": (
            "You have used 80% of your data allowance. Consider "
            "upgrading your plan to avoid extra charges."
        ),
        "status": "sent",
    },
    {
        "subscriber_id": SUB_THOMAS,
        "notification_type": "invoice",
        "channel": "email",
        "subject": "New Invoice #INV-2024-0042",
        "body": (
            "Your invoice #INV-2024-0042 for EUR 25.00 has been "
            "issued. Please review and pay before the due date."
        ),
        "status": "sent",
    },
    {
        "subscriber_id": SUB_EMMA,
        "notification_type": "usage_warning",
        "channel": "sms",
        "subject": "Data Usage Warning",
        "body": (
            "You have used 90% of your data allowance. Consider "
            "upgrading your plan to avoid extra charges."
        ),
        "status": "sent",
    },
    {
        "subscriber_id": SUB_PIETER,
        "notification_type": "invoice",
        "channel": "email",
        "subject": "New Invoice #INV-2024-0055",
        "body": (
            "Your invoice #INV-2024-0055 for EUR 40.00 has been "
            "issued. Please review and pay before the due date."
        ),
        "status": "sent",
    },
]


async def seed_notifications() -> None:
    """Insert sample notifications if the table is empty."""
    async with async_session_factory() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(Notification)
            )
        ).scalar()
        if count and count > 0:
            logger.info(
                "Notifications table already has %d rows — skipping seed",
                count,
            )
            return

        for data in SEED_NOTIFICATIONS:
            session.add(Notification(**data))
        await session.commit()
        logger.info(
            "Seeded %d sample notifications", len(SEED_NOTIFICATIONS)
        )
