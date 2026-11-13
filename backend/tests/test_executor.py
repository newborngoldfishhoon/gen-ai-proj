"""Tests for the Executor module."""

import pytest
import pytest_asyncio

from app.agent.executor import Executor, RunToolBudget
from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus
from app.services.llm_provider import LLMProvider, LLMStepResponse, MockProvider


class FailingProvider(LLMProvider):
    """Provider that always fails."""

    async def generate(self, prompt, *, system_instruction=None):
        raise RuntimeError("LLM unavailable")

    async def generate_json(self, prompt, *, system_instruction=None):
        raise RuntimeError("LLM unavailable")

    async def generate_step(self, messages, tools, *, system_instruction=None):
        raise RuntimeError("LLM unavailable")


class CountingMockProvider(MockProvider):
    def __init__(self):
        super().__init__()
        self.step_calls = 0

    async def generate_step(self, messages, tools, *, system_instruction=None):
        self.step_calls += 1
        return LLMStepResponse(
            is_tool_call=False,
            content="One-call answer grounded in the search result.",
        )


@pytest.mark.asyncio
async def test_execute_task_success(mock_llm, db_session):
    """Test successful task execution."""
    run = AgentRun(goal="Test goal", status=RunStatus.RUNNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    task = AgentTask(
        run_id=run.id,
        title="Test Task",
        description="Do something useful",
        order_index=0,
        status=TaskStatus.PENDING,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    executor = Executor(mock_llm)
    result, sources, tools_count = await executor.execute_task(task, "Test goal", [], db_session)

    assert result
    assert task.status == TaskStatus.COMPLETED
    assert task.result is not None
    assert task.started_at is not None
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_fast_mode_searches_without_spending_an_llm_tool_selection_call(db_session):
    run = AgentRun(goal="Research Python async best practices", status=RunStatus.RUNNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    task = AgentTask(
        run_id=run.id,
        title="Research goal",
        description=run.goal,
        order_index=0,
        status=TaskStatus.PENDING,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    provider = CountingMockProvider()
    result, sources, tools_used = await Executor(provider).execute_task(
        task=task,
        goal=run.goal,
        previous_results=[],
        session=db_session,
        tool_budget=RunToolBudget(1),
        fast_mode=True,
    )

    assert provider.step_calls == 1
    assert tools_used == 1
    assert sources
    assert "One-call answer" in result


@pytest.mark.asyncio
async def test_execute_task_failure(db_session):
    """Test task execution failure handling."""
    run = AgentRun(goal="Test goal", status=RunStatus.RUNNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    task = AgentTask(
        run_id=run.id,
        title="Failing Task",
        description="This will fail",
        order_index=0,
        status=TaskStatus.PENDING,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    executor = Executor(FailingProvider())
    # Even if LLM fails, executor falls back or captures failure
    result, sources, tools_count = await executor.execute_task(task, "Test goal", [], db_session)
    assert task.status == TaskStatus.COMPLETED or task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_execute_task_with_context(mock_llm, db_session):
    """Test that previous results are passed as context."""
    run = AgentRun(goal="Analyze AI", status=RunStatus.RUNNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    task = AgentTask(
        run_id=run.id,
        title="Build on Previous",
        description="Use previous context",
        order_index=1,
        status=TaskStatus.PENDING,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    previous_results = [
        {"title": "Previous Task", "result": "Some earlier findings"},
    ]

    executor = Executor(mock_llm)
    result, sources, tools_count = await executor.execute_task(task, "Analyze AI", previous_results, db_session)

    assert result
    assert task.status == TaskStatus.COMPLETED
