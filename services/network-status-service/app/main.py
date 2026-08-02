import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.events import close_rabbitmq, connect_rabbitmq
from app.redis_client import close_redis, get_redis
from app.routes import router
from app.seed import seed_data

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    await get_redis()
    logger.info("Redis connection established")

    await seed_data()
    await connect_rabbitmq()

    yield

    # Shutdown
    await close_rabbitmq()
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title="TelePortal Network Status Service",
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)

Instrumentator().instrument(app).expose(app)
