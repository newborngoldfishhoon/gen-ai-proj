"""Unit tests for web search, webpage extraction, and SSRF security controls."""

import pytest
from app.tools.search_provider import MockSearchProvider, TavilySearchProvider, SafeHttpExtractor, SearchProviderError
from app.tools.web_search import WebSearchTool
from app.tools.extract_webpage import ExtractWebpageTool


@pytest.mark.asyncio
async def test_mock_search_provider_internship_query():
    provider = MockSearchProvider()
    results = await provider.search("software engineering internship python btech 2025", max_results=5)

    assert len(results) > 0
    first = results[0]
    assert "title" in first
    assert "url" in first
    assert "domain" in first
    assert "snippet" in first
    assert first["url"].startswith("https://")


@pytest.mark.asyncio
async def test_mock_search_provider_extraction():
    provider = MockSearchProvider()
    url = "https://careers.google.com/jobs/results/swe-intern-summer-2025"
    data = await provider.extract(url)

    assert data["success"] is True
    assert data["url"] == url
    assert "Google" in data["title"]
    assert "Eligibility" in data["content"]


@pytest.mark.asyncio
async def test_web_search_tool_execution():
    tool = WebSearchTool(provider=MockSearchProvider())
    result = await tool.execute(query="python internships", max_results=3)

    assert result.success is True
    assert result.tool_name == "web_search"
    assert len(result.sources) > 0
    assert result.sources[0]["extraction_status"] == "snippet_only"
    assert "python internships" in result.summary.lower()


@pytest.mark.asyncio
async def test_extract_webpage_tool_execution():
    tool = ExtractWebpageTool(provider=MockSearchProvider())
    url = "https://careers.google.com/jobs/results/swe-intern-summer-2025"
    result = await tool.execute(url=url)

    assert result.success is True
    assert result.tool_name == "extract_webpage"
    assert len(result.sources) == 1
    assert result.sources[0]["extraction_status"] == "extracted"
    assert result.sources[0]["url"] == url


def test_ssrf_protection_blocks_dangerous_urls():
    # Loopback / Localhost
    with pytest.raises(ValueError, match="blocked for security"):
        SafeHttpExtractor.validate_url("http://localhost:8000/secret")

    with pytest.raises(ValueError, match="blocked for security"):
        SafeHttpExtractor.validate_url("http://127.0.0.1:5432/admin")

    with pytest.raises(ValueError, match="blocked for security"):
        SafeHttpExtractor.validate_url("http://[::1]/secret")

    # Private IP ranges
    with pytest.raises(ValueError, match="blocked"):
        SafeHttpExtractor.validate_url("http://192.168.1.1/router")

    with pytest.raises(ValueError, match="blocked"):
        SafeHttpExtractor.validate_url("http://10.0.0.5/api")

    with pytest.raises(ValueError, match="blocked"):
        SafeHttpExtractor.validate_url("http://172.16.0.1/internal")

    # Cloud metadata endpoints
    with pytest.raises(ValueError, match="blocked"):
        SafeHttpExtractor.validate_url("http://169.254.169.254/latest/meta-data/")

    # Unsupported schemes
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        SafeHttpExtractor.validate_url("file:///etc/passwd")

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        SafeHttpExtractor.validate_url("gopher://example.com")


@pytest.mark.asyncio
async def test_tavily_missing_api_key_raises_clear_error():
    provider = TavilySearchProvider(api_key="")
    with pytest.raises(SearchProviderError, match="TAVILY_API_KEY is not configured"):
        await provider.search("python jobs")
