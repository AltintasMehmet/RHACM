import logging

import httpx
from fastapi import APIRouter

from .config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

SERVICE_URLS = {
    "subscriber-service": settings.subscriber_service_url,
    "plan-service": settings.plan_service_url,
    "usage-service": settings.usage_service_url,
    "billing-service": settings.billing_service_url,
    "notification-service": settings.notification_service_url,
    "network-status-service": settings.network_service_url,
}


@router.get("/health")
async def liveness():
    return {"status": "alive"}


@router.post("/crash")
async def crash():
    """Kill this service to demo self-healing. Docker/K8s will restart it."""
    import asyncio, os, signal
    asyncio.get_event_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)
    return {"status": "crashing"}


@router.get("/ready")
async def readiness():
    checks = {}
    all_ok = True
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in SERVICE_URLS.items():
            try:
                resp = await client.get(f"{url}/health")
                checks[name] = "ok" if resp.status_code == 200 else "degraded"
            except Exception:
                checks[name] = "unavailable"
                all_ok = False
    status_code = 200 if all_ok else 503
    from starlette.responses import JSONResponse

    return JSONResponse(
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
        status_code=status_code,
    )
