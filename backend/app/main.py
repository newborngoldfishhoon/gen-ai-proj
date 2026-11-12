"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import dispose_engine
from app.api.routes import router
from app.schemas.agent import HealthResponse

logger = logging.getLogger("agentforge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    setup_logging()
    settings = get_settings()
    logger.info("AgentForge starting — environment: %s", settings.environment)
    logger.info("LLM provider: %s", settings.llm_provider)
    yield
    logger.info("AgentForge shutting down")
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
