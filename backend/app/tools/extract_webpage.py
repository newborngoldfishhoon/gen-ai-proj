"""Extract webpage tool for deep content retrieval."""

import logging
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.tools.search_provider import SearchProvider, get_search_provider, SafeHttpExtractor

logger = logging.getLogger("agentforge.tools.extract_webpage")


class ExtractWebpageInput(BaseModel):
    """Input parameters for the extract_webpage tool."""

    url: str = Field(
        ...,
        min_length=8,
        max_length=1000,
        description="The full HTTP/HTTPS URL of the webpage to extract detailed content from",
        examples=["https://careers.google.com/jobs/results/swe-intern-summer-2025"],
    )


class ExtractWebpageTool(BaseTool):
    """Extracts detailed text and facts from a specific webpage."""

    name = "extract_webpage"
    description = (
        "Extract the full text content of a specific webpage by URL. "
        "Use this after web_search when a snippet does not contain all required details "
        "(e.g., exact eligibility rules, application deadlines, syllabus, or requirements)."
    )
    args_schema = ExtractWebpageInput

    def __init__(self, provider: SearchProvider | None = None):
        self._provider = provider or get_search_provider()

    async def execute(self, url: str, **kwargs) -> ToolResult:
        """Execute webpage content extraction."""
        cleaned_url = url.strip()
        logger.info("Executing extract_webpage for URL: %s", cleaned_url)

        # 1. SSRF & Scheme Validation
        try:
            SafeHttpExtractor.validate_url(cleaned_url)
        except ValueError as val_err:
            return ToolResult(
                success=False,
                tool_name=self.name,
                summary=f"Security check failed: {str(val_err)}",
                error=str(val_err),
                metadata={"url": cleaned_url},
            )

        parsed = urlparse(cleaned_url)
        domain = parsed.netloc.lower()

        # 2. Extract content via provider
        try:
            data = await self._provider.extract(cleaned_url)

            if not data.get("success", False) or not data.get("content"):
                error_msg = data.get("error") or "No readable text content could be extracted from page"
                return ToolResult(
                    success=False,
                    tool_name=self.name,
                    summary=f"Failed to extract {domain}: {error_msg}",
                    error=error_msg,
                    metadata={"url": cleaned_url, "domain": domain},
                )

            title = data.get("title") or domain
            content = data.get("content", "")

            source_record = {
                "title": title,
                "url": cleaned_url,
                "domain": domain,
                "snippet": content[:300] + ("..." if len(content) > 300 else ""),
                "extracted_content": content,
                "extraction_status": "extracted",
            }

            summary = f"Successfully extracted content from {title} ({domain}, {len(content)} characters)"

            # Format text output for LLM
            llm_text = (
                f"## Extracted Content from: [{title}]({cleaned_url})\n"
                f"**Domain**: {domain}\n\n"
                f"### Page Text:\n{content}"
            )

            return ToolResult(
                success=True,
                tool_name=self.name,
                summary=summary,
                output=llm_text,
                sources=[source_record],
                metadata={
                    "url": cleaned_url,
                    "domain": domain,
                    "title": title,
                    "content_length": len(content),
                },
            )

        except Exception as e:
            logger.exception("Unexpected error extracting webpage %s: %s", cleaned_url, str(e))
            return ToolResult(
                success=False,
                tool_name=self.name,
                summary=f"Extraction failed for {cleaned_url}: {str(e)}",
                error=str(e),
                metadata={"url": cleaned_url},
            )
