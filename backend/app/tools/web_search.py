"""Web search tool for AgentForge."""

import logging
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.tools.search_provider import SearchProvider, get_search_provider, SearchProviderError

logger = logging.getLogger("agentforge.tools.web_search")


class WebSearchInput(BaseModel):
    """Input parameters for web search tool."""

    query: str = Field(
        ...,
        min_length=2,
        max_length=400,
        description="The specific search query to discover live web information",
        examples=["software engineering internship 2nd year BTech Python 2025"],
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of search results to retrieve (1 to 10, default 5)",
    )


class WebSearchTool(BaseTool):
    """Discovers live web information using the configured search provider."""

    name = "web_search"
    description = (
        "Search the live web for current facts, company details, job postings, documentation, "
        "and technical articles. Returns relevant page titles, URLs, and text snippets. "
        "Use this whenever factual research on external topics is required."
    )
    args_schema = WebSearchInput

    def __init__(self, provider: SearchProvider | None = None):
        self._provider = provider or get_search_provider()

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        """Execute the web search."""
        cleaned_query = query.strip()
        logger.info("Executing web_search for query: '%s' (max_results=%d)", cleaned_query, max_results)

        try:
            results = await self._provider.search(cleaned_query, max_results=max_results)

            if not results:
                return ToolResult(
                    success=True,
                    tool_name=self.name,
                    summary=f"No results found on the web for query: '{cleaned_query}'",
                    output={
                        "query": cleaned_query,
                        "count": 0,
                        "results": [],
                    },
                    sources=[],
                    metadata={"query": cleaned_query, "count": 0},
                )

            # Deduplicate by URL
            seen_urls = set()
            unique_results = []
            sources_to_record = []

            for r in results:
                url = r["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                unique_results.append(r)

                # Source record metadata for persistence
                sources_to_record.append({
                    "title": r.get("title", "Untitled"),
                    "url": url,
                    "domain": r.get("domain", ""),
                    "snippet": r.get("snippet", ""),
                    "extracted_content": None,
                    "extraction_status": "snippet_only",
                })

            summary = f"Found {len(unique_results)} search results for query: '{cleaned_query}'"

            # Build a clear text representation for the LLM
            lines = [summary + "\n"]
            for i, r in enumerate(unique_results, 1):
                lines.append(f"{i}. [{r['title']}]({r['url']})")
                lines.append(f"   Domain: {r['domain']}")
                lines.append(f"   Snippet: {r['snippet']}\n")

            return ToolResult(
                success=True,
                tool_name=self.name,
                summary=summary,
                output="\n".join(lines).strip(),
                sources=sources_to_record,
                metadata={
                    "query": cleaned_query,
                    "count": len(unique_results),
                    "urls": list(seen_urls),
                },
            )

        except SearchProviderError as e:
            logger.warning("Web search error: %s", str(e))
            return ToolResult(
                success=False,
                tool_name=self.name,
                summary=f"Search failed: {str(e)}",
                error=str(e),
                metadata={"query": cleaned_query},
            )
        except Exception as e:
            logger.exception("Unexpected error during web search: %s", str(e))
            return ToolResult(
                success=False,
                tool_name=self.name,
                summary=f"Unexpected search error: {str(e)}",
                error=str(e),
                metadata={"query": cleaned_query},
            )
