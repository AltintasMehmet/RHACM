import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.events import publish_event, rabbitmq_healthy
from app.models import Subscriber
from app.schemas import (
    StatusUpdate,
    SubscriberCreate,
    SubscriberListResponse,
    SubscriberResponse,
    SubscriberUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscribers", tags=["subscribers"])


# ------------------------------------------------------------------
# Health / readiness — declared first so they aren't shadowed by
# the /{subscriber_id} path parameter.
# ------------------------------------------------------------------


@router.get("/health", response_model=dict, include_in_schema=False)
async def health():
    return {"status": "alive"}


@router.get("/ready", response_model=dict, include_in_schema=False)
async def readiness(db: AsyncSession = Depends(get_db)):
    checks = {}

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    # RabbitMQ check
    checks["rabbitmq"] = "ok" if await rabbitmq_healthy() else "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", **checks}


@router.post("/crash", response_model=dict, include_in_schema=False)
async def crash():
    import asyncio, os, signal
    asyncio.get_event_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)
    return {"status": "crashing"}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _validate_plan(plan_id: uuid.UUID) -> bool:
    """Call plan-service to verify a plan exists. Returns True if valid or
    if plan-service is unreachable (fail-open)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.plan_service_url}/plans/{plan_id}"
            )
            if resp.status_code == 200:
                return True
            if resp.status_code == 404:
                return False
            logger.warning(
                "plan-service returned unexpected status %s", resp.status_code
            )
            return True  # fail-open
    except Exception:
        logger.warning(
            "Could not reach plan-service — skipping plan validation",
            exc_info=True,
        )
        return True  # fail-open


@router.post("/", response_model=SubscriberResponse, status_code=201)
async def create_subscriber(
    payload: SubscriberCreate, db: AsyncSession = Depends(get_db)
):
    # Validate plan_id if provided
    if payload.plan_id is not None:
        valid = await _validate_plan(payload.plan_id)
        if not valid:
            raise HTTPException(
                status_code=400,
                detail=f"Plan {payload.plan_id} does not exist",
            )

    # Check for duplicate msisdn
    existing = await db.execute(
        select(Subscriber).where(Subscriber.msisdn == payload.msisdn)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Subscriber with msisdn {payload.msisdn} already exists",
        )

    subscriber = Subscriber(**payload.model_dump())
    db.add(subscriber)
    await db.flush()
    await db.refresh(subscriber)

    await publish_event(
        "subscriber.created",
        {"subscriber_id": str(subscriber.id), "msisdn": subscriber.msisdn},
    )

    return subscriber


@router.get("/", response_model=SubscriberListResponse)
async def list_subscribers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Subscriber)
    count_query = select(func.count()).select_from(Subscriber)

    if status:
        query = query.where(Subscriber.status == status)
        count_query = count_query.where(Subscriber.status == status)

    total = (await db.execute(count_query)).scalar()
    result = await db.execute(
        query.order_by(Subscriber.created_at.desc()).offset(skip).limit(limit)
    )
    subscribers = result.scalars().all()

    return SubscriberListResponse(count=total, subscribers=subscribers)


@router.get("/msisdn/{msisdn}", response_model=SubscriberResponse)
async def get_subscriber_by_msisdn(
    msisdn: str, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Subscriber).where(Subscriber.msisdn == msisdn)
    )
    subscriber = result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    return subscriber


@router.get("/{subscriber_id}", response_model=SubscriberResponse)
async def get_subscriber(
    subscriber_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Subscriber).where(Subscriber.id == subscriber_id)
    )
    subscriber = result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    return subscriber


@router.put("/{subscriber_id}", response_model=SubscriberResponse)
async def update_subscriber(
    subscriber_id: uuid.UUID,
    payload: SubscriberUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscriber).where(Subscriber.id == subscriber_id)
    )
    subscriber = result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subscriber, field, value)

    await db.flush()
    await db.refresh(subscriber)
    return subscriber


@router.patch("/{subscriber_id}/status", response_model=SubscriberResponse)
async def change_status(
    subscriber_id: uuid.UUID,
    payload: StatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscriber).where(Subscriber.id == subscriber_id)
    )
    subscriber = result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    old_status = subscriber.status
    subscriber.status = payload.status
    await db.flush()
    await db.refresh(subscriber)

    await publish_event(
        "subscriber.status_changed",
        {
            "subscriber_id": str(subscriber.id),
            "msisdn": subscriber.msisdn,
            "old_status": old_status,
            "new_status": payload.status,
        },
    )

    return subscriber


@router.delete("/{subscriber_id}", response_model=SubscriberResponse)
async def delete_subscriber(
    subscriber_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Subscriber).where(Subscriber.id == subscriber_id)
    )
    subscriber = result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    subscriber.status = "terminated"
    await db.flush()
    await db.refresh(subscriber)
    return subscriber
