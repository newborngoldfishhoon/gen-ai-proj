"""
Regression tests for GroqProvider tool-calling protocol and error handling.

All tests are fully offline — they use httpx.MockTransport so no real HTTP
requests are made and no API keys are required.
"""

import json
import pytest
import httpx

from app.services.llm_provider import GroqProvider, LLMStepResponse


# ── Helpers ───────────────────────────────────────────────────────────────────

def _response(
    body: dict,
    status: int = 200,
    headers: dict | None = None,
) -> httpx.Response:
    """Build a minimal fake httpx.Response."""
    response_headers = {
        "content-type": "application/json",
        "x-request-id": "test-req-id",
    }
    if headers:
        response_headers.update(headers)
    return httpx.Response(
        status_code=status,
        headers=response_headers,
        content=json.dumps(body).encode(),
    )


def _tool_call_response(name: str, arguments: dict, tc_id: str = "call_abc123") -> dict:
    return {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }],
            },
        }],
        "usage": {"total_tokens": 100},
    }


def _text_response(content: str) -> dict:
    return {
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": content, "tool_calls": None},
        }],
        "usage": {"total_tokens": 150},
    }


def _error_response(msg: str, code: str = "tool_use_failed") -> dict:
    return {"error": {"message": msg, "type": "invalid_request_error", "code": code}}


class _MockTransport(httpx.AsyncBaseTransport):
    """Replay a fixed sequence of responses."""

    def __init__(self, responses: list[httpx.Response | Exception]):
        self._queue = list(responses)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert self._queue, "Unexpected extra request made"
        response = self._queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _make_provider(
    responses: list[httpx.Response | Exception],
) -> tuple[GroqProvider, _MockTransport]:
    transport = _MockTransport(responses)
    provider = GroqProvider.__new__(GroqProvider)
    provider._api_key = "test-key"
    provider._model = "openai/gpt-oss-120b"
    provider._max_retries = 4
    provider._retry_max_delay_seconds = 60
    provider._client = httpx.AsyncClient(
        base_url="https://api.groq.com/openai/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=transport,
        timeout=10,
    )
    return provider, transport


@pytest.mark.asyncio
async def test_rate_limit_retries_after_server_hint(monkeypatch):
    """A 429 waits as directed, then retries successfully."""
    provider, transport = _make_provider([
        _response(
            _error_response("Rate limit reached", "rate_limit_exceeded"),
            status=429,
            headers={"retry-after": "0"},
        ),
        _response(_text_response("Recovered after rate limit")),
    ])
    delays = []

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("app.services.llm_provider.asyncio.sleep", record_sleep)
    result = await provider.generate("Try again")

    assert result == "Recovered after rate limit"
    assert len(transport.requests) == 2
    assert delays == [0.0]


@pytest.mark.asyncio
async def test_transient_server_error_retries_with_backoff(monkeypatch):
    """A transient upstream 503 retries with bounded backoff."""
    provider, transport = _make_provider([
        _response(_error_response("Temporarily unavailable"), status=503),
        _response(_text_response("Recovered after upstream error")),
    ])
    delays = []

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("app.services.llm_provider.asyncio.sleep", record_sleep)
    result = await provider.generate("Try again")

    assert result == "Recovered after upstream error"
    assert len(transport.requests) == 2
    assert len(delays) == 1
    assert 0 < delays[0] <= provider._retry_max_delay_seconds


@pytest.mark.asyncio
async def test_transient_network_error_retries(monkeypatch):
    """A transient connection error retries instead of failing the task immediately."""
    provider, transport = _make_provider([
        httpx.ConnectError("temporary network failure"),
        _response(_text_response("Recovered after network error")),
    ])
    delays = []

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("app.services.llm_provider.asyncio.sleep", record_sleep)
    result = await provider.generate("Try again")

    assert result == "Recovered after network error"
    assert len(transport.requests) == 2
    assert len(delays) == 1


TOOL_DECLS = [
    {
        "name": "web_search",
        "description": "Search the web",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "query"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    }
]


# ── Test 1: single successful tool call ───────────────────────────────────────

