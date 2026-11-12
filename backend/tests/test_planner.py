"""Tests for the Planner module."""

import pytest
import pytest_asyncio

from app.agent.planner import Planner, ExecutionPlan
from app.services.llm_provider import MockProvider, LLMProvider


class MalformedProvider(LLMProvider):
    """Provider that returns invalid JSON."""
    async def generate(self, prompt, *, system_instruction=None):
        return "not json"

    async def generate_json(self, prompt, *, system_instruction=None):
        return {"invalid": "structure"}

    async def generate_step(self, messages, tools, *, system_instruction=None):
        raise NotImplementedError()


class EmptyPlanProvider(LLMProvider):
    """Provider that returns an empty task list."""
    async def generate(self, prompt, *, system_instruction=None):
        return ""

    async def generate_json(self, prompt, *, system_instruction=None):
        return {"tasks": []}

    async def generate_step(self, messages, tools, *, system_instruction=None):
        raise NotImplementedError()


@pytest.mark.asyncio
async def test_create_plan_success(mock_llm):
    """Test that the planner creates a valid plan."""
    planner = Planner(mock_llm)
    plan = await planner.create_plan("Research AI trends")

    assert isinstance(plan, ExecutionPlan)
    assert len(plan.tasks) >= 1
    assert len(plan.tasks) <= 6
    for task in plan.tasks:
        assert task.title
        assert task.description


@pytest.mark.asyncio
async def test_create_plan_empty_goal(mock_llm):
    """Test that empty goals are rejected."""
    planner = Planner(mock_llm)

    with pytest.raises(ValueError, match="empty"):
        await planner.create_plan("")

    with pytest.raises(ValueError, match="empty"):
        await planner.create_plan("   ")


@pytest.mark.asyncio
async def test_create_plan_too_long_goal(mock_llm):
    """Test that excessively long goals are rejected."""
    planner = Planner(mock_llm)
    long_goal = "a" * 3000

    with pytest.raises(ValueError, match="maximum length"):
        await planner.create_plan(long_goal)


@pytest.mark.asyncio
async def test_create_plan_malformed_output():
    """Test that malformed LLM output causes a bounded retry failure."""
    planner = Planner(MalformedProvider())

    with pytest.raises(ValueError, match="Failed to generate"):
        await planner.create_plan("Test goal")


@pytest.mark.asyncio
async def test_create_plan_empty_plan():
    """Test that empty plans are rejected."""
    planner = Planner(EmptyPlanProvider())

    with pytest.raises(ValueError, match="Failed to generate"):
        await planner.create_plan("Test goal")
