"""LLM provider abstraction and implementations with Phase 2 tool calling support.

Provides a clean interface for Gemini function calling and deterministic mock testing.
"""

from abc import ABC, abstractmethod
import asyncio
import json
import logging
import re
from typing import Any
import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("agentforge.llm")


class LLMStepResponse(BaseModel):
    """Result of a single generation step in the tool-calling loop."""

    is_tool_call: bool
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    content: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, *, system_instruction: str | None = None) -> str:
        """Generate text from a prompt. Returns the raw text response."""
        ...

    @abstractmethod
    async def generate_json(self, prompt: str, *, system_instruction: str | None = None) -> dict:
        """Generate a JSON-parseable response. Returns a parsed dict."""
        ...

    @abstractmethod
    async def generate_step(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        system_instruction: str | None = None,
    ) -> LLMStepResponse:
        """Generate the next step in an agentic loop: either a tool call or final text answer."""
        ...


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider using the official google-genai SDK."""

    def __init__(self):
        settings = get_settings()
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when LLM_PROVIDER=gemini. "
                "Set it in .env or use LLM_PROVIDER=mock for testing."
            )
        try:
            from google import genai
            self._client = genai.Client(api_key=settings.gemini_api_key)
        except Exception as e:
            logger.error("Failed to initialize Gemini Client: %s", str(e))
            raise

        self._model = settings.gemini_model
        logger.info("Gemini provider initialized with model: %s", self._model)

    async def generate(self, prompt: str, *, system_instruction: str | None = None) -> str:
        """Generate text using Gemini."""
        from google.genai import types as genai_types

        config = genai_types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=4096,
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self._model,
            contents=prompt,
            config=config,
        )
        return response.text or ""

    async def generate_json(self, prompt: str, *, system_instruction: str | None = None) -> dict:
        """Generate JSON using Gemini with JSON output mode."""
        from google.genai import types as genai_types

        config = genai_types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=4096,
            response_mime_type="application/json",
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self._model,
            contents=prompt,
            config=config,
        )
        text = (response.text or "").strip()
        return json.loads(text)

    async def generate_step(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        system_instruction: str | None = None,
    ) -> LLMStepResponse:
        """Execute a step with Gemini function declarations."""
        from google.genai import types as genai_types

        # Convert tool schemas to Gemini function declarations
        fn_declarations = []
        for t in tools:
            fn_declarations.append(
                genai_types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=t.get("parameters"),
                )
            )

        gemini_tools = [genai_types.Tool(function_declarations=fn_declarations)] if fn_declarations else None

        config = genai_types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=4096,
            tools=gemini_tools,
        )
        if system_instruction:
            config.system_instruction = system_instruction

        # Convert conversation messages
        contents = self._convert_messages_to_gemini(messages)

        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self._model,
            contents=contents,
            config=config,
        )

        # Inspect if Gemini requested a function call
        if response.function_calls:
            fc = response.function_calls[0]
            args = dict(fc.args) if fc.args else {}
            logger.info("Gemini requested tool call: %s with args: %s", fc.name, args)
            return LLMStepResponse(
                is_tool_call=True,
                tool_name=fc.name,
                tool_args=args,
            )

        return LLMStepResponse(
            is_tool_call=False,
            content=response.text or "",
        )

    def _convert_messages_to_gemini(self, messages: list[dict]) -> list[Any]:
        """Convert standard message dicts to google-genai Content structures."""
        from google.genai import types as genai_types

        gemini_contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content_text = msg.get("content", "")

            if role == "user":
                gemini_contents.append(
                    genai_types.Content(
                        role="user",
                        parts=[genai_types.Part.from_text(text=content_text)],
                    )
                )
            elif role == "model" and msg.get("tool_call"):
                tc = msg["tool_call"]
                gemini_contents.append(
                    genai_types.Content(
                        role="model",
                        parts=[
                            genai_types.Part.from_text(
                                text=f"I will call the tool '{tc['name']}' with arguments: {json.dumps(tc.get('args', {}))}"
                            )
                        ],
                    )
                )
            elif role == "tool":
                gemini_contents.append(
                    genai_types.Content(
                        role="user",
                        parts=[
                            genai_types.Part.from_text(
                                text=f"Tool '{msg.get('name', 'tool')}' result:\n{content_text}"
                            )
                        ],
                    )
                )
            elif role == "model":
                gemini_contents.append(
                    genai_types.Content(
                        role="model",
                        parts=[genai_types.Part.from_text(text=content_text)],
                    )
                )

        return gemini_contents


class GroqProvider(LLMProvider):
    """Groq LLM provider using the OpenAI-compatible REST API."""

    _BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self):
        settings = get_settings()
        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is required when LLM_PROVIDER=groq. "
                "Set it in .env or use LLM_PROVIDER=mock for testing."
            )
        self._api_key = settings.groq_api_key
        self._model = settings.groq_model
        self._client = httpx.AsyncClient(
            base_url=self._BASE_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=60.0,
        )
        logger.info("Groq provider initialized with model: %s", self._model)

    async def _chat(self, messages: list[dict], **kwargs) -> dict:
        """Make a raw chat completions call and return the parsed JSON.

        Key behaviour:
        - When ``tools`` is non-empty, sends ``tool_choice='auto'``.
        - When no tools are provided, sends ``tool_choice='none'``.
        - Handles 429 rate limit (TPM limit) with backoff and retry.
        - Handles 400 "Tool choice is none, but model called a tool" by retrying with
          an explicit disallow system message so the generation does not fail.
        """
        tools = kwargs.get("tools") or []
        max_tokens = kwargs.get("max_tokens", 2048)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": max_tokens,
        }
        if "response_format" in kwargs:
            payload["response_format"] = kwargs["response_format"]
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        else:
            payload["tool_choice"] = "none"

        max_retries = 2
        for attempt in range(max_retries + 1):
            resp = await self._client.post("/chat/completions", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                logger.debug(
                    "Groq response finish_reason=%s tokens=%s",
                    data["choices"][0].get("finish_reason"),
                    data.get("usage", {}).get("total_tokens"),
                )
                return data

            # Parse error payload safely
            err_type = "unknown"
            err_code = "unknown"
            err_msg = resp.text
            try:
                err_body = resp.json().get("error", {})
                err_type = err_body.get("type", "unknown")
                err_code = err_body.get("code", "unknown")
                err_msg = err_body.get("message", resp.text)
            except Exception:
                pass

            logger.error(
                "Groq API %d | type=%s | code=%s | request_id=%s | message=%s",
                resp.status_code,
                err_type,
                err_code,
                resp.headers.get("x-request-id", "—"),
                err_msg[:500],
            )

            # Handle 429 Rate Limit (TPM token limit exceeded)
            if resp.status_code == 429 and attempt < max_retries:
                retry_after = resp.headers.get("retry-after")
                wait_s = 5.0
                if retry_after:
                    try:
                        wait_s = float(retry_after)
                    except ValueError:
                        pass
                else:
                    m = re.search(r"try again in ([\d\.]+)s", err_msg)
                    if m:
                        try:
                            wait_s = float(m.group(1))
                        except ValueError:
                            pass
                wait_s = min(max(wait_s, 2.0), 25.0)
                logger.info(
                    "Groq TPM rate limit reached on %s; waiting %.1fs before retry (attempt %d/%d)...",
                    self._model,
                    wait_s,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(wait_s + 0.5)
                continue

            # Handle 400 "Tool choice is none, but model called a tool" / tool_use_failed
            if (
                resp.status_code == 400
                and not tools
                and (err_code == "tool_use_failed" or "Tool choice is none" in err_msg or "tool" in err_msg.lower())
                and attempt < max_retries
            ):
                logger.info("Groq 400 tool_use_failed during synthesis/direct generation. Retrying with explicit disallow directive...")
                retry_messages = list(payload["messages"]) + [
                    {
                        "role": "system",
                        "content": (
                            "IMPORTANT: Tool calling is disabled. You must NOT output tool calls, "
                            "function calls, or tool JSON. Provide your complete response directly in plain markdown text."
                        ),
                    }
                ]
                payload["messages"] = retry_messages
                payload["tool_choice"] = "none"
                continue

            # If not retriable or out of retries, raise HTTP error
            resp.raise_for_status()

        resp.raise_for_status()
        return resp.json()

    async def generate(self, prompt: str, *, system_instruction: str | None = None) -> str:
        """Generate text using Groq."""
        messages: list[dict] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        data = await self._chat(messages, temperature=0.7)
        return data["choices"][0]["message"]["content"] or ""

    async def generate_json(self, prompt: str, *, system_instruction: str | None = None) -> dict:
        """Generate JSON using Groq with JSON response mode."""
        messages: list[dict] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        data = await self._chat(
            messages,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        text = (data["choices"][0]["message"]["content"] or "").strip()
        return json.loads(text)

    async def generate_step(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        system_instruction: str | None = None,
    ) -> LLMStepResponse:
        """Execute one agentic step: returns a tool call or final text answer."""
        groq_messages: list[dict] = []
        if system_instruction:
            groq_messages.append({"role": "system", "content": system_instruction})

        # Convert generic message dicts to OpenAI-compatible format
        for msg in messages:
            role = msg.get("role", "user")
            if role == "tool":
                # Tool result messages
                groq_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", "call_0"),
                    "content": msg.get("content", ""),
                })
            elif role == "model":
                if msg.get("tool_call"):
                    tc = msg["tool_call"]
                    groq_messages.append({
                        "role": "assistant",
                        "tool_calls": [{
                            "id": tc.get("id", "call_0"),
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("args", {})),
                            },
                        }],
                    })
                else:
                    groq_messages.append({"role": "assistant", "content": msg.get("content", "")})
            else:
                groq_messages.append({"role": role, "content": msg.get("content", "")})

        # Convert tool schemas to OpenAI function-calling format
        groq_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

        data = await self._chat(
            groq_messages,
            temperature=0.4,
            tools=groq_tools if groq_tools else None,
            max_tokens=1500,
        )

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason", "")

        if finish_reason == "tool_calls" or message.get("tool_calls"):
            tc = message["tool_calls"][0]
            fn = tc["function"]
            args = {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool call args: %s", fn.get("arguments"))
            logger.info("Groq requested tool call: %s with args: %s", fn["name"], args)
            return LLMStepResponse(
                is_tool_call=True,
                tool_name=fn["name"],
                tool_args=args,
            )

        return LLMStepResponse(
            is_tool_call=False,
            content=message.get("content") or "",
        )



class MockProvider(LLMProvider):
    """Mock LLM provider for development and testing without API keys."""

    def __init__(self):
        logger.info("Mock LLM provider initialized (no API key required)")

    async def generate(self, prompt: str, *, system_instruction: str | None = None) -> str:
        """Return realistic mock text responses."""
        await asyncio.sleep(0.05)  # Fast simulated latency

        prompt_lower = prompt.lower()
        if "final report" in prompt_lower or "synthesize" in prompt_lower:
            return self._mock_report(prompt)

        return self._mock_task_result(prompt)

    async def generate_json(self, prompt: str, *, system_instruction: str | None = None) -> dict:
        """Return a realistic mock plan as JSON."""
        await asyncio.sleep(0.05)
        return self._mock_plan(prompt)

    async def generate_step(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        system_instruction: str | None = None,
    ) -> LLMStepResponse:
        """Simulate realistic, multi-step agentic tool calling."""
        await asyncio.sleep(0.05)

        # Count how many tool outputs we've received in this conversation
        tool_responses = [m for m in messages if m.get("role") == "tool"]
        tool_count = len(tool_responses)
        available_tool_names = {t["name"] for t in tools}

        initial_prompt = messages[0].get("content", "").lower() if messages else ""

        # Check if math / calculation task
        if "calculate" in initial_prompt or "arithmetic" in initial_prompt or "compute" in initial_prompt:
            if tool_count == 0 and "calculator" in available_tool_names:
                return LLMStepResponse(
                    is_tool_call=True,
                    tool_name="calculator",
                    tool_args={"expression": "(40 * 12) + 120"},
                )
            else:
                last_result = tool_responses[-1].get("content", "600") if tool_responses else "600"
                return LLMStepResponse(
                    is_tool_call=False,
                    content=(
                        f"The arithmetic calculation was completed using the calculator tool:\n"
                        f"{last_result}\n\n"
                        f"Final verified numerical result: **600**."
                    ),
                )

        # Research / Internship / Web tasks
        if any(w in initial_prompt for w in ["research", "internship", "search", "web", "find", "compare"]):
            if tool_count == 0 and "web_search" in available_tool_names:
                # Step 1: Request web search
                return LLMStepResponse(
                    is_tool_call=True,
                    tool_name="web_search",
                    tool_args={
                        "query": "software engineering internship python web development 2nd year BTech 2025",
                        "max_results": 5,
                    },
                )
            elif tool_count == 1 and "extract_webpage" in available_tool_names:
                # Step 2: Request deep extraction of first search result
                return LLMStepResponse(
                    is_tool_call=True,
                    tool_name="extract_webpage",
                    tool_args={
                        "url": "https://careers.google.com/jobs/results/swe-intern-summer-2025",
                    },
                )
            else:
                # Step 3: Conclude with evidence-backed findings
                return LLMStepResponse(
                    is_tool_call=False,
                    content=(
                        "### Research Findings & Verified Opportunities\n\n"
                        "Based on live search and webpage extraction, here are five verified software engineering internships suitable for 2nd-year BTech students with Python and web development skills:\n\n"
                        "1. **Google Software Engineering Summer Internship 2025**\n"
                        "   - **Eligibility**: Currently enrolled in 2nd/3rd year B.Tech/B.E. (Graduation 2026/2027)\n"
                        "   - **Key Skills**: Python, data structures, algorithms, web platforms\n"
                        "   - **Deadline**: March 31, 2025\n"
                        "   - **Source**: [Google Summer Internship](https://careers.google.com/jobs/results/swe-intern-summer-2025)\n\n"
                        "2. **Microsoft Learn Student SWE Intern**\n"
                        "   - **Eligibility**: 2nd year undergraduates with 7.0+ CGPA\n"
                        "   - **Key Skills**: Python, TypeScript, modern web frameworks (React, FastAPI)\n"
                        "   - **Deadline**: April 15, 2025\n"
                        "   - **Source**: [Microsoft Careers](https://careers.microsoft.com/students/us/en/job/swe-intern-2025)\n\n"
                        "3. **Razorpay Software Engineering Intern (Python & Backend)**\n"
                        "   - **Eligibility**: 2nd/3rd year engineering students\n"
                        "   - **Key Skills**: Python fundamentals, REST APIs, PostgreSQL\n"
                        "   - **Deadline**: Rolling basis\n"
                        "   - **Source**: [Razorpay Careers](https://razorpay.com/careers/engineering-intern-python)\n\n"
                        "4. **Cisco Software Development Internship**\n"
                        "   - **Eligibility**: Enrolled B.Tech students\n"
                        "   - **Key Skills**: Python programming, Linux, REST APIs\n"
                        "   - **Deadline**: Rolling basis\n"
                        "   - **Source**: [Cisco Jobs](https://jobs.cisco.com/jobs/ProjectDetail/Software-Intern/1429810)\n\n"
                        "5. **Swiggy Campus Summer Engineering Internship**\n"
                        "   - **Eligibility**: 2nd and 3rd year B.Tech in CS/IT\n"
                        "   - **Key Skills**: Python, React, web microservices\n"
                        "   - **Deadline**: April 30, 2025\n"
                        "   - **Source**: [Swiggy Careers](https://careers.swiggy.com/internships/software-engineer)\n"
                    ),
                )

        # Default task step
        return LLMStepResponse(
            is_tool_call=False,
            content=self._mock_task_result(initial_prompt),
        )

    def _mock_plan(self, prompt: str) -> dict:
        """Generate a mock execution plan tailored to the goal."""
        prompt_lower = prompt.lower()
        if "internship" in prompt_lower:
            return {
                "tasks": [
                    {
                        "title": "Search for Python SWE Internships",
                        "description": "Discover current software engineering internships suitable for 2nd-year BTech students using web search.",
                    },
                    {
                        "title": "Extract Eligibility and Deadline Details",
                        "description": "Extract full page details for top opportunities to verify requirements, stipends, and deadlines.",
                    },
                    {
                        "title": "Compare Opportunities & Synthesize Findings",
                        "description": "Compare eligibility criteria, locations, tech stacks, and prepare structured recommendations.",
                    },
                ]
            }

        return {
            "tasks": [
                {
                    "title": "Analyze Requirements & Identify Key Topics",
                    "description": "Break down the user's goal into core criteria and determine necessary research points.",
                },
                {
                    "title": "Conduct Web Research & Evidence Collection",
                    "description": "Gather live data and authoritative sources using search and extraction tools.",
                },
                {
                    "title": "Synthesize Evidence & Formulate Recommendations",
                    "description": "Evaluate the gathered evidence, perform calculations if needed, and draft the final conclusions.",
                },
            ]
        }

    def _mock_task_result(self, prompt: str) -> str:
        """Generate a mock task execution result."""
        return (
            "Based on the analysis of available context and evidence:\n\n"
            "1. **Core Findings**: The requirements have been reviewed and validated against retrieved information.\n\n"
            "2. **Evidence Assessment**: Key considerations were evaluated, distinguishing verified facts from estimates.\n\n"
            "3. **Conclusion**: The task objectives are satisfied, ready for final report synthesis."
        )

    def _mock_report(self, prompt: str) -> str:
        """Generate a mock final report with verifiable markdown citations."""
        return (
            "# AgentForge Research & Execution Report\n\n"
            "## Executive Summary\n"
            "AgentForge planned and executed the research goal through sequential text reasoning and real tool use. "
            "Evidence was gathered from live web search and webpage extraction to verify specific criteria, eligibility, and deadlines.\n\n"
            "## Key Findings\n"
            "- Multiple relevant opportunities were discovered matching the requested skillset (Python, web development) and academic standing (2nd-year BTech).\n"
            "- Exact deadlines range between March 31, 2025 and April 30, 2025, with several companies operating on rolling evaluation.\n"
            "- Eligibility requirements emphasize core programming proficiency (Python, algorithms, data structures) and foundational web knowledge.\n\n"
            "## Comparison of Identified Opportunities\n"
            "1. **Google SWE Summer Internship 2025** — [Google Careers](https://careers.google.com/jobs/results/swe-intern-summer-2025)\n"
            "   - Target: 2nd/3rd Year BTech | Skills: Python, Algorithms | Deadline: March 31, 2025\n\n"
            "2. **Microsoft Learn Student SWE Intern** — [Microsoft Careers](https://careers.microsoft.com/students/us/en/job/swe-intern-2025)\n"
            "   - Target: 2nd Year BTech | Skills: Python, React, Web Platforms | Deadline: April 15, 2025\n\n"
            "3. **Razorpay Python Backend Intern** — [Razorpay Careers](https://razorpay.com/careers/engineering-intern-python)\n"
            "   - Target: 2nd/3rd Year BTech | Skills: FastAPI, PostgreSQL | Deadline: Rolling\n\n"
            "4. **Cisco Software Engineering Intern** — [Cisco Jobs](https://jobs.cisco.com/jobs/ProjectDetail/Software-Intern/1429810)\n"
            "   - Target: Enrolled Undergraduates | Skills: Python, Linux, APIs | Deadline: Rolling\n\n"
            "5. **Swiggy Summer Tech Intern** — [Swiggy Careers](https://careers.swiggy.com/internships/software-engineer)\n"
            "   - Target: 2nd/3rd Year BTech CS/IT | Skills: Python, React, Microservices | Deadline: April 30, 2025\n\n"
            "## Limitations & Unverified Items\n"
            "- Application links and deadlines are subject to change as employers fill positions.\n"
            "- Stipends vary by branch and exact location and should be confirmed upon interview invitation.\n\n"
            "## Recommended Next Steps\n"
            "- Ensure your resume highlights projects demonstrating Python, REST APIs, and modern web frameworks.\n"
            "- Submit applications prior to deadlines, prioritizing rolling admission opportunities.\n\n"
            "## Sources & Citations\n"
            "- [Google Summer Internship](https://careers.google.com/jobs/results/swe-intern-summer-2025) `[Extracted]`\n"
            "- [Microsoft Careers](https://careers.microsoft.com/students/us/en/job/swe-intern-2025) `[Search Result]`\n"
            "- [Razorpay Careers](https://razorpay.com/careers/engineering-intern-python) `[Search Result]`\n"
            "- [Cisco Jobs](https://jobs.cisco.com/jobs/ProjectDetail/Software-Intern/1429810) `[Search Result]`\n"
            "- [Swiggy Careers](https://careers.swiggy.com/internships/software-engineer) `[Search Result]`\n"
        )


def create_llm_provider() -> LLMProvider:
    """Factory: create the appropriate LLM provider based on configuration."""
    settings = get_settings()
    provider_name = settings.llm_provider.lower()

    if provider_name == "mock":
        return MockProvider()
    elif provider_name == "gemini":
        return GeminiProvider()
    elif provider_name == "groq":
        return GroqProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}. Use 'groq', 'gemini', or 'mock'.")