@pytest.mark.asyncio
async def test_single_tool_call_returned():
    """generate_step returns is_tool_call=True when the model calls a tool."""
    provider, transport = _make_provider([
        _response(_tool_call_response("web_search", {"query": "pilot requirements"})),
    ])
    messages = [{"role": "user", "content": "Find pilot requirements"}]
    step = await provider.generate_step(messages, tools=TOOL_DECLS)

    assert step.is_tool_call is True
    assert step.tool_name == "web_search"
    assert step.tool_args == {"query": "pilot requirements"}

    # Verify tool_choice='auto' was sent
    sent = json.loads(transport.requests[0].content)
    assert sent["tool_choice"] == "auto"
    assert len(sent["tools"]) == 1


# ── Test 2: model returns final text (no tool call) ───────────────────────────

@pytest.mark.asyncio
async def test_final_text_response_no_tools():
    """generate_step returns is_tool_call=False when the model gives a direct answer."""
    provider, transport = _make_provider([
        _response(_text_response("Here is the answer.")),
    ])
    messages = [{"role": "user", "content": "Summarise what you found"}]
    step = await provider.generate_step(messages, tools=[])

    assert step.is_tool_call is False
    assert step.content == "Here is the answer."

    # Verify tool_choice='none' was sent (key fix)
    sent = json.loads(transport.requests[0].content)
    assert sent["tool_choice"] == "none"
    assert "tools" not in sent


# ── Test 3: multi-round search → extract → final answer ──────────────────────

@pytest.mark.asyncio
async def test_multi_round_tool_conversation():
    """
    Full multi-round agentic loop:
      iter 1 → tool call (web_search)
      iter 2 → tool call (extract_webpage)
      iter 3 → final text answer (no more tools)

    Verifies that each assistant tool-call message is correctly echoed back
    with matching tool_call_id in the subsequent tool result message.
    """
    tc1_id = "call_11111111"
    tc2_id = "call_22222222"

    provider, transport = _make_provider([
        _response(_tool_call_response("web_search", {"query": "FAA pilot age"}, tc1_id)),
        _response(_tool_call_response("extract_webpage", {"url": "https://faa.gov/pilot"}, tc2_id)),
        _response(_text_response("FAA requires age 17+ for PPL, 23+ for ATP.")),
    ])

    # ── Round 1 ──────────────────────────────────────────────────────────────
    messages = [{"role": "user", "content": "What are FAA pilot age requirements?"}]
    step1 = await provider.generate_step(messages, tools=TOOL_DECLS)

    assert step1.is_tool_call is True
    assert step1.tool_name == "web_search"

    # Simulate executor appending both messages
    messages.append({"role": "model", "tool_call": {"id": tc1_id, "name": "web_search", "args": step1.tool_args}})
    messages.append({"role": "tool", "tool_call_id": tc1_id, "name": "web_search", "content": "5 results found..."})

    # ── Round 2 ──────────────────────────────────────────────────────────────
    step2 = await provider.generate_step(messages, tools=TOOL_DECLS)

    assert step2.is_tool_call is True
    assert step2.tool_name == "extract_webpage"

    messages.append({"role": "model", "tool_call": {"id": tc2_id, "name": "extract_webpage", "args": step2.tool_args}})
    messages.append({"role": "tool", "tool_call_id": tc2_id, "name": "extract_webpage", "content": "Age 17 for PPL..."})

    # ── Round 3: final answer (no more tools) ────────────────────────────────
    step3 = await provider.generate_step(messages, tools=[])

    assert step3.is_tool_call is False
    assert "FAA" in step3.content

    # Verify the synthesis call uses tool_choice='none'
    last_sent = json.loads(transport.requests[2].content)
    assert last_sent["tool_choice"] == "none"
    assert "tools" not in last_sent


# ── Test 4: correct assistant/tool message ordering ──────────────────────────

@pytest.mark.asyncio
async def test_message_ordering_in_request():
    """
    After a tool exchange, the next request must contain:
      [system, user, assistant(tool_calls), tool(result)]
    in that exact order, with matching tool_call_id.
    """
    tc_id = "call_deadbeef"
    provider, transport = _make_provider([
        _response(_text_response("Done.")),
    ])

    messages = [
        {"role": "user", "content": "Research AI"},
        {"role": "model", "tool_call": {"id": tc_id, "name": "web_search", "args": {"query": "AI news"}}},
        {"role": "tool",  "tool_call_id": tc_id, "name": "web_search", "content": "AI news results"},
    ]

    await provider.generate_step(messages, tools=[], system_instruction="Be helpful.")

    sent = json.loads(transport.requests[0].content)
    msgs = sent["messages"]

    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "tool"]

    # tool_call_id must match
    assert msgs[2]["tool_calls"][0]["id"] == tc_id
    assert msgs[3]["tool_call_id"] == tc_id
    assert msgs[3]["content"] == "AI news results"


