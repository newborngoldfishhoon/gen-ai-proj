"""Orchestrator — coordinates the full agent workflow with tool use and evidence tracking.

Manages: planning → task creation → iterative execution (with tools) → citation-backed report.
Keeps workflow logic cleanly separated from HTTP route handlers.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun, AgentTask, RunStatus, TaskStatus
from app.services.llm_provider import LLMProvider
from app.agent.planner import Planner
from app.agent.executor import Executor
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

            # ── Phase 3: Sequential execution with tool loop ──────
            completed_results: list[dict] = []
            failed_tasks: list[dict] = []
            all_sources: list[dict] = []
            run_total_tools = 0
            execution_failed = False

            for task in tasks:
                if execution_failed:
                    task.status = TaskStatus.FAILED
                    task.error_message = "Skipped due to earlier task failure"
                    session.add(task)
                    failed_tasks.append({
                        "title": task.title,
                        "error": task.error_message,
                    })
                    continue

                try:
                    result, task_sources, tools_used = await self._executor.execute_task(
                        task=task,
                        goal=run.goal,
                        previous_results=completed_results,
                        session=session,
                        run_total_tools=run_total_tools,
                    )
                    run_total_tools += tools_used
                    all_sources.extend(task_sources)
                    completed_results.append({
                        "title": task.title,
                        "result": result,
                    })
                except Exception as e:
                    logger.error("Task '%s' failed: %s", task.title, str(e))
                    failed_tasks.append({
                        "title": task.title,
                        "error": str(e),
                    })
                    execution_failed = True

            await session.commit()

            # ── Phase 4: Report generation with citations ─────────
            if not completed_results:
                run.status = RunStatus.FAILED
                run.error_message = "All tasks failed. No results to report."
                run.completed_at = datetime.now(timezone.utc)
                session.add(run)
                await session.commit()
                logger.error("Run %s failed: no tasks completed", run.id)
                return

            report = await self._reporter.generate_report(
                goal=run.goal,
                task_results=completed_results,
                sources=all_sources,
                failed_tasks=failed_tasks if failed_tasks else None,
            )

            # ── Phase 5: Finalize run record ──────────────────────
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
