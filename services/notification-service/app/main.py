import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.consumers import (
    close_rabbitmq,
    connect_rabbitmq,
    consume_billing_events,
    consume_subscriber_events,
    consume_usage_events,
)
from app.database import Base, engine
from app.routes import router
from app.seed import seed_notifications

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_consumer_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    await seed_notifications()
    await connect_rabbitmq()

    # Start RabbitMQ consumers as background tasks
    _consumer_tasks.extend([
        asyncio.create_task(
            consume_subscriber_events(), name="consumer-subscriber"
        ),
        asyncio.create_task(
            consume_usage_events(), name="consumer-usage"
        ),
        asyncio.create_task(
            consume_billing_events(), name="consumer-billing"
        ),
    ])
    logger.info("Started %d consumer tasks", len(_consumer_tasks))

    yield

    # Shutdown
    for task in _consumer_tasks:
        task.cancel()
    if _consumer_tasks:
        await asyncio.gather(*_consumer_tasks, return_exceptions=True)
        logger.info("Consumer tasks cancelled")
    _consumer_tasks.clear()

    await close_rabbitmq()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="TelePortal Notification Service",
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)

Instrumentator().instrument(app).expose(app)
