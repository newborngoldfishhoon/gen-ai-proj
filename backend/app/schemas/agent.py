"""Pydantic schemas for API request/response validation with Phase 2 tools and sources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Requests ──────────────────────────────────────────────────────────────


class RunCreateRequest(BaseModel):
    """Request body for creating a new agent run."""

    goal: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The natural-language goal for the agent.",
        examples=["Research five software engineering internships suitable for 2nd-year BTech students with Python skills"],
    )


# ── Tool & Source Responses ──────────────────────────────────────────────


class ToolCallResponse(BaseModel):
    """Details of a tool invocation."""

    id: UUID
    run_id: UUID
    task_id: UUID
    tool_name: str
    arguments: str
    status: str
    result_summary: str | None = None
    result_data: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceResponse(BaseModel):
    """Details of a retrieved web source."""

    id: UUID
    run_id: UUID
    task_id: UUID | None = None
    tool_call_id: UUID | None = None
    title: str
    url: str
    domain: str
    snippet: str | None = None
    extracted_content: str | None = None
    extraction_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Task & Run Responses ─────────────────────────────────────────────────


class TaskResponse(BaseModel):
    """A single task within an agent run."""

    id: UUID
    run_id: UUID
    title: str
    description: str
    order_index: int
    status: str
    result: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    tool_calls: list[ToolCallResponse] = []

    model_config = {"from_attributes": True}


class RunResponse(BaseModel):
    """Full details of an agent run, including tasks, tool calls, and sources."""

    id: UUID
    goal: str
    status: str
    final_report: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    tasks: list[TaskResponse] = []
    tool_calls: list[ToolCallResponse] = []
    sources: list[SourceResponse] = []

    model_config = {"from_attributes": True}


class RunListItem(BaseModel):
    """Summary of a run for list views (no heavy task results)."""

    id: UUID
    goal: str
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    task_count: int = 0
    completed_task_count: int = 0
    tool_call_count: int = 0
    source_count: int = 0

    model_config = {"from_attributes": True}


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    runs: list[RunListItem]
    total: int


class RunCreatedResponse(BaseModel):
    """Response after creating a new run."""

    id: UUID
    status: str
    message: str = "Agent run started"


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    service: str = "agentforge"
    version: str = "0.2.0"


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
