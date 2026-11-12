"""Integration tests for the agentic tool-calling loop, ToolCall/Source persistence, and citations."""

import pytest
from sqlalchemy import select

from app.agent.orchestrator import Orchestrator
from app.agent.executor import Executor
from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus, ToolCall, Source, ToolCallStatus
from app.services.llm_provider import MockProvider
from app.tools.registry import create_default_registry


@pytest.mark.asyncio
async def test_agentic_tool_loop_in_executor(db_session, tool_registry):
    """Test that the executor runs iterative tool calls, records ToolCalls, and saves Sources."""
    run = AgentRun(
        goal="Research software engineering internships for BTech students with Python",
        status=RunStatus.RUNNING,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    task = AgentTask(
        run_id=run.id,
        title="Find Python Internships via Web Search",
        description="Search for live internships and extract verified requirements.",
        order_index=0,
        status=TaskStatus.PENDING,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    mock_llm = MockProvider()
    executor = Executor(mock_llm, registry=tool_registry)

    result, new_sources, tools_used = await executor.execute_task(
        task=task,
        goal=run.goal,
        previous_results=[],
        session=db_session,
    )

    # 1. Verification of task outcome
    assert task.status == TaskStatus.COMPLETED
    assert task.result is not None
    assert len(task.result) > 0
    assert tools_used >= 1

    # 2. Verification of persisted ToolCall records
    tool_calls_res = await db_session.execute(
        select(ToolCall).where(ToolCall.task_id == task.id)
    )
    tool_calls = tool_calls_res.scalars().all()
    assert len(tool_calls) >= 1

    first_tc = tool_calls[0]
    assert first_tc.tool_name == "web_search"
    assert first_tc.status == ToolCallStatus.COMPLETED
    assert first_tc.result_summary is not None

    # 3. Verification of persisted Source records
    sources_res = await db_session.execute(
        select(Source).where(Source.run_id == run.id)
    )
    sources = sources_res.scalars().all()
    assert len(sources) >= 1
    assert any(s.url.startswith("https://") for s in sources)


@pytest.mark.asyncio
async def test_full_orchestration_with_tools_and_citations(db_session):
    """Test the complete Phase 2 workflow: planning, multi-step tool execution, source tracking, and report citations."""
    goal = "Research five software engineering internships for 2nd-year BTech student with Python skills"
    run = AgentRun(goal=goal, status=RunStatus.PLANNING)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    mock_llm = MockProvider()
    orchestrator = Orchestrator(mock_llm)
    await orchestrator.run_agent(run, db_session)

    # Refresh run from DB
    await db_session.refresh(run)

    assert run.status == RunStatus.COMPLETED
    assert run.final_report is not None
    assert "## Sources & Citations" in run.final_report

    # Ensure report contains markdown links to actual retrieved sources
    assert "https://" in run.final_report

    # Verify ToolCall records exist in database for this run
    tc_res = await db_session.execute(
        select(ToolCall).where(ToolCall.run_id == run.id)
    )
    persisted_tool_calls = tc_res.scalars().all()
    assert len(persisted_tool_calls) >= 1

    # Verify Source records exist in database for this run
    src_res = await db_session.execute(
        select(Source).where(Source.run_id == run.id)
    )
    persisted_sources = src_res.scalars().all()
    assert len(persisted_sources) >= 1
