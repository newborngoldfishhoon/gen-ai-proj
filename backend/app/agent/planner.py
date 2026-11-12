"""Planner — converts a user goal into a structured execution plan."""

import logging
from pydantic import BaseModel, Field, field_validator

from app.services.llm_provider import LLMProvider
from app.core.config import get_settings

logger = logging.getLogger("agentforge.planner")


class PlannedTask(BaseModel):
    """A single task in the execution plan."""
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field(..., min_length=1, max_length=2000)


class ExecutionPlan(BaseModel):
    """Validated execution plan from the LLM."""
    tasks: list[PlannedTask] = Field(..., min_length=1)

    @field_validator("tasks")
    @classmethod
    def validate_task_count(cls, v):
        settings = get_settings()
        if len(v) > settings.max_tasks:
            raise ValueError(f"Plan exceeds maximum of {settings.max_tasks} tasks (got {len(v)})")
        if len(v) == 0:
            raise ValueError("Plan must contain at least one task")
        return v


PLANNING_SYSTEM_PROMPT = """You are a task planning AI for AgentForge. Your job is to break down a user's goal into a structured execution plan.

IMPORTANT CONSTRAINTS:
- Create 3-6 focused, self-contained tasks that can run independently and concurrently.
- Do not make a task rely on another planned task's results.
- Do not include a final synthesis task; a separate final research and synthesis pass runs after all tasks finish.
- Tasks may use the tools provided during execution to gather evidence.
- Tasks should be logical steps that contribute to addressing the user's goal.
- Each task needs a clear title and description.

Return your plan as a JSON object with this exact structure:
{
  "tasks": [
    {"title": "Task Title", "description": "What this independent task should accomplish"},
    ...
  ]
}

Return ONLY the JSON object, no other text."""


class Planner:
    """Generates structured execution plans from user goals."""

    def __init__(self, llm: LLMProvider):
        self._llm = llm
        self._settings = get_settings()

    async def create_plan(self, goal: str) -> ExecutionPlan:
        """Create a validated execution plan for the given goal.

        Uses bounded retries for malformed LLM output.
        Raises ValueError if the plan cannot be generated after retries.
        """
        if not goal or not goal.strip():
            raise ValueError("Goal cannot be empty")

        if len(goal) > self._settings.max_goal_length:
            raise ValueError(
                f"Goal exceeds maximum length of {self._settings.max_goal_length} characters"
            )

        last_error = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                logger.info("Planning attempt %d for goal: %.100s...", attempt, goal)

                prompt = f"Create an execution plan for this goal:\n\n{goal}"
                raw = await self._llm.generate_json(
                    prompt,
                    system_instruction=PLANNING_SYSTEM_PROMPT,
                )

                plan = ExecutionPlan.model_validate(raw)
                logger.info("Plan created with %d tasks", len(plan.tasks))
                return plan

            except Exception as e:
                last_error = e
                logger.warning(
                    "Planning attempt %d failed: %s", attempt, str(e)
                )

        raise ValueError(
            f"Failed to generate a valid plan after {self._settings.max_retries} attempts: {last_error}"
        )