# ── Test 5: provider 400 error raises with diagnostic detail ─────────────────

@pytest.mark.asyncio
async def test_provider_400_raises_with_details(caplog):
    """
    When Groq returns a 400 and retries also fail, _chat raises HTTPStatusError
    and the error body (type, code, message, request_id) is logged — but not the API key.
    """
    import logging
    err_body = _error_response("Tool choice is none, but model called a tool", "tool_use_failed")
    provider, _ = _make_provider([
        _response(err_body, status=400),
        _response(err_body, status=400),
        _response(err_body, status=400),
        _response(err_body, status=400),
        _response(err_body, status=400),
    ])

    with caplog.at_level(logging.ERROR, logger="agentforge.llm"):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.generate_step(
                [{"role": "user", "content": "hello"}],
                tools=[],
            )

    log_text = "\n".join(caplog.messages)
    assert "400" in log_text
    assert "tool_use_failed" in log_text
    # API key must never appear in logs
    assert "gsk_" not in log_text
    assert "test-key" not in log_text


@pytest.mark.asyncio
async def test_provider_400_tool_use_failed_recovers():
    """
    When Groq returns 400 'tool_use_failed' on a synthesis step (no tools),
    it automatically retries with an explicit disallow directive and recovers.
    """
    provider, transport = _make_provider([
        _response(
            _error_response("Tool choice is none, but model called a tool", "tool_use_failed"),
            status=400,
        ),
        _response(_text_response("Recovered synthesized response without tools")),
    ])

    step = await provider.generate_step(
        [{"role": "user", "content": "synthesize this"}],
        tools=[],
    )

    assert not step.is_tool_call
    assert step.content == "Recovered synthesized response without tools"
    # Verify two requests were made (original + retry)
    assert len(transport.requests) == 2
    # Verify the retry injected the disallow directive
    body2 = json.loads(transport.requests[1].content)
    assert any("Tool calling is disabled" in m.get("content", "") for m in body2["messages"])


# ── Test 6: large research context is accepted (bounded tool result) ──────────

@pytest.mark.asyncio
async def test_large_context_accepted():
    """
    With many tool exchanges the provider still sends a valid request.
    (This guards against accidental payload construction failures.)
    """
    tc_ids = [f"call_{i:08x}" for i in range(5)]
    big_content = "X" * 3000  # 3 KB per tool result

    provider, transport = _make_provider([
        _response(_text_response("Final answer after large context.")),
    ])

    messages: list[dict] = [{"role": "user", "content": "Big research task"}]
    for i, tc_id in enumerate(tc_ids):
        messages.append({"role": "model", "tool_call": {"id": tc_id, "name": "web_search", "args": {"query": f"query {i}"}}})
        messages.append({"role": "tool", "tool_call_id": tc_id, "name": "web_search", "content": big_content})

    step = await provider.generate_step(messages, tools=[])
    assert step.is_tool_call is False
    assert "Final answer" in step.content

    sent = json.loads(transport.requests[0].content)
    # Must have: system? + user + 5*(assistant+tool) = 11 or 12 messages
    assert len(sent["messages"]) == 11  # no system instruction in this test
    assert sent["tool_choice"] == "none"


# ── Test 7: generate_json uses json_object mode ───────────────────────────────

@pytest.mark.asyncio
async def test_generate_json_uses_json_mode():
    """generate_json sends response_format={'type':'json_object'} and parses result."""
    provider, transport = _make_provider([
        _response(_text_response('{"tasks": [{"title": "Step 1", "description": "Do X"}]}')),
    ])

    result = await provider.generate_json("Plan this goal")

    assert isinstance(result, dict)
    assert "tasks" in result

    sent = json.loads(transport.requests[0].content)
    assert sent.get("response_format") == {"type": "json_object"}
    # JSON mode must not include tools or tool_choice
    assert "tools" not in sent
    # tool_choice must be 'none' (no tools)
    assert sent.get("tool_choice") == "none"
