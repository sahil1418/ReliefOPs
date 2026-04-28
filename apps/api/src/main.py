from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.errors import (
    ApiError,
    ApiResponse,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from src.core.firebase import init_firebase
from src.core.logging import configure_logging, get_logger
from src.modules.admin.router import router as admin_router
from src.modules.ai.router import router as ai_router
from src.modules.ai_copilot.router import router as copilot_router
from src.modules.analytics.router import router as analytics_router
from src.modules.auth.router import router as auth_router
from src.modules.disasters.router import router as disasters_router
from src.modules.inventory.router import router as inventory_router
from src.modules.notifications.router import router as notifications_router
from src.modules.predictions.router import router as predictions_router
from src.modules.requests.router import router as requests_router
from src.modules.routing.router import router as routing_router
from src.modules.shipments.router import router as shipments_router
from src.modules.tracking.router import router as tracking_router

settings = get_settings()
configure_logging(settings.env)
log = get_logger("relief.api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    log.info(
        "api.startup",
        env=settings.env,
        project=settings.gcp_project_id,
        region=settings.gcp_region,
        emulators=settings.use_emulators,
    )
    init_firebase()
    yield
    log.info("api.shutdown")


app = FastAPI(
    title="ReliefOps API",
    version="0.1.0",
    description="AI-powered humanitarian disaster logistics — modular monolith on Cloud Run.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


class HealthPayload(ApiResponse[dict[str, str]]):
    pass


@app.get("/health", response_model=HealthPayload, tags=["meta"])
async def health() -> HealthPayload:
    """Liveness probe consumed by Cloud Run + GitHub Actions smoke tests."""
    return HealthPayload(
        data={
            "status": "ok",
            "env": settings.env,
            "service": "relief-api",
            "version": app.version,
        }
    )


@app.get("/", tags=["meta"])
async def root() -> ApiResponse[dict[str, str]]:
    return ApiResponse(
        data={
            "name": "ReliefOps API",
            "docs": "/docs",
            "health": "/health",
        }
    )


app.include_router(auth_router)
app.include_router(shipments_router)
app.include_router(analytics_router)
app.include_router(disasters_router)
app.include_router(requests_router)
app.include_router(routing_router)
app.include_router(inventory_router)
app.include_router(tracking_router)
app.include_router(predictions_router)
app.include_router(copilot_router)
app.include_router(notifications_router)
app.include_router(admin_router)
app.include_router(ai_router)
