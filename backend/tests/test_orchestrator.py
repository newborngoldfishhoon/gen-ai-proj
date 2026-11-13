"""Tests for the Orchestrator — full workflow integration."""

import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.agent.orchestrator import Orchestrator
from app.agent.planner import ExecutionPlan
from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus
from app.services.llm_provider import MockProvider, LLMProvider


class FailingProvider(LLMProvider):
    """Provider that fails during task execution."""
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
    assert len(tasks) >= 3
    for task in tasks:
        assert task.status == TaskStatus.COMPLETED
        assert task.result is not None
    resource_task = next(task for task in tasks if task.title == "Resource research")
    assert "# Kickstart Resources" in resource_task.result
    assert "Kickstart Resources" not in run.final_report
    from sqlalchemy import select
    from app.models.agent import Source
    resource_sources = await db_session.execute(
        select(Source).where(Source.task_id == resource_task.id)
    )
    assert resource_sources.scalars().all()


@pytest.mark.asyncio
async def test_orchestration_execution_failure(db_session):
    """Test that task execution failures are persisted."""
    run = AgentRun(goal="This will fail during task execution", status=RunStatus.PLANNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    orchestrator = Orchestrator(FailingProvider())
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


@pytest.mark.asyncio
async def test_single_task_is_reported_without_extra_synthesis(
    mock_llm, db_session, monkeypatch
):
    """Run one research task and format the report without another model call."""
    run = AgentRun(goal="Research and compare a topic", status=RunStatus.PLANNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    orchestrator = Orchestrator(mock_llm)
    plan = ExecutionPlan.model_validate({
        "tasks": [
            {"title": "Research goal", "description": "Research independently"}
        ],
    })

    async def create_plan(_goal):
        return plan

    monkeypatch.setattr(orchestrator._planner, "create_plan", create_plan)
    monkeypatch.setattr(
        "app.agent.orchestrator.get_settings",
        lambda: SimpleNamespace(
            max_concurrent_tasks=1,
            max_tool_calls_per_task=1,
            max_tool_calls_per_run=1,
        ),
    )
    active_tasks = 0
    max_active_tasks = 0
    completed_tasks = set()
    report_inputs = []

    async def execute_task(task, goal, previous_results, session, **kwargs):
        nonlocal active_tasks, max_active_tasks
        assert previous_results == []
        active_tasks += 1
        max_active_tasks = max(max_active_tasks, active_tasks)
        await asyncio.sleep(0.03)
        completed_tasks.add(task.title)
        source = {
            "title": f"Source for {task.title}",
            "url": f"https://example.com/{task.order_index}",
            "snippet": f"Evidence for {task.title}",
        }
        tools_used = int(await kwargs["tool_budget"].reserve())

        async with kwargs["session_lock"]:
            task.status = TaskStatus.COMPLETED
            task.result = f"Result for {task.title}"
            session.add(task)
            await session.commit()
        active_tasks -= 1
        return task.result, [source] if source else [], tools_used

    async def generate_report(**kwargs):
        report_inputs.append(kwargs)
        return "# Structured report"

    monkeypatch.setattr(orchestrator._executor, "execute_task", execute_task)
    monkeypatch.setattr(orchestrator._reporter, "generate_report", generate_report)
    await orchestrator.run_agent(run, db_session)
    await db_session.refresh(run)

    assert max_active_tasks == 1
    assert completed_tasks == {"Research goal"}
    assert len(report_inputs) == 1
    assert [item["title"] for item in report_inputs[0]["task_results"]] == [
        "Research goal"
    ]
    assert len(report_inputs[0]["sources"]) == 1
    assert run.tasks[-1].title == "Final Report"
    assert run.tasks[-1].result == run.final_report == "# Structured report"
    assert all(task.status == TaskStatus.COMPLETED for task in run.tasks)
    assert run.status == RunStatus.COMPLETED
