"""API routes for agent runs, tools, and research sources."""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db, get_session_factory
from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus, ToolCall, Source
from app.schemas.agent import (
    ErrorResponse,
    RunCreateRequest,
    RunCreatedResponse,
    RunListItem,
    RunListResponse,
    RunResponse,
    ToolCallResponse,
    SourceResponse,
)
from app.services.llm_provider import create_llm_provider
from app.agent.orchestrator import Orchestrator

logger = logging.getLogger("agentforge.api")

router = APIRouter(prefix="/api", tags=["agent"])


@router.post(
    "/runs",
    response_model=RunCreatedResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create a new agent run",
    description="Submit a goal and start autonomous agent execution with planning and tool use.",
)
async def create_run(
    request: RunCreateRequest,
    session: AsyncSession = Depends(get_db),
):
    """Create a new agent run and start background execution."""
    goal = request.goal.strip()

    # Create the run record
    run = AgentRun(goal=goal, status=RunStatus.PLANNING)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    run_id = run.id
    logger.info("Created run %s for goal: %.100s...", run_id, goal)

    # Start background execution
    # NOTE: In-process background task — can be interrupted by backend restart.
    asyncio.create_task(_execute_run_background(run_id, goal))

    return RunCreatedResponse(
        id=run_id,
        status=run.status.value,
        message="Agent run started",
    )


async def _execute_run_background(run_id: UUID, goal: str) -> None:
    """Execute an agent run in the background with isolated database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            result = await session.execute(
                select(AgentRun).where(AgentRun.id == run_id)
            )
            run = result.scalar_one_or_none()

            if run is None:
                logger.error("Run %s not found for background execution", run_id)
                return

            llm = create_llm_provider()
            orchestrator = Orchestrator(llm)
            await orchestrator.run_agent(run, session)

        except Exception as e:
            logger.exception("Background execution failed for run %s: %s", run_id, str(e))
            try:
                run.status = RunStatus.FAILED
                run.error_message = f"Background execution error: {str(e)}"
                session.add(run)
                await session.commit()
            except Exception:
                logger.exception("Failed to save error state for run %s", run_id)


@router.get(
    "/runs",
    response_model=RunListResponse,
    summary="List recent agent runs",
    description="Returns recent runs with summary metadata. Supports pagination.",
)
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100, description="Max runs to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
):
    """List recent agent runs with summary metadata."""
    count_result = await session.execute(select(func.count(AgentRun.id)))
    total = count_result.scalar() or 0

    result = await session.execute(
        select(AgentRun)
        .options(
            selectinload(AgentRun.tasks),
            selectinload(AgentRun.tool_calls),
            selectinload(AgentRun.sources),
        )
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = result.scalars().all()

    items = []
    for run in runs:
        task_count = len(run.tasks)
        completed_count = sum(
            1 for t in run.tasks if t.status == TaskStatus.COMPLETED
        )
        items.append(
            RunListItem(
                id=run.id,
                goal=run.goal,
                status=run.status.value,
                created_at=run.created_at,
                updated_at=run.updated_at,
                completed_at=run.completed_at,
                task_count=task_count,
                completed_task_count=completed_count,
                tool_call_count=len(run.tool_calls),
                source_count=len(run.sources),
            )
        )

    return RunListResponse(runs=items, total=total)


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get run details",
    description="Returns full run details including tasks, tool calls, sources, and final report.",
)
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Get full details of a specific agent run."""
    result = await session.execute(
        select(AgentRun)
        .options(
            selectinload(AgentRun.tasks).selectinload(AgentTask.tool_calls),
            selectinload(AgentRun.tool_calls),
            selectinload(AgentRun.sources),
        )
        .where(AgentRun.id == run_id)
    )
    run = result.scalar_one_or_none()

    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return RunResponse.model_validate(run)


@router.get(
    "/runs/{run_id}/tools",
    response_model=list[ToolCallResponse],
    responses={404: {"model": ErrorResponse}},
    summary="Get run tool calls",
    description="Returns recorded tool calls for a run in chronological order.",
)
async def get_run_tools(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Return all tool calls executed during a run."""
    result = await session.execute(
        select(ToolCall)
        .where(ToolCall.run_id == run_id)
        .order_by(ToolCall.created_at.asc())
    )
    return [ToolCallResponse.model_validate(tc) for tc in result.scalars().all()]


@router.get(
    "/runs/{run_id}/sources",
    response_model=list[SourceResponse],
    responses={404: {"model": ErrorResponse}},
    summary="Get run sources",
    description="Returns research sources discovered during a run.",
)
async def get_run_sources(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Return all sources gathered during a run."""
    result = await session.execute(
        select(Source)
        .where(Source.run_id == run_id)
        .order_by(Source.created_at.asc())
    )
    return [SourceResponse.model_validate(s) for s in result.scalars().all()]
