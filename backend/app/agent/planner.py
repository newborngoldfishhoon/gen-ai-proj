"""Planner — converts a user goal into a structured execution plan."""

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings


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


class Planner:
    """Creates focused research and resource tasks without a planning model call."""

    def __init__(self):
        self._settings = get_settings()

    async def create_plan(self, goal: str) -> ExecutionPlan:
        """Create the answer and practical-resource tasks directly from the goal."""
        if not goal or not goal.strip():
            raise ValueError("Goal cannot be empty")

        if len(goal) > self._settings.max_goal_length:
            raise ValueError(
                f"Goal exceeds maximum length of {self._settings.max_goal_length} characters"
            )

        return ExecutionPlan(tasks=[
            PlannedTask(
                title="Research and answer the goal",
                description=goal.strip(),
            ),
            PlannedTask(
                title="Resource research",
                description=(
                    "Find practical resources related to the goal, prioritizing useful "
                    "tutorial videos and courses. For job or career goals, prioritize "
                    "current openings and official application links. Include relevant "
                    "trending or up-to-date resources. Use credible, directly useful links "
                    "and summarize each in 1-2 lines. Do not invent URLs or availability."
                ),
            ),
        ])
