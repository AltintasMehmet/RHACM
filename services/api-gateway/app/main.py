import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .config import settings
from .health import router as health_router
from .middleware import RequestIDMiddleware
from .routes import router as proxy_router

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Gateway starting — routing to backend services")
    yield
    logger.info("API Gateway shutting down")


app = FastAPI(
    title="TelePortal API Gateway",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(proxy_router)

Instrumentator().instrument(app).expose(app)


@app.get("/")
async def root():
    return {
        "application": "TelePortal API Gateway",
        "version": settings.app_version,
        "routes": {
            "/api/v1/subscribers/*": "Subscriber management",
            "/api/v1/plans/*": "Telecom plan management",
            "/api/v1/usage/*": "Usage tracking",
            "/api/v1/billing/*": "Billing and invoicing",
            "/api/v1/notifications/*": "Notification history",
            "/api/v1/network/*": "Network status monitoring",
        },
    }
