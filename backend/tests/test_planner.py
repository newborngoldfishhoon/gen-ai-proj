"""Tests for the Planner module."""

import pytest

from app.agent.planner import Planner, ExecutionPlan


@pytest.mark.asyncio
async def test_create_plan_uses_one_fast_task_without_calling_llm():
    """A fast plan must not spend an LLM request planning work."""
    planner = Planner()
    plan = await planner.create_plan("Research AI trends")

    assert isinstance(plan, ExecutionPlan)
    assert len(plan.tasks) == 1
    assert plan.tasks[0].description == "Research AI trends"
    for task in plan.tasks:
        assert task.title
        assert task.description


@pytest.mark.asyncio
async def test_create_plan_empty_goal():
    """Test that empty goals are rejected."""
    planner = Planner()

    with pytest.raises(ValueError, match="empty"):
        await planner.create_plan("")

    with pytest.raises(ValueError, match="empty"):
        await planner.create_plan("   ")


@pytest.mark.asyncio
async def test_create_plan_too_long_goal():
    """Test that excessively long goals are rejected."""
    planner = Planner()
    long_goal = "a" * 3000

    with pytest.raises(ValueError, match="maximum length"):
        await planner.create_plan(long_goal)
