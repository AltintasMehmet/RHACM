import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.consumers import rabbitmq_healthy
from app.database import get_db
from app.models import Notification
from app.schemas import (
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/health", response_model=dict, include_in_schema=False)
async def health():
    return {"status": "alive"}


@router.get("/ready", response_model=dict, include_in_schema=False)
async def readiness(db: AsyncSession = Depends(get_db)):
    checks = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
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


@router.get("/recent", response_model=NotificationListResponse)
async def list_recent_notifications(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List recent notifications across all subscribers."""
    result = await db.execute(
        select(Notification)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifications = result.scalars().all()
    return NotificationListResponse(
        count=len(notifications), notifications=notifications
    )


@router.get(
    "/{subscriber_id}", response_model=NotificationListResponse
)
async def list_subscriber_notifications(
    subscriber_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List notifications for a specific subscriber, paginated."""
    count_query = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.subscriber_id == subscriber_id)
    )
    total = (await db.execute(count_query)).scalar()

    result = await db.execute(
        select(Notification)
        .where(Notification.subscriber_id == subscriber_id)
        .order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    notifications = result.scalars().all()

    return NotificationListResponse(
        count=total, notifications=notifications
    )


@router.post(
    "/send", response_model=NotificationResponse, status_code=201
)
async def send_notification(
    payload: NotificationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Manually create and 'send' a notification (demo mode)."""
    notification = Notification(
        subscriber_id=payload.subscriber_id,
        notification_type=payload.notification_type,
        channel=payload.channel,
        subject=payload.subject,
        body=payload.body,
        status="sent",
        sent_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)

    logger.info(
        "[DEMO SEND] %s notification via %s to subscriber %s: %s",
        payload.notification_type,
        payload.channel,
        payload.subscriber_id,
        payload.subject,
    )

    return notification


