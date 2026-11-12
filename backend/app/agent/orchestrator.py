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
        self._planner = Planner(llm)
        self._executor = Executor(llm, registry=self._registry)
        self._reporter = Reporter(llm)

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
            final_tool_limit = min(
                settings.max_tool_calls_per_task,
                settings.max_tool_calls_per_run,
            )
            parallel_tool_budget = RunToolBudget(
                settings.max_tool_calls_per_run - final_tool_limit
            )
            final_tool_budget = RunToolBudget(final_tool_limit)
            run_seen_urls: set[str] = set()
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
                        run_seen_urls=run_seen_urls,
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

                completed_results.append({
                    "title": task.title,
                    "result": result,
                })
                all_sources.extend(task_sources)

            await session.commit()

            # ── Phase 4: Final research pass with full context ───
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
                title="Final Research and Synthesis",
                description=(
                    "Review all parallel task findings and gathered sources against the original goal. "
                    "Identify contradictions or gaps, use web search or extraction to verify important "
                    "claims and fill missing information, then produce a complete evidence-based synthesis."
                ),
                order_index=len(tasks),
                status=TaskStatus.PENDING,
            )
            session.add(final_task)
            await session.commit()
            await session.refresh(final_task)

            final_context = list(completed_results)
            if all_sources:
                source_lines = []
                for source in all_sources:
                    url = source.get("url", "")
                    title = source.get("title") or url or "Untitled source"
                    excerpt = (
                        source.get("extracted_content")
                        or source.get("snippet")
                        or ""
                    )
                    source_lines.append(
                        f"- [{title}]({url}) {excerpt[:500]}"
                    )
                final_context.append({
                    "title": "Sources gathered by parallel tasks",
                    "result": "\n".join(source_lines),
                })
            if failed_tasks:
                final_context.append({
                    "title": "Parallel tasks that failed",
                    "result": "\n".join(
                        f"- {item['title']}: {item['error']}"
                        for item in failed_tasks
                    ),
                })

            try:
                final_result, final_sources, _final_tools_used = (
                    await self._executor.execute_task(
                        task=final_task,
                        goal=run.goal,
                        previous_results=final_context,
                        session=session,
                        session_lock=session_lock,
                        tool_budget=final_tool_budget,
                        run_seen_urls=run_seen_urls,
                    )
                )
                all_sources.extend(final_sources)
                if final_task.status == TaskStatus.FAILED:
                    failed_tasks.append({
                        "title": final_task.title,
                        "error": final_task.error_message or "Final research pass failed",
                    })
                else:
                    completed_results.append({
                        "title": final_task.title,
                        "result": final_result,
                    })
            except Exception as e:
                logger.error("Final research pass failed: %s", str(e))
                final_task.status = TaskStatus.FAILED
                final_task.error_message = str(e)
                final_task.completed_at = datetime.now(timezone.utc)
                session.add(final_task)
                failed_tasks.append({
                    "title": final_task.title,
                    "error": final_task.error_message,
                })

            run_total_tools = (
                parallel_tool_budget.used_calls + final_tool_budget.used_calls
            )
            await session.commit()

            # ── Phase 5: Report generation with citations ─────────
            report = await self._reporter.generate_report(
                goal=run.goal,
                task_results=completed_results,
                sources=all_sources,
                failed_tasks=failed_tasks if failed_tasks else None,
            )

            # ── Phase 6: Finalize run record ──────────────────────
            run.final_report = report
            if failed_tasks:
                run.status = RunStatus.FAILED
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
                run_total_tools,
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
