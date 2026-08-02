import logging

import httpx
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, StreamingResponse

from .config import settings
from .middleware import circuit_breaker

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)

ROUTE_MAP = {
    "subscribers": settings.subscriber_service_url,
    "plans": settings.plan_service_url,
    "usage": settings.usage_service_url,
    "billing": settings.billing_service_url,
    "notifications": settings.notification_service_url,
    "network": settings.network_service_url,
}


async def _proxy(service_name: str, base_url: str, path: str, request: Request):
    if circuit_breaker.is_open(service_name):
        return JSONResponse(
            {"error": f"{service_name} is temporarily unavailable (circuit open)"},
            status_code=503,
        )

    target_url = f"{base_url}/{path}"
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "transfer-encoding")
    }
    headers["X-Request-ID"] = getattr(request.state, "request_id", "unknown")

    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout, follow_redirects=True) as client:
            body = await request.body()
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body if body else None,
                params=dict(request.query_params),
            )
        circuit_breaker.record_success(service_name)
        proxy_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")
        }
        return StreamingResponse(
            content=iter([resp.content]),
            status_code=resp.status_code,
            headers=proxy_headers,
            media_type=resp.headers.get("content-type"),
        )
    except Exception as exc:
        circuit_breaker.record_failure(service_name)
        logger.error("Proxy to %s failed: %s", service_name, exc)
        return JSONResponse(
            {"error": f"Failed to reach {service_name}", "detail": str(exc)},
            status_code=502,
        )


@router.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_request(service: str, path: str, request: Request):
    if service not in ROUTE_MAP:
        return JSONResponse(
            {"error": f"Unknown service: {service}", "available": list(ROUTE_MAP.keys())},
            status_code=404,
        )
    return await _proxy(service, ROUTE_MAP[service], path, request)
