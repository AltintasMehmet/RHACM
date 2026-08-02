import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Plan, PlanFeature

logger = logging.getLogger(__name__)

SEED_PLANS: list[dict] = [
    {
        "name": "Telenet ONE 50",
        "plan_type": "mobile",
        "data_limit_mb": 5120,
        "voice_minutes": 120,
        "sms_limit": 500,
        "monthly_price_eur": Decimal("25.00"),
        "features": [],
    },
    {
        "name": "Telenet ONE Unlimited",
        "plan_type": "mobile",
        "data_limit_mb": None,
        "voice_minutes": None,
        "sms_limit": None,
        "monthly_price_eur": Decimal("40.00"),
        "features": [
            {"feature_name": "5G Access", "feature_value": "included"},
            {"feature_name": "EU Roaming Included", "feature_value": "included"},
        ],
    },
    {
        "name": "Telenet Internet 200",
        "plan_type": "fixed",
        "speed_mbps": 200,
        "monthly_price_eur": Decimal("45.00"),
        "features": [],
    },
    {
        "name": "Telenet WIGO",
        "plan_type": "bundle",
        "data_limit_mb": 10240,
        "voice_minutes": None,
        "speed_mbps": 100,
        "monthly_price_eur": Decimal("70.00"),
        "features": [
            {"feature_name": "TV Included", "feature_value": "included"},
            {"feature_name": "5G Access", "feature_value": "included"},
            {"feature_name": "EU Roaming Included", "feature_value": "included"},
        ],
    },
    {
        "name": "Telenet Business Pro",
        "plan_type": "mobile",
        "data_limit_mb": 20480,
        "voice_minutes": None,
        "sms_limit": None,
        "monthly_price_eur": Decimal("55.00"),
        "features": [
            {"feature_name": "Priority Support", "feature_value": "included"},
            {"feature_name": "5G Access", "feature_value": "included"},
            {"feature_name": "VPN Access", "feature_value": "included"},
        ],
    },
]


async def seed_plans(session: AsyncSession) -> None:
    result = await session.execute(select(Plan).limit(1))
    if result.scalar_one_or_none() is not None:
        logger.info("Plans table already populated — skipping seed")
        return

    for plan_data in SEED_PLANS:
        features_data = plan_data.pop("features", [])
        plan = Plan(**plan_data)
        for feat in features_data:
            plan.features.append(PlanFeature(**feat))
        session.add(plan)

    await session.commit()
    logger.info("Seeded %d plans into the database", len(SEED_PLANS))
