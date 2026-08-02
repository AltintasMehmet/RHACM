import logging

from sqlalchemy import func, select

from app.database import async_session_factory
from app.models import Subscriber

logger = logging.getLogger(__name__)

SEED_SUBSCRIBERS = [
    {
        "msisdn": "+32471234501",
        "first_name": "Luc",
        "last_name": "Janssens",
        "email": "luc.janssens@example.be",
        "status": "active",
        "address_city": "Brussels",
        "address_postal_code": "1000",
    },
    {
        "msisdn": "+32479876502",
        "first_name": "Sophie",
        "last_name": "Peeters",
        "email": "sophie.peeters@example.be",
        "status": "active",
        "address_city": "Antwerp",
        "address_postal_code": "2000",
    },
    {
        "msisdn": "+32468112203",
        "first_name": "Thomas",
        "last_name": "Maes",
        "email": "thomas.maes@example.be",
        "status": "active",
        "address_city": "Ghent",
        "address_postal_code": "9000",
    },
    {
        "msisdn": "+32475334404",
        "first_name": "Emma",
        "last_name": "Claes",
        "email": "emma.claes@example.be",
        "status": "suspended",
        "address_city": "Mechelen",
        "address_postal_code": "2800",
    },
    {
        "msisdn": "+32472556605",
        "first_name": "Pieter",
        "last_name": "Willems",
        "email": "pieter.willems@example.be",
        "status": "active",
        "address_city": "Leuven",
        "address_postal_code": "3000",
    },
]


async def seed_subscribers() -> None:
    """Insert sample subscribers if the table is empty."""
    async with async_session_factory() as session:
        count = (
            await session.execute(select(func.count()).select_from(Subscriber))
        ).scalar()
        if count and count > 0:
            logger.info(
                "Subscribers table already has %d rows — skipping seed", count
            )
            return

        for data in SEED_SUBSCRIBERS:
            session.add(Subscriber(**data))
        await session.commit()
        logger.info("Seeded %d sample subscribers", len(SEED_SUBSCRIBERS))
