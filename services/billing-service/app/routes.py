import logging
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.events import publish_event, rabbitmq_healthy
from app.models import Invoice, InvoiceLineItem
from app.schemas import (
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceStatusUpdate,
    RevenueSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ---------- Helper: inter-service calls ----------


async def _get_subscriber(subscriber_id: UUID) -> dict:
    """Fetch subscriber info from subscriber-service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.subscriber_service_url}/subscribers/{subscriber_id}"
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Subscriber {subscriber_id} not found",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Subscriber service returned status {resp.status_code}",
            )
    except httpx.HTTPError as exc:
        logger.error(
            "Failed to reach subscriber-service: %s", exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subscriber service unavailable",
        )


async def _get_plan(plan_id: UUID) -> dict:
    """Fetch plan details from plan-service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.plan_service_url}/plans/{plan_id}"
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Plan {plan_id} not found",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Plan service returned status {resp.status_code}",
            )
    except httpx.HTTPError as exc:
        logger.error(
            "Failed to reach plan-service: %s", exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plan service unavailable",
        )


async def _get_usage_summary(subscriber_id: UUID) -> dict | None:
    """Fetch usage summary from usage-service. Returns None if unavailable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.usage_service_url}/usage/summary/{subscriber_id}"
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "Usage service returned status %s for subscriber %s",
                resp.status_code,
                subscriber_id,
            )
            return None
    except httpx.HTTPError as exc:
        logger.warning(
            "Could not reach usage-service: %s — proceeding without usage data",
            exc,
        )
        return None


async def _list_active_subscribers() -> list[dict]:
    """Fetch all active subscribers from subscriber-service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.subscriber_service_url}/subscribers/",
                params={"status": "active", "limit": 100},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("subscribers", [])
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Subscriber service returned status {resp.status_code}",
            )
    except httpx.HTTPError as exc:
        logger.error(
            "Failed to reach subscriber-service: %s", exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subscriber service unavailable",
        )


def _quantize(value: Decimal, places: int = 2) -> Decimal:
    """Round a Decimal to the given number of decimal places."""
    q = Decimal(10) ** -places
    return value.quantize(q, rounding=ROUND_HALF_UP)


# ---------- Invoice generation ----------


async def _generate_invoice_for_subscriber(
    subscriber_id: UUID,
    db: AsyncSession,
) -> Invoice:
    """Core logic: build an invoice for one subscriber."""
    now = datetime.now(timezone.utc)
    billing_period = now.strftime("%Y-%m")

    # 1. Get subscriber info
    subscriber = await _get_subscriber(subscriber_id)

    plan_id = subscriber.get("plan_id")
    if plan_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Subscriber {subscriber_id} has no plan assigned",
        )

    # 2. Get plan pricing
    plan = await _get_plan(plan_id)

    # 3. Get usage summary (best-effort)
    usage = await _get_usage_summary(subscriber_id)

    # 4. Calculate amounts
    base_amount = _quantize(Decimal(str(plan["monthly_price_eur"])))

    line_items: list[InvoiceLineItem] = []

    # Base plan line item
    line_items.append(
        InvoiceLineItem(
            description=f"Monthly plan: {plan['name']}",
            quantity=Decimal("1"),
            unit_price_eur=base_amount,
            total_eur=base_amount,
        )
    )

    # Overage calculation
    overage_total = Decimal("0.00")

    if usage:
        # Data overage: EUR 0.05 per MB over limit
        data_used_mb = Decimal(str(usage.get("total_data_mb", 0)))
        data_limit = plan.get("data_limit_mb")
        if data_limit is not None and data_used_mb > data_limit:
            data_over = data_used_mb - Decimal(str(data_limit))
            data_rate = Decimal("0.05")
            data_overage = _quantize(data_over * data_rate)
            overage_total += data_overage
            line_items.append(
                InvoiceLineItem(
                    description="Data overage",
                    quantity=data_over,
                    unit_price_eur=data_rate,
                    total_eur=data_overage,
                )
            )

        # Voice overage: EUR 0.15 per minute over limit
        voice_used = Decimal(str(usage.get("total_voice_minutes", 0)))
        voice_limit = plan.get("voice_minutes")
        if voice_limit is not None and voice_used > voice_limit:
            voice_over = voice_used - Decimal(str(voice_limit))
            voice_rate = Decimal("0.15")
            voice_overage = _quantize(voice_over * voice_rate)
            overage_total += voice_overage
            line_items.append(
                InvoiceLineItem(
                    description="Voice overage",
                    quantity=voice_over,
                    unit_price_eur=voice_rate,
                    total_eur=voice_overage,
                )
            )

        # SMS overage: EUR 0.10 per SMS over limit
        sms_used = Decimal(str(usage.get("total_sms", 0)))
        sms_limit = plan.get("sms_limit")
        if sms_limit is not None and sms_used > sms_limit:
            sms_over = sms_used - Decimal(str(sms_limit))
            sms_rate = Decimal("0.10")
            sms_overage = _quantize(sms_over * sms_rate)
            overage_total += sms_overage
            line_items.append(
                InvoiceLineItem(
                    description="SMS overage",
                    quantity=sms_over,
                    unit_price_eur=sms_rate,
                    total_eur=sms_overage,
                )
            )

    subtotal = base_amount + overage_total
    tax_rate = Decimal(str(settings.tax_rate))
    tax_amount = _quantize(subtotal * tax_rate)
    total_amount = _quantize(subtotal + tax_amount)

    # Tax line item
    line_items.append(
        InvoiceLineItem(
            description=f"VAT ({int(tax_rate * 100)}%)",
            quantity=Decimal("1"),
            unit_price_eur=tax_amount,
            total_eur=tax_amount,
        )
    )

    # 5. Create invoice
    invoice = Invoice(
        subscriber_id=subscriber_id,
        billing_period=billing_period,
        plan_base_amount_eur=base_amount,
        overage_amount_eur=overage_total,
        tax_amount_eur=tax_amount,
        total_amount_eur=total_amount,
        status="issued",
        issued_at=now,
        due_date=(now + timedelta(days=30)).date(),
        line_items=line_items,
    )
    db.add(invoice)
    await db.flush()
    await db.refresh(invoice)

    # 6. Publish event
    await publish_event(
        "invoice.issued",
        {
            "invoice_id": str(invoice.id),
            "subscriber_id": str(subscriber_id),
            "billing_period": billing_period,
            "total_amount_eur": str(total_amount),
        },
    )

    logger.info(
        "Generated invoice %s for subscriber %s (period %s, total EUR %s)",
        invoice.id,
        subscriber_id,
        billing_period,
        total_amount,
    )

    return invoice


