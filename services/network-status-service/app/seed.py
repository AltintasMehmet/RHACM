import logging

from app.redis_client import get_redis

logger = logging.getLogger(__name__)

REGIONS = {
    "flanders": {
        "name": "Flanders",
        "status": "operational",
        "active_towers": 450,
        "total_towers": 450,
        "latency_ms": 12.5,
    },
    "wallonia": {
        "name": "Wallonia",
        "status": "operational",
        "active_towers": 320,
        "total_towers": 320,
        "latency_ms": 14.2,
    },
    "brussels": {
        "name": "Brussels",
        "status": "operational",
        "active_towers": 180,
        "total_towers": 180,
        "latency_ms": 10.8,
    },
}

# 10 sample towers per region with realistic Belgian GPS coordinates
TOWERS = {
    "flanders": [
        {"tower_id": "FL-001", "lat": 51.2194, "lon": 4.4025, "status": "online"},   # Antwerp
        {"tower_id": "FL-002", "lat": 51.0543, "lon": 3.7174, "status": "online"},   # Ghent
        {"tower_id": "FL-003", "lat": 50.8798, "lon": 4.7005, "status": "online"},   # Leuven
        {"tower_id": "FL-004", "lat": 51.3292, "lon": 3.1869, "status": "online"},   # Bruges
        {"tower_id": "FL-005", "lat": 51.0259, "lon": 4.4776, "status": "online"},   # Mechelen
        {"tower_id": "FL-006", "lat": 50.9307, "lon": 5.3325, "status": "online"},   # Hasselt
        {"tower_id": "FL-007", "lat": 51.1667, "lon": 4.1500, "status": "online"},   # Sint-Niklaas
        {"tower_id": "FL-008", "lat": 50.8503, "lon": 4.3517, "status": "online"},   # Halle
        {"tower_id": "FL-009", "lat": 51.0742, "lon": 4.0018, "status": "online"},   # Dendermonde
        {"tower_id": "FL-010", "lat": 50.9879, "lon": 5.0547, "status": "online"},   # Diest
    ],
    "wallonia": [
        {"tower_id": "WA-001", "lat": 50.4674, "lon": 4.8712, "status": "online"},   # Namur
        {"tower_id": "WA-002", "lat": 50.6326, "lon": 5.5797, "status": "online"},   # Liege
        {"tower_id": "WA-003", "lat": 50.4108, "lon": 4.4446, "status": "online"},   # Charleroi
        {"tower_id": "WA-004", "lat": 50.6050, "lon": 3.3883, "status": "online"},   # Tournai
        {"tower_id": "WA-005", "lat": 50.4542, "lon": 3.9561, "status": "online"},   # Mons
        {"tower_id": "WA-006", "lat": 49.6833, "lon": 5.8167, "status": "online"},   # Arlon
        {"tower_id": "WA-007", "lat": 50.0875, "lon": 5.8676, "status": "online"},   # Bastogne
        {"tower_id": "WA-008", "lat": 50.2647, "lon": 4.8684, "status": "online"},   # Dinant
        {"tower_id": "WA-009", "lat": 50.5985, "lon": 4.3260, "status": "online"},   # Nivelles
        {"tower_id": "WA-010", "lat": 50.4867, "lon": 3.8081, "status": "online"},   # Soignies
    ],
    "brussels": [
        {"tower_id": "BR-001", "lat": 50.8503, "lon": 4.3517, "status": "online"},   # City centre
        {"tower_id": "BR-002", "lat": 50.8660, "lon": 4.3636, "status": "online"},   # Schaerbeek
        {"tower_id": "BR-003", "lat": 50.8218, "lon": 4.3414, "status": "online"},   # Uccle
        {"tower_id": "BR-004", "lat": 50.8557, "lon": 4.3190, "status": "online"},   # Molenbeek
        {"tower_id": "BR-005", "lat": 50.8389, "lon": 4.3964, "status": "online"},   # Etterbeek
        {"tower_id": "BR-006", "lat": 50.8676, "lon": 4.4139, "status": "online"},   # Evere
        {"tower_id": "BR-007", "lat": 50.8312, "lon": 4.3680, "status": "online"},   # Ixelles
        {"tower_id": "BR-008", "lat": 50.8486, "lon": 4.4361, "status": "online"},   # Woluwe-Saint-Lambert
        {"tower_id": "BR-009", "lat": 50.8116, "lon": 4.3450, "status": "online"},   # Forest
        {"tower_id": "BR-010", "lat": 50.8625, "lon": 4.2850, "status": "online"},   # Jette
    ],
}


async def seed_data() -> None:
    """Seed Redis with initial region, tower, and outage data if not already present."""
    try:
        r = await get_redis()

        # Check if data is already seeded
        if await r.exists("network:regions"):
            logger.info("Network data already seeded — skipping")
            return

        pipe = r.pipeline()

        # Seed regions
        region_keys = []
        for region_key, region_data in REGIONS.items():
            redis_key = f"network:region:{region_key}"
            region_keys.append(region_key)
            pipe.hset(redis_key, mapping={
                "name": region_data["name"],
                "status": region_data["status"],
                "active_towers": str(region_data["active_towers"]),
                "total_towers": str(region_data["total_towers"]),
                "latency_ms": str(region_data["latency_ms"]),
            })

        # Store region list
        pipe.sadd("network:regions", *region_keys)

        # Seed towers
        for region_key, towers in TOWERS.items():
            for tower in towers:
                tower_key = f"network:tower:{tower['tower_id']}"
                pipe.hset(tower_key, mapping={
                    "tower_id": tower["tower_id"],
                    "region": region_key,
                    "status": tower["status"],
                    "lat": str(tower["lat"]),
                    "lon": str(tower["lon"]),
                })
                # Add tower to region's tower set
                pipe.sadd(f"network:region:{region_key}:towers", tower["tower_id"])

        await pipe.execute()
        logger.info(
            "Seeded network data: %d regions, %d towers",
            len(REGIONS),
            sum(len(t) for t in TOWERS.values()),
        )

    except Exception:
        logger.error("Failed to seed network data", exc_info=True)
