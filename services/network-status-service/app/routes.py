import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.events import publish_event, rabbitmq_healthy
from app.redis_client import get_redis, redis_healthy
from app.schemas import (
    NetworkOverview,
    OutageCreate,
    OutageListResponse,
    OutageResponse,
    RegionStatus,
    TowerStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["network"])

VALID_REGIONS = {"flanders", "wallonia", "brussels"}


async def _get_region_status(r, region_key: str) -> RegionStatus | None:
    """Read a single region's status from Redis."""
    data = await r.hgetall(f"network:region:{region_key}")
    if not data:
        return None
    return RegionStatus(
        region=data.get("name", region_key),
        status=data.get("status", "operational"),
        active_towers=int(data.get("active_towers", 0)),
        total_towers=int(data.get("total_towers", 0)),
        latency_ms=float(data.get("latency_ms", 0.0)),
    )


def _calculate_overall_status(regions: list[RegionStatus]) -> str:
    """Determine overall network status from individual region statuses."""
    statuses = {r.status for r in regions}
    if "outage" in statuses:
        return "outage"
    if "degraded" in statuses:
        return "degraded"
    return "operational"


@router.get("/status", response_model=NetworkOverview)
async def network_status():
    """Overall network health across all regions."""
    try:
        r = await get_redis()
        region_keys = await r.smembers("network:regions")

        regions = []
        for key in sorted(region_keys):
            status = await _get_region_status(r, key)
            if status:
                regions.append(status)

        # Count active outages
        active_outage_ids = await r.smembers("network:outages:active")
        active_outages = len(active_outage_ids)

        return NetworkOverview(
            overall_status=_calculate_overall_status(regions),
            regions=regions,
            active_outages=active_outages,
            last_updated=datetime.now(timezone.utc),
        )
    except Exception:
        logger.error("Failed to fetch network status", exc_info=True)
        raise HTTPException(status_code=503, detail="Redis unavailable")


@router.get("/regions", response_model=list[RegionStatus])
async def list_regions():
    """List all regions with their current status."""
    try:
        r = await get_redis()
        region_keys = await r.smembers("network:regions")

        regions = []
        for key in sorted(region_keys):
            status = await _get_region_status(r, key)
            if status:
                regions.append(status)

        return regions
    except Exception:
        logger.error("Failed to list regions", exc_info=True)
        raise HTTPException(status_code=503, detail="Redis unavailable")


@router.get("/regions/{region}", response_model=RegionStatus)
async def get_region(region: str):
    """Detailed status for a specific region."""
    region_lower = region.lower()
    if region_lower not in VALID_REGIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Region '{region}' not found. Valid regions: Flanders, Wallonia, Brussels",
        )
    try:
        r = await get_redis()
        status = await _get_region_status(r, region_lower)
        if status is None:
            raise HTTPException(status_code=404, detail="Region data not found")
        return status
    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to get region %s", region, exc_info=True)
        raise HTTPException(status_code=503, detail="Redis unavailable")


@router.get("/outages", response_model=OutageListResponse)
async def list_outages():
    """List active and recent outages."""
    try:
        r = await get_redis()

        # Get all outage IDs (active + recent resolved)
        active_ids = await r.smembers("network:outages:active")
        resolved_ids = await r.zrevrange("network:outages:resolved", 0, 49)
        all_ids = list(active_ids) + list(resolved_ids)

        outages = []
        for outage_id in all_ids:
            data = await r.hgetall(f"network:outage:{outage_id}")
            if data:
                outages.append(OutageResponse(
                    id=outage_id,
                    region=data["region"],
                    affected_towers=int(data["affected_towers"]),
                    description=data["description"],
                    severity=data["severity"],
                    status=data["status"],
                    started_at=datetime.fromisoformat(data["started_at"]),
                    resolved_at=(
                        datetime.fromisoformat(data["resolved_at"])
                        if data.get("resolved_at")
                        else None
                    ),
                ))

        # Sort: active first, then by started_at descending
        outages.sort(
            key=lambda o: (o.status != "active", o.started_at),
            reverse=False,
        )
        # Re-sort so active come first, and within each group newest first
        active = [o for o in outages if o.status == "active"]
        resolved = [o for o in outages if o.status == "resolved"]
        active.sort(key=lambda o: o.started_at, reverse=True)
        resolved.sort(key=lambda o: o.started_at, reverse=True)
        outages = active + resolved

        return OutageListResponse(count=len(outages), outages=outages)
    except Exception:
        logger.error("Failed to list outages", exc_info=True)
        raise HTTPException(status_code=503, detail="Redis unavailable")


