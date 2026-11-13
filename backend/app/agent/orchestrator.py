"""Orchestrator — coordinates the full agent workflow with tool use and evidence tracking.

Manages: planning → task creation → iterative execution (with tools) → citation-backed report.
Keeps workflow logic cleanly separated from HTTP route handlers.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus
from app.services.llm_provider import LLMProvider
from app.agent.planner import Planner
from app.agent.executor import Executor, RunToolBudget
from app.agent.reporter import Reporter
from app.tools.registry import ToolRegistry, create_default_registry

logger = logging.getLogger("agentforge.orchestrator")


class Orchestrator:
    """Coordinates the full agent execution workflow with tools and evidence tracking."""

    def __init__(self, llm: LLMProvider, registry: ToolRegistry | None = None):
        self._registry = registry or create_default_registry()
        self._planner = Planner()
        self._executor = Executor(llm, registry=self._registry)
        self._reporter = Reporter()

    async def run_agent(self, run: AgentRun, session: AsyncSession) -> None:
        """Execute the complete agent workflow for a given run.

        This method handles all state transitions, tool coordination,
        evidence collection, and database persistence.
        """
        try:
            # ── Phase 1: Planning ─────────────────────────────────
            logger.info("Starting agent run %s for goal: %.100s...", run.id, run.goal)
            run.status = RunStatus.PLANNING
            session.add(run)
            await session.commit()

            plan = await self._planner.create_plan(run.goal)

            # ── Phase 2: Create tasks in DB ───────────────────────
            tasks = []
            for i, planned_task in enumerate(plan.tasks):
                task = AgentTask(
                    run_id=run.id,
                    title=planned_task.title,
                    description=planned_task.description,
                    order_index=i,
                    status=TaskStatus.PENDING,
                )
                session.add(task)
                tasks.append(task)

            run.status = RunStatus.RUNNING
            session.add(run)
            await session.commit()

            # Refresh tasks to ensure IDs are available
            for task in tasks:
                await session.refresh(task)

            logger.info("Created %d tasks for run %s", len(tasks), run.id)

            # ── Phase 3: Run independent tasks in parallel ───────
            completed_results: list[dict] = []
            failed_tasks: list[dict] = []
            all_sources: list[dict] = []
            settings = get_settings()
            session_lock = asyncio.Lock()
            parallel_tool_budget = RunToolBudget(settings.max_tool_calls_per_run)
            task_semaphore = asyncio.Semaphore(
                min(settings.max_concurrent_tasks, len(tasks))
            )

            async def execute_task(index: int):
                task = tasks[index]
                async with task_semaphore:
                    return await self._executor.execute_task(
                        task=task,
                        goal=run.goal,
                        previous_results=[],
                        session=session,
                        session_lock=session_lock,
                        tool_budget=parallel_tool_budget,
                        fast_mode=True,
                    )

            outcomes = await asyncio.gather(
                *(execute_task(index) for index in range(len(tasks))),
                return_exceptions=True,
            )
            for task, outcome in zip(tasks, outcomes):
                if isinstance(outcome, BaseException):
                    logger.error("Task '%s' failed: %s", task.title, str(outcome))
                    task.status = TaskStatus.FAILED
                    task.error_message = str(outcome)
                    task.completed_at = datetime.now(timezone.utc)
                    session.add(task)
                    failed_tasks.append({
                        "title": task.title,
                        "error": task.error_message,
                    })
                    continue

                result, task_sources, _tools_used = outcome
                if task.status == TaskStatus.FAILED:
                    failed_tasks.append({
                        "title": task.title,
                        "error": task.error_message or "Task execution failed",
                    })
                    continue

                if task.title != "Resource research":
                    completed_results.append({
                        "title": task.title,
                        "result": result,
                    })
                    all_sources.extend(task_sources)

            await session.commit()

            # ── Phase 4: Final report synthesis ──────────────────
            if not completed_results:
                run.status = RunStatus.FAILED
                run.error_message = "All tasks failed. No results to report."
                run.completed_at = datetime.now(timezone.utc)
                session.add(run)
                await session.commit()
                logger.error("Run %s failed: no tasks completed", run.id)
                return

            final_task = AgentTask(
                run_id=run.id,
                title="Final Report",
                description=(
                    "Format the research answer and gathered sources into a structured report."
                ),
                order_index=len(tasks),
                status=TaskStatus.IN_PROGRESS,
                started_at=datetime.now(timezone.utc),
            )
            session.add(final_task)
            await session.commit()
            await session.refresh(final_task)

            # Report generation is the final synthesis step; a separate LLM research pass
            # here would repeat synthesis and add another serial set of model/tool calls.
            report = await self._reporter.generate_report(
                goal=run.goal,
                task_results=completed_results,
                sources=all_sources,
                failed_tasks=failed_tasks if failed_tasks else None,
            )
            final_task.result = report
            final_task.status = TaskStatus.COMPLETED
            final_task.completed_at = datetime.now(timezone.utc)
            session.add(final_task)
            await session.commit()

            # ── Phase 5: Finalize run record ──────────────────────
            run.final_report = report
            if failed_tasks:
                run.status = RunStatus.FAILED
                if any("429" in str(item.get("error", "")) for item in failed_tasks):
                    run.error_message = (
                        "The AI provider is temporarily rate-limited (HTTP 429). "
                        "Wait briefly, then retry this run."
                    )
                else:
                    run.error_message = f"{len(failed_tasks)} task(s) failed during execution"
            else:
                run.status = RunStatus.COMPLETED

            run.completed_at = datetime.now(timezone.utc)
            session.add(run)
            await session.commit()

            logger.info(
                "Run %s finished with status: %s (%d tasks completed, %d tools called, %d sources gathered)",
                run.id,
                run.status.value,
                len(completed_results),
                parallel_tool_budget.used_calls,
                len(all_sources),
            )

        except Exception as e:
            logger.exception("Run %s encountered an unhandled error: %s", run.id, str(e))
            try:
                run.status = RunStatus.FAILED
                run.error_message = f"Agent execution failed: {str(e)}"
                run.completed_at = datetime.now(timezone.utc)
                session.add(run)
                await session.commit()
            except Exception as db_err:
                logger.exception("Failed to persist error state: %s", str(db_err))
