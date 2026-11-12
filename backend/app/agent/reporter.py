"""Reporter — synthesizes task results and retrieved sources into citation-backed final reports."""

import logging
from typing import Any

from app.services.llm_provider import LLMProvider

logger = logging.getLogger("agentforge.reporter")

REPORT_SYSTEM_PROMPT = """You are a report synthesis AI for AgentForge. Your job is to create a comprehensive, authoritative final report from completed task results and verified sources.

IMPORTANT CONSTRAINTS & CITATIONS:
- Summarize what was actually discovered in the task results and sources.
- For every factual claim, include a clickable markdown citation to the retrieved source: [Source Title](url).
- NEVER fabricate URLs, quotes, dates, or sources. If an item could not be verified, explicitly state so in the Limitations section.
- Clearly separate findings, conclusions, limitations, and recommended next steps.
- Conclude with a dedicated "## Sources & Citations" section listing all referenced sources.

Structure your report with these sections:
1. **Executive Summary** — High-level overview of what was accomplished
2. **Key Findings & Evidence** — Detailed findings with citations [Title](url)
3. **Comparison & Evaluation** — Comparative breakdown (e.g. comparing internships, requirements, deadlines)
4. **Limitations & Unverified Items** — Information that could not be fully verified or external constraints
5. **Recommended Next Steps** — Actionable advice for the user
6. **Sources & Citations** — List of all actual sources consulted with status ([Extracted] or [Search Result])"""


class Reporter:
    """Generates citation-backed final reports from completed task results and sources."""

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def generate_report(
        self,
        goal: str,
        task_results: list[dict],
        sources: list[dict] | None = None,
        failed_tasks: list[dict] | None = None,
    ) -> str:
        """Synthesize task results and sources into a final report.

        Args:
            goal: The original user goal.
            task_results: List of dicts with title/result from completed tasks.
            sources: List of source records gathered during the run.
            failed_tasks: Optional list of dicts with title/error for failed tasks.

        Returns:
            The final report as Markdown text with verified citations.
        """
        # Support positional calling convention where 3rd param is failed_tasks
        if sources and not failed_tasks and any("error" in item for item in sources if isinstance(item, dict)):
            failed_tasks = sources
            all_sources = []
        else:
            all_sources = sources or []
        prompt = self._build_prompt(goal, task_results, all_sources, failed_tasks)

        try:
            report = await self._llm.generate(
                prompt,
                system_instruction=REPORT_SYSTEM_PROMPT,
            )
            report_text = report.strip()

            # Ensure report includes a sources section if sources exist
            if all_sources and "## Sources" not in report_text:
                report_text += "\n\n" + self._build_sources_section(all_sources)

            logger.info("Final report generated (%d characters)", len(report_text))
            return report_text
        except Exception as e:
            logger.error("Report generation failed: %s; using fallback synthesizer", str(e))
            return self._fallback_report(goal, task_results, all_sources, failed_tasks)

    def _build_prompt(
        self,
        goal: str,
        task_results: list[dict],
        sources: list[dict],
        failed_tasks: list[dict] | None,
    ) -> str:
        """Build the report synthesis prompt."""
        parts = [
            f"## Original Goal\n{goal}\n",
            "## Completed Task Results\n",
        ]

        for i, tr in enumerate(task_results, 1):
            parts.append(f"### Task {i}: {tr['title']}\n{tr['result']}\n")

        if sources:
            parts.append("## Retrieved Verified Sources\n")
            for i, src in enumerate(sources, 1):
                url = src.get("url", "")
                title = src.get("title") or url or f"Source {i}"
                domain = src.get("domain", "")
                status = f"[{src.get('extraction_status', 'snippet_only').replace('_', ' ').title()}]"
                parts.append(
                    f"{i}. [{title}]({url}) ({domain}) — Status: {status}\n"
                    f"   Summary: {src.get('snippet', '')[:200]}\n"
                )

        if failed_tasks:
            parts.append("## Failed Tasks\n")
            for ft in failed_tasks:
                parts.append(f"- **{ft['title']}**: {ft.get('error', 'Unknown error')}\n")

        parts.append(
            "\n## Instructions\n"
            "Create a comprehensive final report synthesizing all findings above. "
            "Use clickable markdown links [Title](url) to cite the retrieved sources. "
            "Follow the required report structure."
        )

        return "\n".join(parts)

    def _build_sources_section(self, sources: list[dict]) -> str:
        """Format the consolidated sources section."""
        lines = ["## Sources & Citations\n"]
        seen_urls = set()
        for src in sources:
            url = src.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            status = "Extracted" if src.get("extraction_status") == "extracted" else "Search Result"
            lines.append(f"- [{src.get('title', url)}]({url}) `[{status}]`")
        return "\n".join(lines)

    def _fallback_report(
        self,
        goal: str,
        task_results: list[dict],
        sources: list[dict],
        failed_tasks: list[dict] | None,
    ) -> str:
        """Generate a structured fallback report if LLM synthesis fails."""
        lines = [
            "# AgentForge Execution Report\n",
            f"## Goal\n{goal}\n",
            "## Task Results\n",
        ]
        for tr in task_results:
            lines.append(f"### {tr['title']}\n{tr['result']}\n")

        if failed_tasks:
            lines.append("## Failed Tasks\n")
            for ft in failed_tasks:
                lines.append(f"- **{ft['title']}**: {ft.get('error', 'Unknown error')}\n")

        if sources:
            lines.append("\n" + self._build_sources_section(sources))

        lines.append(
            "\n---\n*Note: This fallback report was assembled from completed task results. AI synthesis encountered an issue.*"
        )
        return "\n".join(lines)
