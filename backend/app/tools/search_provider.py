"""Search provider abstractions, Tavily provider, and Mock provider."""

from abc import ABC, abstractmethod
import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

logger = logging.getLogger("agentforge.search")


class SearchProviderError(Exception):
    """Raised when a search or extraction provider encounters an error."""
    pass


class SearchProvider(ABC):
    """Abstract base class for search and extraction providers."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search the web for a query.

        Returns a list of dicts:
        [
            {
                "title": str,
                "url": str,
                "domain": str,
                "snippet": str,
                "score": float | None,
            }, ...
        ]
        """
        ...

    @abstractmethod
    async def extract(self, url: str) -> dict:
        """Extract text content from a webpage URL.

        Returns a dict:
        {
            "title": str,
            "url": str,
            "domain": str,
            "content": str,
            "success": bool,
            "error": str | None,
        }
        """
        ...


class TavilySearchProvider(SearchProvider):
    """Tavily API search and extraction provider."""

    SEARCH_ENDPOINT = "https://api.tavily.com/search"
    EXTRACT_ENDPOINT = "https://api.tavily.com/extract"

    def __init__(self, api_key: str | None = None, timeout: float = 20.0):
        settings = get_settings()
        self._api_key = api_key or settings.tavily_api_key
        self._timeout = timeout
        self._max_chars = settings.max_extracted_chars

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        if not self._api_key:
            raise SearchProviderError(
                "TAVILY_API_KEY is not configured. Please set TAVILY_API_KEY in .env "
                "or set SEARCH_PROVIDER=mock for testing without an API key."
            )

        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": min(max_results, 10),
            "search_depth": "basic",
            "include_answer": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self.SEARCH_ENDPOINT, json=payload)
                if response.status_code != 200:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = error_json.get("detail", error_detail)
                    except Exception:
                        pass
                    raise SearchProviderError(
                        f"Tavily search API error (HTTP {response.status_code}): {error_detail}"
                    )

                data = response.json()
                raw_results = data.get("results", [])
                normalized = []

                for item in raw_results:
                    url = item.get("url", "")
                    title = item.get("title", "") or "Untitled Page"
                    snippet = item.get("content", "")
                    score = item.get("score")

                    parsed = urlparse(url)
                    domain = parsed.netloc.lower() or "unknown"

                    normalized.append({
                        "title": title.strip(),
                        "url": url.strip(),
                        "domain": domain,
                        "snippet": snippet.strip(),
                        "score": score,
                    })

                return normalized
        except httpx.TimeoutException as e:
            raise SearchProviderError(f"Tavily search request timed out after {self._timeout}s") from e
        except httpx.RequestError as e:
            raise SearchProviderError(f"Network error contacting Tavily search API: {str(e)}") from e

    async def extract(self, url: str) -> dict:
        parsed = urlparse(url)
        domain = parsed.netloc.lower() or "unknown"

        if not self._api_key:
            raise SearchProviderError(
                "TAVILY_API_KEY is not configured. Set TAVILY_API_KEY in .env or use SEARCH_PROVIDER=mock."
            )

        payload = {
            "api_key": self._api_key,
            "urls": [url],
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self.EXTRACT_ENDPOINT, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    if results:
                        raw_content = results[0].get("raw_content", "") or ""
                        # Bound extracted content size
                        bounded = raw_content[: self._max_chars].strip()
                        return {
                            "title": results[0].get("title") or domain,
                            "url": url,
                            "domain": domain,
                            "content": bounded,
                            "success": True,
                            "error": None,
                        }

                # If Tavily extract endpoint fails or is unsupported on the plan, fallback to safe HTTP fetch
                logger.info("Tavily extract endpoint returned %d; using safe fallback extractor", response.status_code)
                return await SafeHttpExtractor.fetch_and_extract(url, max_chars=self._max_chars, timeout=self._timeout)

        except Exception as e:
            logger.warning("Tavily extract error: %s; using safe fallback extractor", str(e))
            return await SafeHttpExtractor.fetch_and_extract(url, max_chars=self._max_chars, timeout=self._timeout)


class SafeHttpExtractor:
    """Safe HTTP webpage extractor with strict SSRF protection and HTML cleanup."""

    @staticmethod
    def validate_url(url: str) -> None:
        """Validate URL to prevent Server-Side Request Forgery (SSRF)."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.")

        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL must have a valid hostname")

        # Block localhost and common local names
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "metadata.google.internal"):
            raise ValueError("Access to local/loopback or metadata addresses is blocked for security")

        # Block private, link-local, loopback, and reserved IP addresses
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None

        if ip is not None:
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ValueError(f"Access to private IP address '{hostname}' is blocked")

    @classmethod
    async def fetch_and_extract(cls, url: str, max_chars: int = 8000, timeout: float = 15.0) -> dict:
        """Safely fetch HTML and extract readable text."""
        cls.validate_url(url)
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        headers = {
            "User-Agent": "AgentForge/0.2 (Research Assistant; +https://agentforge.dev)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
        }

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
                max_redirects=3,
            ) as client:
                response = await client.get(url)
                if response.status_code >= 400:
                    return {
                        "title": domain,
                        "url": url,
                        "domain": domain,
                        "content": "",
                        "success": False,
                        "error": f"HTTP {response.status_code} {response.reason_phrase}",
                    }

                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return {
                        "title": domain,
                        "url": url,
                        "domain": domain,
                        "content": "",
                        "success": False,
                        "error": f"Unsupported content-type: {content_type}",
                    }

                html_text = response.text
                text, title = cls._strip_html(html_text)
                bounded_text = text[:max_chars].strip()

                return {
                    "title": title or domain,
                    "url": url,
                    "domain": domain,
                    "content": bounded_text,
                    "success": True,
                    "error": None,
                }
        except Exception as e:
            return {
                "title": domain,
                "url": url,
                "domain": domain,
                "content": "",
                "success": False,
                "error": f"Extraction failed: {str(e)}",
            }

    @staticmethod
    def _strip_html(html: str) -> tuple[str, str]:
        """Strip HTML tags, extract title and text using regex without heavy dependencies."""
        import re

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Remove script and style elements
        clean = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
        # Remove comments
        clean = re.sub(r"<!--.*?-->", " ", clean, flags=re.DOTALL)
        # Replace block tags with newlines
        clean = re.sub(r"<(?:p|div|h[1-6]|li|br|tr)[^>]*>", "\n", clean, flags=re.IGNORECASE)
        # Remove remaining tags
        clean = re.sub(r"<[^>]+>", " ", clean)
        # Normalize whitespace
        clean = re.sub(r"[ \t]+", " ", clean)
        clean = re.sub(r"\n\s*\n+", "\n\n", clean)

        return clean.strip(), title


class MockSearchProvider(SearchProvider):
    """Deterministic mock search provider for testing and development without API keys."""

    MOCK_DATABASE = [
        {
            "query_keywords": ["internship", "python", "software", "btech", "web"],
            "results": [
                {
                    "title": "Google Summer Internship 2025 — Software Engineering",
                    "url": "https://careers.google.com/jobs/results/swe-intern-summer-2025",
                    "domain": "careers.google.com",
                    "snippet": "Eligibility: 2nd or 3rd year B.Tech/B.E. students in CS or related fields. Requirements: Python, C++, or Java; web technologies. Duration: 10-12 weeks. Application deadline: March 31, 2025.",
                    "content": (
                        "Google Engineering Internship Program:\n"
                        "Eligibility: Currently enrolled in a Bachelor's degree (BTech/BE) program with graduation in 2026 or 2027.\n"
                        "Skills: Strong proficiency in Python, algorithms, data structures, and web technologies.\n"
                        "Location: Bangalore, Hyderabad, and remote options.\n"
                        "Stipend: Competitive industry stipend provided with housing allowance.\n"
                        "Deadline: Applications close March 31, 2025.\n"
                        "Apply link: https://careers.google.com/jobs/results/swe-intern-summer-2025"
                    ),
                },
                {
                    "title": "Microsoft Learn Student Internship 2025",
                    "url": "https://careers.microsoft.com/students/us/en/job/swe-intern-2025",
                    "domain": "careers.microsoft.com",
                    "snippet": "Open to 2nd year undergraduates. Projects in cloud computing, web platforms, and Python services. Deadline: April 15, 2025. Location: Hyderabad, Noida, Bangalore.",
                    "content": (
                        "Microsoft Software Engineering Internship:\n"
                        "Eligibility: Undergraduate BTech students (2nd and 3rd year).\n"
                        "Skills: Experience with Python, JavaScript, TypeScript, or modern web frameworks (React, FastAPI).\n"
                        "Perks: Health coverage, mentorship, return offer opportunities.\n"
                        "Application deadline: April 15, 2025."
                    ),
                },
                {
                    "title": "Razorpay Software Engineering Intern — Python & Backend",
                    "url": "https://razorpay.com/careers/engineering-intern-python",
                    "domain": "razorpay.com",
                    "snippet": "Fintech software engineering internship for 2nd/3rd year engineering students. Hands-on experience with FastAPI, Python, PostgreSQL, and scalable microservices. Rolling applications.",
                    "content": (
                        "Razorpay Summer Tech Internship:\n"
                        "Eligibility: Second-year and pre-final year BTech/BE students.\n"
                        "Requirements: Strong Python fundamentals, understanding of REST APIs, basic SQL and Git.\n"
                        "Duration: 3 to 6 months.\n"
                        "Application process: Technical assessment followed by system design and coding interview."
                    ),
                },
                {
                    "title": "Cisco Software Development Internship 2025",
                    "url": "https://jobs.cisco.com/jobs/ProjectDetail/Software-Intern/1429810",
                    "domain": "jobs.cisco.com",
                    "snippet": "Cisco is hiring Software Engineering Interns. Work with networking software, cloud infrastructure, and Python automation. Open to enrolled BTech students graduating 2026-2027.",
                    "content": (
                        "Cisco Software Engineering Internship 2025:\n"
                        "Eligibility: B.Tech/B.E. 2nd year and 3rd year students with 7.0+ CGPA.\n"
                        "Key skills: Python programming, Linux fundamentals, REST APIs.\n"
                        "Deadline: Rolling basis until positions are filled.\n"
                        "Locations: Bangalore, Chennai."
                    ),
                },
                {
                    "title": "Swiggy Campus Summer Engineering Internship",
                    "url": "https://careers.swiggy.com/internships/software-engineer",
                    "domain": "careers.swiggy.com",
                    "snippet": "Swiggy Tech internship program for passionate undergraduate coders. High-scale distributed systems, Python microservices, and React web apps. Applications open until April 30, 2025.",
                    "content": (
                        "Swiggy Engineering Internship Program:\n"
                        "Target: 2nd and 3rd year B.Tech students in Computer Science or IT.\n"
                        "Tech Stack: Python, Go, React, Kafka, PostgreSQL.\n"
                        "Duration: May - July 2025 (8-10 weeks).\n"
                        "Application deadline: April 30, 2025."
                    ),
                },
            ],
        },
    ]

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        query_lower = query.lower()
        limit = min(max_results, 10)

        # Match query keywords against mock database
        matched_results = []
        for entry in self.MOCK_DATABASE:
            if any(kw in query_lower for kw in entry["query_keywords"]):
                matched_results.extend(entry["results"])
                break

        if not matched_results:
            # Fallback generic mock results
            matched_results = [
                {
                    "title": f"Technical Research Resource: {query.title()}",
                    "url": f"https://example.org/research/{query.replace(' ', '-').lower()}",
                    "domain": "example.org",
                    "snippet": f"Comprehensive technical overview and empirical analysis regarding {query}. Details key methodologies, practical frameworks, and findings.",
                    "content": f"Detailed reference article on {query}. Contains analysis, verified criteria, and specifications for implementation.",
                },
                {
                    "title": f"Documentation & Specifications for {query.title()}",
                    "url": f"https://docs.example.org/{query.replace(' ', '-').lower()}",
                    "domain": "docs.example.org",
                    "snippet": f"Official documentation, standards, and benchmarks related to {query}. Includes comparative analysis and specifications.",
                    "content": f"Official guide and documentation on {query}.",
                },
            ]

        results = []
        for item in matched_results[:limit]:
            results.append({
                "title": item["title"],
                "url": item["url"],
                "domain": item["domain"],
                "snippet": item["snippet"],
                "score": 0.95,
            })
        return results

    async def extract(self, url: str) -> dict:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check mock database for matching URL
        for entry in self.MOCK_DATABASE:
            for item in entry["results"]:
                if item["url"] == url:
                    return {
                        "title": item["title"],
                        "url": url,
                        "domain": domain,
                        "content": item["content"],
                        "success": True,
                        "error": None,
                    }

        return {
            "title": f"Extracted Page from {domain}",
            "url": url,
            "domain": domain,
            "content": f"This is mock extracted page text from {url}. It contains detailed information relevant to the research goal.",
            "success": True,
            "error": None,
        }


def get_search_provider() -> SearchProvider:
    """Factory returning the configured search provider."""
    settings = get_settings()
    provider_name = settings.search_provider.lower()

    if provider_name == "mock" or not settings.tavily_api_key:
        logger.info("Using MockSearchProvider (mock mode or no TAVILY_API_KEY provided)")
        return MockSearchProvider()
    elif provider_name == "tavily":
        return TavilySearchProvider()
    else:
        logger.warning("Unknown search provider '%s'; defaulting to MockSearchProvider", provider_name)
        return MockSearchProvider()
