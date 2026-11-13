"""FastAPI application entry point."""

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import dispose_engine
from app.api.routes import purge_expired_guest_runs, recover_stale_runs, router
from app.schemas.agent import HealthResponse
from app.services.pdf_export import close_pdf_browser

logger = logging.getLogger("agentforge")


async def _guest_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            deleted = await purge_expired_guest_runs()
            if deleted:
                logger.info("Deleted %d expired guest run(s)", deleted)
        except Exception:
            logger.exception("Could not purge expired guest runs")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    setup_logging()
    settings = get_settings()
    logger.info("AgentForge starting — environment: %s", settings.environment)
    logger.info("LLM provider: %s", settings.llm_provider)
    await recover_stale_runs()
    cleanup_task = asyncio.create_task(_guest_cleanup_loop())
    yield
    logger.info("AgentForge shutting down")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await close_pdf_browser()
    await dispose_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AgentForge",
        description="Autonomous AI Agent Platform — Phase 2: Tool Use & Web Research",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health endpoint
    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    async def health_check():
        """Return service health status."""
        return HealthResponse()

    # Agent routes
    app.include_router(router)

    return app


app = create_app()
