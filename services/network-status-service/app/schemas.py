from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RegionStatus(BaseModel):
    region: str
    status: Literal["operational", "degraded", "outage"]
    active_towers: int
    total_towers: int
    latency_ms: float


class NetworkOverview(BaseModel):
    overall_status: str
    regions: list[RegionStatus]
    active_outages: int
    last_updated: datetime


class OutageCreate(BaseModel):
    region: str
    affected_towers: int
    description: str
    severity: Literal["minor", "major", "critical"]


class OutageResponse(BaseModel):
    id: str
    region: str
    affected_towers: int
    description: str
    severity: str
    status: str
    started_at: datetime
    resolved_at: datetime | None = None


class OutageListResponse(BaseModel):
    count: int
    outages: list[OutageResponse]


class TowerStatus(BaseModel):
    tower_id: str
    region: str
    status: str
    lat: float
    lon: float