# ---------- Routes ----------


@router.post(
    "/generate/{subscriber_id}",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_invoice(
    subscriber_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Invoice:
    """Generate an invoice for a subscriber for the current billing period."""
    return await _generate_invoice_for_subscriber(subscriber_id, db)


@router.post("/generate-all", status_code=status.HTTP_200_OK)
async def generate_all_invoices(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate invoices for all active subscribers."""
    subscribers = await _list_active_subscribers()

    results = {"generated": 0, "failed": 0, "errors": []}

    for sub in subscribers:
        sub_id = UUID(sub["id"])
        try:
            await _generate_invoice_for_subscriber(sub_id, db)
            results["generated"] += 1
        except HTTPException as exc:
            results["failed"] += 1
            results["errors"].append(
                {"subscriber_id": str(sub_id), "detail": exc.detail}
            )
            logger.warning(
                "Failed to generate invoice for %s: %s", sub_id, exc.detail
            )
        except Exception as exc:
            results["failed"] += 1
            results["errors"].append(
                {"subscriber_id": str(sub_id), "detail": str(exc)}
            )
            logger.exception(
                "Unexpected error generating invoice for %s", sub_id
            )

    return results


@router.get("/invoices", response_model=InvoiceListResponse)
async def list_invoices(
    subscriber_id: UUID | None = Query(None),
    billing_period: str | None = Query(None, max_length=7),
    invoice_status: str | None = Query(None, alias="status", max_length=20),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List invoices with optional filters."""
    query = select(Invoice)

    if subscriber_id is not None:
        query = query.where(Invoice.subscriber_id == subscriber_id)
    if billing_period is not None:
        query = query.where(Invoice.billing_period == billing_period)
    if invoice_status is not None:
        query = query.where(Invoice.status == invoice_status)

    query = query.order_by(Invoice.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    invoices = list(result.scalars().all())

    return {"count": len(invoices), "invoices": invoices}


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Invoice:
    """Get a single invoice with its line items."""
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found",
        )
    return invoice


@router.patch(
    "/invoices/{invoice_id}/status", response_model=InvoiceResponse
)
async def update_invoice_status(
    invoice_id: UUID,
    payload: InvoiceStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> Invoice:
    """Update the status of an invoice."""
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found",
        )

    old_status = invoice.status
    invoice.status = payload.status

    if payload.status == "issued" and invoice.issued_at is None:
        invoice.issued_at = datetime.now(timezone.utc)
        invoice.due_date = (
            datetime.now(timezone.utc) + timedelta(days=30)
        ).date()

    await db.flush()
    await db.refresh(invoice)

    logger.info(
        "Invoice %s status changed: %s -> %s",
        invoice_id,
        old_status,
        payload.status,
    )

    return invoice


@router.get("/revenue/summary", response_model=RevenueSummary)
async def revenue_summary(
    billing_period: str = Query(..., max_length=7),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregate revenue summary for a given billing period."""
    base_query = select(Invoice).where(
        Invoice.billing_period == billing_period
    )

    result = await db.execute(base_query)
    invoices = list(result.scalars().all())

    total_revenue = sum(
        (inv.total_amount_eur for inv in invoices), Decimal("0.00")
    )
    paid_count = sum(1 for inv in invoices if inv.status == "paid")
    outstanding_count = sum(
        1 for inv in invoices if inv.status in ("issued", "overdue")
    )

    return {
        "billing_period": billing_period,
        "total_revenue_eur": total_revenue,
        "invoice_count": len(invoices),
        "paid_count": paid_count,
        "outstanding_count": outstanding_count,
    }


# ---------- Health / Readiness ----------

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health() -> dict:
    return {"status": "alive"}


@health_router.get("/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
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
