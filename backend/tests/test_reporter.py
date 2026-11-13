"""Tests for the Reporter module."""

import pytest

from app.agent.reporter import Reporter
@pytest.mark.asyncio
async def test_generate_report_success():
    """Report formatting does not need another model request."""
    reporter = Reporter()
    results = [
        {"title": "Task 1", "result": "Result 1"},
        {"title": "Task 2", "result": "Result 2"},
    ]
    report = await reporter.generate_report("Test goal", results)

    assert "# Research Report" in report
    assert "## Task 1" in report
    assert "Result 2" in report


@pytest.mark.asyncio
async def test_report_preserves_structured_markdown_answer():
    reporter = Reporter()
    report = await reporter.generate_report(
        "Prepare a concise strategy",
        [{
            "title": "Research",
            "result": "# Strategy\n\n## Vision\nA clear future state.\n\n## Roadmap\n1. Start small.",
        }],
    )

    assert "## Vision\nA clear future state." in report
    assert "## Roadmap\n1. Start small." in report
    assert "### Research" not in report


@pytest.mark.asyncio
async def test_generate_report_with_failures():
    """Test report generation with failed tasks."""
    reporter = Reporter()
    results = [{"title": "Task 1", "result": "Result 1"}]
    failed = [{"title": "Task 2", "error": "Something went wrong"}]

    report = await reporter.generate_report("Test goal", results, failed)
    assert "## Incomplete work" in report
    assert "Something went wrong" in report


@pytest.mark.asyncio
async def test_generate_report_adds_source_table():
    reporter = Reporter()
    report = await reporter.generate_report(
        "Compare options",
        [{"title": "Findings", "result": "Two useful options."}],
        [{"title": "Source A", "url": "https://example.com", "domain": "example.com"}],
    )

    assert "## Sources & Evidence" in report
    assert "| Source A | example.com |" in report
    assert "[Visit](https://example.com)" in report


@pytest.mark.asyncio
async def test_generate_report_deduplicates_sources():
    reporter = Reporter()
    duplicate_source = {
        "title": "Source A",
        "url": "https://example.com",
        "domain": "example.com",
    }

    report = await reporter.generate_report(
        "Research a topic",
        [],
        [duplicate_source, duplicate_source],
    )

    assert report.count("[Visit](https://example.com)") == 1
