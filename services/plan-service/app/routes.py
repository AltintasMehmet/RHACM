import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Plan, PlanFeature
from app.schemas import (
    PlanCreate,
    PlanListResponse,
    PlanResponse,
    PlanUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanCreate,
    db: AsyncSession = Depends(get_db),
) -> Plan:
    plan = Plan(
        name=payload.name,
        plan_type=payload.plan_type,
        data_limit_mb=payload.data_limit_mb,
        voice_minutes=payload.voice_minutes,
        sms_limit=payload.sms_limit,
        monthly_price_eur=payload.monthly_price_eur,
        speed_mbps=payload.speed_mbps,
        is_active=payload.is_active,
    )
    if payload.features:
        for feat in payload.features:
            plan.features.append(
                PlanFeature(
                    feature_name=feat.feature_name,
                    feature_value=feat.feature_value,
                )
            )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    logger.info("Created plan %s (%s)", plan.name, plan.id)
    return plan


@router.get("/", response_model=PlanListResponse)
async def list_plans(
    plan_type: str | None = Query(None, max_length=20),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(Plan)

    if plan_type is not None:
        query = query.where(Plan.plan_type == plan_type)
    if is_active is not None:
        query = query.where(Plan.is_active == is_active)

    query = query.order_by(Plan.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    plans = list(result.scalars().all())

    return {"count": len(plans), "plans": plans}


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Plan:
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )
    return plan


@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    db: AsyncSession = Depends(get_db),
) -> Plan:
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    features_data = update_data.pop("features", None)

    for field, value in update_data.items():
        setattr(plan, field, value)

    if features_data is not None:
        plan.features.clear()
        for feat in features_data:
            plan.features.append(
                PlanFeature(
                    feature_name=feat["feature_name"],
                    feature_value=feat["feature_value"],
                )
            )

    await db.flush()
    await db.refresh(plan)
    logger.info("Updated plan %s (%s)", plan.name, plan.id)
    return plan


@router.patch("/{plan_id}/deactivate", response_model=PlanResponse)
async def deactivate_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Plan:
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )
    plan.is_active = False
    await db.flush()
    await db.refresh(plan)
    logger.info("Deactivated plan %s (%s)", plan.name, plan.id)
    return plan


# ---------- Health / Readiness ----------

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health() -> dict:
    return {"status": "alive"}


@health_router.get("/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        logger.exception("Readiness check failed — database unreachable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )
    return {"status": "ready", "checks": {"database": db_status}}


@health_router.post("/crash")
async def crash():
    import asyncio, os, signal
    asyncio.get_event_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)
    return {"status": "crashing"}
