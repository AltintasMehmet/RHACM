import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.database import Base, async_session_factory, engine
from app.events import close_rabbitmq, connect_rabbitmq
from app.redis_client import close_redis, connect_redis
from app.routes import health_router, router
from app.seed import seed_usage

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---------- Startup ----------
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    async with async_session_factory() as session:
        await seed_usage(session)

    await connect_redis()
    await connect_rabbitmq()

    yield

    # ---------- Shutdown ----------
    logger.info("Shutting down %s", settings.app_name)
    await close_rabbitmq()
    await close_redis()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="TelePortal Usage Service",
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(health_router)

Instrumentator().instrument(app).expose(app)
