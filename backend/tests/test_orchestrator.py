"""Tests for the Orchestrator — full workflow integration."""

import pytest
import pytest_asyncio

from app.agent.orchestrator import Orchestrator
from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus
from app.services.llm_provider import MockProvider, LLMProvider


class PlanFailProvider(LLMProvider):
    """Provider that fails during planning."""
    async def generate(self, prompt, *, system_instruction=None):
        raise RuntimeError("Planning failed")

    async def generate_json(self, prompt, *, system_instruction=None):
        raise RuntimeError("Planning failed")

    async def generate_step(self, messages, tools, *, system_instruction=None):
        raise RuntimeError("Planning failed")


@pytest.mark.asyncio
async def test_full_orchestration_success(mock_llm, db_session):
    """Test the complete orchestration workflow."""
    run = AgentRun(goal="Research best practices for Python testing", status=RunStatus.PLANNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    orchestrator = Orchestrator(mock_llm)
    await orchestrator.run_agent(run, db_session)

    # Refresh from DB
    await db_session.refresh(run)

    assert run.status == RunStatus.COMPLETED
    assert run.final_report is not None
    assert len(run.final_report) > 0
    assert run.completed_at is not None
    assert run.error_message is None

    # Check tasks
    tasks = run.tasks
    assert len(tasks) >= 1
    for task in tasks:
        assert task.status == TaskStatus.COMPLETED
        assert task.result is not None


@pytest.mark.asyncio
async def test_orchestration_planning_failure(db_session):
    """Test that planning failure is handled gracefully."""
    run = AgentRun(goal="This will fail during planning", status=RunStatus.PLANNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    orchestrator = Orchestrator(PlanFailProvider())
    await orchestrator.run_agent(run, db_session)

    await db_session.refresh(run)
    assert run.status == RunStatus.FAILED
    assert run.error_message is not None


@pytest.mark.asyncio
async def test_task_ordering(mock_llm, db_session):
    """Test that tasks are created with correct ordering."""
    run = AgentRun(goal="Multi-step analysis", status=RunStatus.PLANNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    orchestrator = Orchestrator(mock_llm)
    await orchestrator.run_agent(run, db_session)

    await db_session.refresh(run)
    tasks = sorted(run.tasks, key=lambda t: t.order_index)

    for i, task in enumerate(tasks):
        assert task.order_index == i


@pytest.mark.asyncio
async def test_run_persistence(mock_llm, db_session):
    """Test that run data persists correctly."""
    goal = "Persistent test goal"
    run = AgentRun(goal=goal, status=RunStatus.PLANNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    run_id = run.id

    orchestrator = Orchestrator(mock_llm)
    await orchestrator.run_agent(run, db_session)

    # Re-fetch from DB
    from sqlalchemy import select
    result = await db_session.execute(
        select(AgentRun).where(AgentRun.id == run_id)
    )
    fetched = result.scalar_one()

    assert fetched.goal == goal
    assert fetched.status == RunStatus.COMPLETED
    assert fetched.final_report is not None
