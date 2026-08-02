import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.database import Base, engine
from app.events import close_rabbitmq, connect_rabbitmq
from app.routes import router
from app.seed import seed_subscribers

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    await seed_subscribers()
    await connect_rabbitmq()

    yield

    # Shutdown
    await close_rabbitmq()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="TelePortal Subscriber Service",
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)

Instrumentator().instrument(app).expose(app)
