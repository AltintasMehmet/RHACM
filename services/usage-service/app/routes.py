import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.events import publish_event, rabbitmq_healthy
from app.models import UsageRecord
from app.redis_client import get_redis
from app.schemas import (
    CurrentUsageResponse,
    UsageBatchCreate,
    UsageCreate,
    UsageResponse,
    UsageSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usage", tags=["usage"])

# ---------- Demo plan limits (hardcoded for demo) ----------
PLAN_LIMITS = {
    "data": Decimal("10000"),   # 10 000 MB
    "voice": Decimal("500"),    # 500 minutes
    "sms": Decimal("1000"),     # 1 000 messages
}
THRESHOLDS = [Decimal("0.50"), Decimal("0.80"), Decimal("1.00")]


def _current_billing_period() -> str:
    """Return the current billing period as 'YYYY-MM'."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _redis_key(subscriber_id: UUID, billing_period: str, usage_type: str) -> str:
    return f"usage:{subscriber_id}:{billing_period}:{usage_type}"


async def _increment_redis_counter(
    subscriber_id: UUID,
    billing_period: str,
    usage_type: str,
    quantity: Decimal,
) -> Decimal | None:
    """Increment a Redis counter and return the new total, or None if Redis unavailable."""
    r = await get_redis()
    if r is None:
        return None
    try:
        key = await _redis_key(subscriber_id, billing_period, usage_type)
        # Use INCRBYFLOAT for decimal quantities
        new_total = await r.incrbyfloat(key, float(quantity))
        # Set expiry to 45 days so keys auto-clean after the billing period
        await r.expire(key, 45 * 24 * 3600)
        return Decimal(str(new_total))
    except Exception:
        logger.warning(
            "Redis increment failed for %s — skipping counter update",
            subscriber_id,
            exc_info=True,
        )
        return None


async def _check_thresholds(
    subscriber_id: UUID,
    billing_period: str,
    usage_type: str,
    new_total: Decimal,
) -> None:
    """Check if the new total crosses any threshold and publish an event."""
    limit = PLAN_LIMITS.get(usage_type)
    if limit is None or limit == 0:
        return

    ratio = new_total / limit
    for threshold in THRESHOLDS:
        if ratio >= threshold:
            # Check if we already published this threshold (use Redis flag)
            r = await get_redis()
            flag_key = f"threshold:{subscriber_id}:{billing_period}:{usage_type}:{int(threshold * 100)}"
            if r is not None:
                try:
                    already_sent = await r.get(flag_key)
                    if already_sent:
                        continue
                    await r.set(flag_key, "1", ex=45 * 24 * 3600)
                except Exception:
                    logger.warning("Redis threshold flag check failed", exc_info=True)

            pct = int(threshold * 100)
            logger.info(
                "Subscriber %s reached %d%% of %s limit (%s / %s)",
                subscriber_id, pct, usage_type, new_total, limit,
            )
            await publish_event(
                "usage.threshold_reached",
                {
                    "subscriber_id": str(subscriber_id),
                    "billing_period": billing_period,
                    "usage_type": usage_type,
                    "threshold_pct": pct,
                    "current_usage": str(new_total),
                    "limit": str(limit),
                },
            )


async def _get_db_summary(
    db: AsyncSession,
    subscriber_id: UUID,
    billing_period: str,
) -> dict[str, Decimal]:
    """Aggregate usage from the database for a subscriber/period."""
    result = await db.execute(
        select(
            UsageRecord.usage_type,
            func.coalesce(func.sum(UsageRecord.quantity), 0),
        )
        .where(UsageRecord.subscriber_id == subscriber_id)
        .where(UsageRecord.billing_period == billing_period)
        .group_by(UsageRecord.usage_type)
    )
    totals: dict[str, Decimal] = {"data": Decimal("0"), "voice": Decimal("0"), "sms": Decimal("0")}
    for usage_type, total in result.all():
        totals[usage_type] = Decimal(str(total))
    return totals


# ---------- Endpoints ----------


@router.post("/", response_model=UsageResponse, status_code=status.HTTP_201_CREATED)
async def record_usage(
    payload: UsageCreate,
    db: AsyncSession = Depends(get_db),
) -> UsageRecord:
    """Record a single usage event."""
    billing_period = _current_billing_period()

    record = UsageRecord(
        subscriber_id=payload.subscriber_id,
        usage_type=payload.usage_type,
        quantity=payload.quantity,
        billing_period=billing_period,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)

    # Update Redis counter and check thresholds
    new_total = await _increment_redis_counter(
        payload.subscriber_id, billing_period, payload.usage_type, payload.quantity
    )
    if new_total is not None:
        await _check_thresholds(
            payload.subscriber_id, billing_period, payload.usage_type, new_total
        )

    logger.info(
        "Recorded %s usage: %s %s for subscriber %s",
        payload.usage_type, payload.quantity,
        "MB" if payload.usage_type == "data" else payload.usage_type,
        payload.subscriber_id,
    )
    return record


@router.post("/batch", response_model=list[UsageResponse], status_code=status.HTTP_201_CREATED)
async def record_usage_batch(
    payload: UsageBatchCreate,
    db: AsyncSession = Depends(get_db),
) -> list[UsageRecord]:
    """Record a batch of usage events."""
    billing_period = _current_billing_period()
    records: list[UsageRecord] = []

    for item in payload.records:
        record = UsageRecord(
            subscriber_id=item.subscriber_id,
            usage_type=item.usage_type,
            quantity=item.quantity,
            billing_period=billing_period,
        )
        db.add(record)
        records.append(record)

    await db.flush()
    for record in records:
        await db.refresh(record)

    # Update Redis counters and check thresholds for each record
    for item in payload.records:
        new_total = await _increment_redis_counter(
            item.subscriber_id, billing_period, item.usage_type, item.quantity
        )
        if new_total is not None:
            await _check_thresholds(
                item.subscriber_id, billing_period, item.usage_type, new_total
            )

    logger.info("Recorded batch of %d usage events", len(records))
    return records


@router.get("/{subscriber_id}/current", response_model=CurrentUsageResponse)
async def get_current_usage(
    subscriber_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current billing period usage. Tries Redis first (fast path),
    falls back to DB aggregate."""
    billing_period = _current_billing_period()
    source = "redis"

    r = await get_redis()
    if r is not None:
        try:
            data_key = await _redis_key(subscriber_id, billing_period, "data")
            voice_key = await _redis_key(subscriber_id, billing_period, "voice")
            sms_key = await _redis_key(subscriber_id, billing_period, "sms")

            data_val = await r.get(data_key)
            voice_val = await r.get(voice_key)
            sms_val = await r.get(sms_key)

            # If all keys are None, the data may not be in Redis yet — fall back to DB
            if data_val is None and voice_val is None and sms_val is None:
                raise ValueError("No Redis data — fall back to DB")

            return {
                "subscriber_id": subscriber_id,
                "billing_period": billing_period,
                "data_used_mb": Decimal(data_val) if data_val else Decimal("0"),
                "voice_used_minutes": Decimal(voice_val) if voice_val else Decimal("0"),
                "sms_used_count": Decimal(sms_val) if sms_val else Decimal("0"),
                "source": source,
            }
        except Exception:
            logger.debug(
                "Redis lookup failed for %s — falling back to DB",
                subscriber_id,
                exc_info=True,
            )

    # DB fallback
    totals = await _get_db_summary(db, subscriber_id, billing_period)
    return {
        "subscriber_id": subscriber_id,
        "billing_period": billing_period,
        "data_used_mb": totals["data"],
        "voice_used_minutes": totals["voice"],
        "sms_used_count": totals["sms"],
        "source": "database",
    }


@router.get("/{subscriber_id}/history", response_model=list[UsageResponse])
async def get_usage_history(
    subscriber_id: UUID,
    billing_period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[UsageRecord]:
    """Query usage history from the database, optionally filtered by billing period."""
    query = select(UsageRecord).where(UsageRecord.subscriber_id == subscriber_id)

    if billing_period is not None:
        query = query.where(UsageRecord.billing_period == billing_period)

    query = query.order_by(UsageRecord.recorded_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{subscriber_id}/summary", response_model=UsageSummary)
async def get_usage_summary(
    subscriber_id: UUID,
    billing_period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregated summary for a billing period (used by billing-service)."""
    totals = await _get_db_summary(db, subscriber_id, billing_period)
    return {
        "subscriber_id": subscriber_id,
        "billing_period": billing_period,
        "data_used_mb": totals["data"],
        "voice_used_minutes": totals["voice"],
        "sms_used_count": totals["sms"],
    }


# ---------- Health / Readiness ----------

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health() -> dict:
    return {"status": "alive"}


@health_router.get("/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    checks: dict[str, str] = {}

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    # Redis check
    r = await get_redis()
    if r is not None:
        try:
            await r.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
    else:
        checks["redis"] = "unavailable"

    # RabbitMQ check
    checks["rabbitmq"] = "ok" if await rabbitmq_healthy() else "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=checks,
        )
    return {"status": "ready", "checks": checks}


@health_router.post("/crash")
async def crash():
    import asyncio, os, signal
    asyncio.get_event_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)
    return {"status": "crashing"}
