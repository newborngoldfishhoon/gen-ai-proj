"""Tests for the API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import create_app


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    # Override database for tests
    import os
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

    # Patch the db session for testing
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.db.base import Base
    from app.models.agent import AgentRun, AgentTask, ToolCall, Source  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app = create_app()

    # Override the get_db dependency
    from app.db.session import get_db

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    # Also patch get_session_factory for background tasks
    import app.db.session as session_module
    original_factory = session_module.get_session_factory
    session_module.get_session_factory = lambda: factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    session_module.get_session_factory = original_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_check(client):
    """Test the health endpoint."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "agentforge"


@pytest.mark.asyncio
async def test_create_run(client):
    """Test creating a new run."""
    response = await client.post(
        "/api/runs",
        json={"goal": "Test the agent system"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "planning"


@pytest.mark.asyncio
async def test_create_run_empty_goal(client):
    """Test that empty goals are rejected."""
    response = await client.post("/api/runs", json={"goal": ""})
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_create_run_missing_goal(client):
    """Test that missing goal field is rejected."""
    response = await client.post("/api/runs", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_runs_empty(client):
    """Test listing runs when none exist."""
    response = await client.get("/api/runs")
    assert response.status_code == 200
    data = response.json()
    assert data["runs"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_run_not_found(client):
    """Test 404 for unknown run ID."""
    import uuid
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/runs/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_and_list_run(client):
    """Test creating a run and finding it in the list."""
    # Create
    create_response = await client.post(
        "/api/runs",
        json={"goal": "Analyze Python trends"},
    )
    assert create_response.status_code == 201
    run_id = create_response.json()["id"]

    # Small delay for background task to start
    import asyncio
    await asyncio.sleep(0.5)

    # List
    list_response = await client.get("/api/runs")
    assert list_response.status_code == 200
    data = list_response.json()
    assert data["total"] >= 1
    assert any(r["id"] == run_id for r in data["runs"])


@pytest.mark.asyncio
async def test_create_and_get_run(client):
    """Test creating a run and fetching its details."""
    # Create
    create_response = await client.post(
        "/api/runs",
        json={"goal": "Test run details"},
    )
    run_id = create_response.json()["id"]

    # Wait for background execution
    import asyncio
    await asyncio.sleep(3)

    # Get details
    detail_response = await client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200
    data = detail_response.json()
    assert data["id"] == run_id
    assert data["goal"] == "Test run details"
    # Status should be completed or still running
    assert data["status"] in ["planning", "running", "completed", "failed"]


@pytest.mark.asyncio
async def test_goal_too_long(client):
    """Test that excessively long goals are rejected."""
    response = await client.post(
        "/api/runs",
        json={"goal": "a" * 2001},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_run_tools_and_sources(client):
    """Test querying /tools and /sources endpoints."""
    create_response = await client.post(
        "/api/runs",
        json={"goal": "Research Python libraries with calculator check"},
    )
    run_id = create_response.json()["id"]

    import asyncio
    await asyncio.sleep(1)

    tools_response = await client.get(f"/api/runs/{run_id}/tools")
    assert tools_response.status_code == 200
    assert isinstance(tools_response.json(), list)

    sources_response = await client.get(f"/api/runs/{run_id}/sources")
    assert sources_response.status_code == 200
    assert isinstance(sources_response.json(), list)

