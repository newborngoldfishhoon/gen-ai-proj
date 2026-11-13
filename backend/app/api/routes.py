"""API routes for agent runs, tools, and research sources."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from playwright.async_api import Error as PlaywrightError

from app.db.session import get_db, get_session_factory
from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus, ToolCall, Source
from app.schemas.agent import (
    ErrorResponse,
    PdfExportRequest,
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
from app.core.config import get_settings
from app.services.pdf_export import render_report_pdf

logger = logging.getLogger("agentforge.api")

router = APIRouter(prefix="/api", tags=["agent"])


async def recover_stale_runs() -> int:
    """Fail runs left active after their in-process background worker disappeared."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=settings.agent_run_timeout_seconds * 2)
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(AgentRun)
            .options(selectinload(AgentRun.tasks))
            .where(
                AgentRun.status.in_([RunStatus.PLANNING, RunStatus.RUNNING]),
                AgentRun.updated_at < stale_before,
            )
        )
        stale_runs = result.scalars().all()
        for run in stale_runs:
            run.status = RunStatus.FAILED
            run.error_message = (
                "This run stopped responding before it completed. "
                "Retry the run to start a fresh attempt."
            )
            run.completed_at = now
            session.add(run)
            for task in run.tasks:
                if task.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS}:
                    task.status = TaskStatus.FAILED
                    task.error_message = run.error_message
                    task.completed_at = now
                    session.add(task)
        if stale_runs:
            await session.commit()
            logger.warning("Recovered %d stale agent run(s)", len(stale_runs))
        return len(stale_runs)


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


@router.post(
    "/runs/{run_id}/retry",
    response_model=RunCreatedResponse,
    status_code=201,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    summary="Retry a failed agent run",
    description="Start a fresh run using the original goal.",
)
async def retry_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Create a fresh run for a failed goal without altering its previous attempt."""
    result = await session.execute(
        select(AgentRun).where(AgentRun.id == run_id)
    )
    previous_run = result.scalar_one_or_none()
    if previous_run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if previous_run.status != RunStatus.FAILED:
        raise HTTPException(
            status_code=409,
            detail="Only failed runs can be retried.",
        )

    retry = AgentRun(goal=previous_run.goal, status=RunStatus.PLANNING)
    session.add(retry)
    await session.commit()
    await session.refresh(retry)

    asyncio.create_task(_execute_run_background(retry.id, retry.goal))
    return RunCreatedResponse(
        id=retry.id,
        status=retry.status.value,
        message="Retry started as a new run",
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
            settings = get_settings()
            await asyncio.wait_for(
                orchestrator.run_agent(run, session),
                timeout=settings.agent_run_timeout_seconds,
            )
        except asyncio.TimeoutError:
            timeout_seconds = get_settings().agent_run_timeout_seconds
            logger.error(
                "Run %s exceeded its %d-second execution deadline",
                run_id,
                timeout_seconds,
            )
            await session.rollback()
            result = await session.execute(
                select(AgentRun)
                .options(selectinload(AgentRun.tasks))
                .where(AgentRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run is not None:
                run.status = RunStatus.FAILED
                run.error_message = (
                    f"Run exceeded the {timeout_seconds}-second time limit. "
                    "Try a shorter goal or retry."
                )
                run.completed_at = datetime.now(timezone.utc)
                for task in run.tasks:
                    if task.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS}:
                        task.status = TaskStatus.FAILED
                        task.error_message = run.error_message
                        task.completed_at = run.completed_at
                        session.add(task)
                session.add(run)
                await session.commit()

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

    task_counts = (
        select(
            AgentTask.run_id.label("run_id"),
            func.count(AgentTask.id).label("task_count"),
            func.count(AgentTask.id)
            .filter(AgentTask.status == TaskStatus.COMPLETED)
            .label("completed_task_count"),
        )
        .group_by(AgentTask.run_id)
        .subquery()
    )
    tool_counts = (
        select(
            ToolCall.run_id.label("run_id"),
            func.count(ToolCall.id).label("tool_call_count"),
        )
        .group_by(ToolCall.run_id)
        .subquery()
    )
    source_counts = (
        select(
            Source.run_id.label("run_id"),
            func.count(Source.id).label("source_count"),
        )
        .group_by(Source.run_id)
        .subquery()
    )
    result = await session.execute(
        select(
            AgentRun.id,
            AgentRun.goal,
            AgentRun.status,
            AgentRun.created_at,
            AgentRun.updated_at,
            AgentRun.completed_at,
            func.coalesce(task_counts.c.task_count, 0).label("task_count"),
            func.coalesce(
                task_counts.c.completed_task_count, 0
            ).label("completed_task_count"),
            func.coalesce(tool_counts.c.tool_call_count, 0).label(
                "tool_call_count"
            ),
            func.coalesce(source_counts.c.source_count, 0).label("source_count"),
        )
        .outerjoin(task_counts, task_counts.c.run_id == AgentRun.id)
        .outerjoin(tool_counts, tool_counts.c.run_id == AgentRun.id)
        .outerjoin(source_counts, source_counts.c.run_id == AgentRun.id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        RunListItem(
            id=run.id,
            goal=run.goal,
            status=run.status.value,
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
            task_count=run.task_count,
            completed_task_count=run.completed_task_count,
            tool_call_count=run.tool_call_count,
            source_count=run.source_count,
        )
        for run in result.all()
    ]

    return RunListResponse(runs=items, total=total)


@router.post(
    "/runs/{run_id}/pdf",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Export a completed report as PDF",
    description="Render the browser-styled report using Chromium's print engine.",
)
async def export_run_pdf(
    run_id: UUID,
    request: PdfExportRequest,
    session: AsyncSession = Depends(get_db),
):
    """Render the report's existing browser markup to an A4 PDF."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status != RunStatus.COMPLETED or not run.final_report:
        raise HTTPException(
            status_code=409,
            detail="Only completed runs with a final report can be exported.",
        )

    try:
        pdf = await render_report_pdf(request.html)
    except PlaywrightError as error:
        logger.exception("PDF rendering failed for run %s", run_id)
        raise HTTPException(
            status_code=503,
            detail="PDF rendering failed. Check that the backend Chromium installation is available.",
        ) from error

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="agentforge-report-{run_id}.pdf"'
        },
    )


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
