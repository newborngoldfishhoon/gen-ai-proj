"""Reporter — synthesizes task results and retrieved sources into citation-backed final reports."""


class Reporter:
    """Formats findings and citations into a structured report without another LLM call."""

    async def generate_report(
        self,
        goal: str,
        task_results: list[dict],
        sources: list[dict] | None = None,
        failed_tasks: list[dict] | None = None,
    ) -> str:
        """Format task results and gathered sources into a final report.

        Args:
            goal: The original user goal.
            task_results: List of dicts with title/result from completed tasks.
            sources: List of source records gathered during the run.
            failed_tasks: Optional list of dicts with title/error for failed tasks.

        Returns:
            The final report as Markdown text with verified citations.
        """
        # Support the historical positional calling convention where 3rd param is failed_tasks.
        if sources and not failed_tasks and any("error" in item for item in sources if isinstance(item, dict)):
            failed_tasks = sources
            all_sources = []
        else:
            all_sources = sources or []
        lines = [
            "# Research Report",
            "",
            f"**Goal:** {goal.strip()}",
            "",
        ]
        for result in task_results:
            title = result.get("title", "Research findings")
            text = str(result.get("result", "")).strip()
            if text.startswith("# "):
                lines.extend([text, ""])
            else:
                lines.extend([f"## {title}", "", text or "No findings were returned.", ""])

        if all_sources:
            lines.extend(self._build_sources_section(all_sources).splitlines())
        else:
            lines.extend(["## Sources", "", "No sources were retrieved.", ""])

        if failed_tasks:
            lines.extend(["## Incomplete work", ""])
            lines.extend(
                f"- **{task.get('title', 'Task')}**: {task.get('error', 'Unknown error')}"
                for task in failed_tasks
            )

        return "\n".join(lines).strip()

    def _build_sources_section(self, sources: list[dict]) -> str:
        """Format the consolidated sources section."""
        lines = [
            "## Sources & Evidence\n",
            "| # | Source Title | Domain | Status | Link |",
            "|---|---|---|---|---|",
        ]
        seen_urls = set()
        count = 0
        for src in sources:
            url = src.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            count += 1
            title = (src.get("title") or url).replace("|", "-").replace("\n", " ")
            domain = src.get("domain", "").replace("|", "-").replace("\n", " ")
            status = "Extracted" if src.get("extraction_status") == "extracted" else "Search Result"
            lines.append(f"| {count} | {title} | {domain} | `{status}` | [Visit]({url}) |")
            if count >= 20:
                break
        return "\n".join(lines)