@router.post("/outages", response_model=OutageResponse, status_code=201)
async def create_outage(payload: OutageCreate):
    """Simulate an outage in a region."""
    region_lower = payload.region.lower()
    if region_lower not in VALID_REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid region '{payload.region}'. Valid regions: Flanders, Wallonia, Brussels",
        )

    try:
        r = await get_redis()

        # Validate affected_towers against region total
        region_data = await r.hgetall(f"network:region:{region_lower}")
        if not region_data:
            raise HTTPException(status_code=404, detail="Region data not found")

        total_towers = int(region_data["total_towers"])
        if payload.affected_towers > total_towers:
            raise HTTPException(
                status_code=400,
                detail=f"affected_towers ({payload.affected_towers}) exceeds total towers ({total_towers}) in {payload.region}",
            )

        outage_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        outage_data = {
            "region": region_lower,
            "affected_towers": str(payload.affected_towers),
            "description": payload.description,
            "severity": payload.severity,
            "status": "active",
            "started_at": now.isoformat(),
        }

        pipe = r.pipeline()
        pipe.hset(f"network:outage:{outage_id}", mapping=outage_data)
        pipe.sadd("network:outages:active", outage_id)

        # Update region status based on severity
        new_active = int(region_data["active_towers"]) - payload.affected_towers
        new_status = "degraded" if payload.severity == "minor" else "outage"
        pipe.hset(f"network:region:{region_lower}", mapping={
            "active_towers": str(max(new_active, 0)),
            "status": new_status,
        })

        await pipe.execute()

        await publish_event("network.outage_started", {
            "outage_id": outage_id,
            "region": region_lower,
            "affected_towers": payload.affected_towers,
            "severity": payload.severity,
            "description": payload.description,
            "started_at": now.isoformat(),
        })

        return OutageResponse(
            id=outage_id,
            region=region_lower,
            affected_towers=payload.affected_towers,
            description=payload.description,
            severity=payload.severity,
            status="active",
            started_at=now,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to create outage", exc_info=True)
        raise HTTPException(status_code=503, detail="Redis unavailable")


@router.patch("/outages/{outage_id}/resolve", response_model=OutageResponse)
async def resolve_outage(outage_id: str):
    """Mark an outage as resolved and restore region status."""
    try:
        r = await get_redis()

        outage_key = f"network:outage:{outage_id}"
        data = await r.hgetall(outage_key)
        if not data:
            raise HTTPException(status_code=404, detail="Outage not found")

        if data["status"] == "resolved":
            raise HTTPException(status_code=409, detail="Outage already resolved")

        now = datetime.now(timezone.utc)
        region_key = data["region"]
        affected = int(data["affected_towers"])

        pipe = r.pipeline()

        # Update outage status
        pipe.hset(outage_key, mapping={
            "status": "resolved",
            "resolved_at": now.isoformat(),
        })

        # Move from active to resolved sorted set (scored by timestamp)
        pipe.srem("network:outages:active", outage_id)
        pipe.zadd("network:outages:resolved", {outage_id: now.timestamp()})

        await pipe.execute()

        # Restore region towers and recalculate status
        region_data = await r.hgetall(f"network:region:{region_key}")
        new_active = int(region_data["active_towers"]) + affected
        total = int(region_data["total_towers"])
        new_active = min(new_active, total)

        # Check if there are still active outages in this region
        active_ids = await r.smembers("network:outages:active")
        has_active_outage = False
        for aid in active_ids:
            outage_info = await r.hgetall(f"network:outage:{aid}")
            if outage_info and outage_info.get("region") == region_key:
                has_active_outage = True
                break

        new_status = "operational" if not has_active_outage else region_data["status"]

        await r.hset(f"network:region:{region_key}", mapping={
            "active_towers": str(new_active),
            "status": new_status,
        })

        await publish_event("network.outage_resolved", {
            "outage_id": outage_id,
            "region": region_key,
            "affected_towers": affected,
            "resolved_at": now.isoformat(),
        })

        return OutageResponse(
            id=outage_id,
            region=region_key,
            affected_towers=affected,
            description=data["description"],
            severity=data["severity"],
            status="resolved",
            started_at=datetime.fromisoformat(data["started_at"]),
            resolved_at=now,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to resolve outage %s", outage_id, exc_info=True)
        raise HTTPException(status_code=503, detail="Redis unavailable")


@router.get("/towers/{tower_id}", response_model=TowerStatus)
async def get_tower(tower_id: str):
    """Get the status of an individual tower."""
    try:
        r = await get_redis()
        data = await r.hgetall(f"network:tower:{tower_id}")
        if not data:
            raise HTTPException(status_code=404, detail="Tower not found")
        return TowerStatus(
            tower_id=data["tower_id"],
            region=data["region"],
            status=data["status"],
            lat=float(data["lat"]),
            lon=float(data["lon"]),
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to get tower %s", tower_id, exc_info=True)
        raise HTTPException(status_code=503, detail="Redis unavailable")


@router.get("/health", response_model=dict, include_in_schema=False)
async def health():
    return {"status": "alive"}


@router.get("/ready", response_model=dict, include_in_schema=False)
async def readiness():
    checks = {}

    # Redis check
    checks["redis"] = "ok" if await redis_healthy() else "unavailable"

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
