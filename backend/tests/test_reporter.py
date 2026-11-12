"""Tests for the Reporter module."""

import pytest

from app.agent.reporter import Reporter
from app.services.llm_provider import LLMProvider


class FailingReportProvider(LLMProvider):
    """Provider that fails during report generation."""
    async def generate(self, prompt, *, system_instruction=None):
        raise RuntimeError("Report generation failed")

    async def generate_json(self, prompt, *, system_instruction=None):
        raise RuntimeError("Report generation failed")

    async def generate_step(self, messages, tools, *, system_instruction=None):
        raise RuntimeError("Report generation failed")


@pytest.mark.asyncio
async def test_generate_report_success(mock_llm):
    """Test successful report generation."""
    reporter = Reporter(mock_llm)
    results = [
        {"title": "Task 1", "result": "Result 1"},
        {"title": "Task 2", "result": "Result 2"},
    ]
    report = await reporter.generate_report("Test goal", results)

    assert report
    assert len(report) > 0


@pytest.mark.asyncio
async def test_generate_report_with_failures(mock_llm):
    """Test report generation with failed tasks."""
    reporter = Reporter(mock_llm)
    results = [{"title": "Task 1", "result": "Result 1"}]
    failed = [{"title": "Task 2", "error": "Something went wrong"}]

    report = await reporter.generate_report("Test goal", results, failed)
    assert report
    assert len(report) > 0


@pytest.mark.asyncio
async def test_generate_report_fallback():
    """Test fallback report when LLM fails."""
    reporter = Reporter(FailingReportProvider())
    results = [{"title": "Task 1", "result": "Result 1"}]

    report = await reporter.generate_report("Test goal", results)
    assert report
    assert "Task 1" in report
    assert "fallback" in report.lower()
