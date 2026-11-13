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
        ac.test_session_factory = factory
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
async def test_export_completed_run_as_pdf(client, monkeypatch):
    import app.api.routes as routes
    from uuid import UUID
    from app.models.agent import AgentRun, RunStatus

    async def render_pdf(html):
        assert "<h1>Research Report</h1>" in html
        return b"%PDF-1.7 test document"

    async def skip_background(_run_id, _goal):
        return None

    monkeypatch.setattr(routes, "render_report_pdf", render_pdf)
    monkeypatch.setattr(routes, "_execute_run_background", skip_background)
    created = await client.post("/api/runs", json={"goal": "PDF export test"})
    run_id = created.json()["id"]
    async with client.test_session_factory() as session:
        run = await session.get(AgentRun, UUID(run_id))
        assert run is not None
        run.status = RunStatus.COMPLETED
        run.final_report = "# Research Report\n\nTest content."
        await session.commit()

    response = await client.post(
        f"/api/runs/{run_id}/pdf",
        json={"html": "<h1>Research Report</h1>"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].endswith(f'{run_id}.pdf"')
    assert response.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_export_pdf_requires_completed_report(client, monkeypatch):
    import app.api.routes as routes

    async def skip_background(_run_id, _goal):
        return None

    monkeypatch.setattr(routes, "_execute_run_background", skip_background)
    created = await client.post("/api/runs", json={"goal": "PDF export state test"})

    response = await client.post(
        f"/api/runs/{created.json()['id']}/pdf",
        json={"html": "<h1>Research Report</h1>"},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_run_not_found(client):
    """Test 404 for unknown run ID."""
    import uuid
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/runs/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_failed_run_creates_new_run_with_same_goal(client, monkeypatch):
    """Retry starts a new attempt and leaves the failed run unchanged."""
    import app.api.routes as routes
    from uuid import UUID
    from app.models.agent import AgentRun, RunStatus

    async def skip_background(_run_id, _goal):
        return None

    monkeypatch.setattr(routes, "_execute_run_background", skip_background)
    created = await client.post("/api/runs", json={"goal": "Research retry behavior"})
    assert created.status_code == 201
    original_id = created.json()["id"]

    async with client.test_session_factory() as session:
        original = await session.get(AgentRun, UUID(original_id))
        assert original is not None
        original.status = RunStatus.FAILED
        original.error_message = "The AI provider is rate-limited (HTTP 429)."
        await session.commit()

    retried = await client.post(f"/api/runs/{original_id}/retry")

    assert retried.status_code == 201
    assert retried.json()["id"] != original_id
    assert retried.json()["status"] == "planning"

    details = await client.get(f"/api/runs/{retried.json()['id']}")
    assert details.status_code == 200
    assert details.json()["goal"] == "Research retry behavior"


@pytest.mark.asyncio
async def test_retry_rejects_non_failed_run(client):
    created = await client.post("/api/runs", json={"goal": "Do not retry active run"})
    retried = await client.post(f"/api/runs/{created.json()['id']}/retry")

    assert retried.status_code == 409
    assert retried.json()["detail"] == "Only failed runs can be retried."


@pytest.mark.asyncio
async def test_recover_stale_runs_marks_abandoned_work_failed(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from uuid import UUID
    from sqlalchemy import select
    import app.api.routes as routes
    from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus

    monkeypatch.setattr(routes, "get_session_factory", lambda: client.test_session_factory)
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: type("Settings", (), {"agent_run_timeout_seconds": 35})(),
    )

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    async with client.test_session_factory() as session:
        run = AgentRun(
            goal="Recover abandoned run",
            status=RunStatus.RUNNING,
            created_at=stale_time,
            updated_at=stale_time,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id
        task = AgentTask(
            run_id=run_id,
            title="Pending task",
            description="A task interrupted by restart",
            order_index=0,
            status=TaskStatus.IN_PROGRESS,
            created_at=stale_time,
            updated_at=stale_time,
        )
        session.add(task)
        await session.commit()

    recovered_count = await routes.recover_stale_runs()

    async with client.test_session_factory() as session:
        recovered = await session.get(AgentRun, run_id)
        assert recovered is not None
        assert recovered.status == RunStatus.FAILED
        assert "Retry the run" in recovered.error_message
        assert recovered.completed_at is not None
        tasks = await session.execute(
            select(AgentTask).where(AgentTask.run_id == run_id)
        )
        assert tasks.scalar_one().status == TaskStatus.FAILED
    assert recovered_count == 1


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
