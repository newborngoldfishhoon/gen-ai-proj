"""Test fixtures and configuration for AgentForge tests."""

import asyncio
import os
import sys
from uuid import uuid4

import pytest
import pytest_asyncio

# Force mock providers and test database for deterministic offline tests
os.environ["LLM_PROVIDER"] = "mock"
os.environ["SEARCH_PROVIDER"] = "mock"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_agentforge.db"
os.environ["GEMINI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["ENVIRONMENT"] = "test"

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.agent import AgentRun, AgentTask, ToolCall, Source  # noqa: F401 — register models
from app.services.llm_provider import MockProvider, create_llm_provider
from app.tools.registry import create_default_registry, ToolRegistry


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create a fresh in-memory database session for each test."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def mock_llm():
    """Return a MockProvider instance."""
    return MockProvider()


@pytest.fixture
def tool_registry():
    """Return default configured tool registry with mock search."""
    return create_default_registry()
