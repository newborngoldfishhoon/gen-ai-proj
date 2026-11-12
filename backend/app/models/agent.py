"""AgentRun and AgentTask ORM models."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class RunStatus(str, enum.Enum):
    """Possible statuses for an agent run."""
    PLANNING = "planning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, enum.Enum):
    """Possible statuses for an agent task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCallStatus(str, enum.Enum):
    """Possible statuses for a tool call."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionStatus(str, enum.Enum):
    """Quality / extraction status of a retrieved source."""
    SNIPPET_ONLY = "snippet_only"
    EXTRACTED = "extracted"
    FAILED = "failed"


def _utcnow():
    return datetime.now(timezone.utc)


class AgentRun(Base):
    """Represents a single agent execution run."""

    __tablename__ = "agent_runs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    goal = Column(Text, nullable=False)
    status = Column(
        Enum(
            RunStatus,
            name="run_status",
            create_constraint=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=RunStatus.PLANNING,
        index=True,
    )
    final_report = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    tasks = relationship(
        "AgentTask",
        back_populates="run",
        order_by="AgentTask.order_index",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tool_calls = relationship(
        "ToolCall",
        back_populates="run",
        order_by="ToolCall.created_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    sources = relationship(
        "Source",
        back_populates="run",
        order_by="Source.created_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_agent_runs_created_at", "created_at"),
    )


class AgentTask(Base):
    """Represents a single task within an agent run."""

    __tablename__ = "agent_tasks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(
        Uuid,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    order_index = Column(Integer, nullable=False)
    status = Column(
        Enum(
            TaskStatus,
            name="task_status",
            create_constraint=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=TaskStatus.PENDING,
    )
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    run = relationship("AgentRun", back_populates="tasks")
    tool_calls = relationship(
        "ToolCall",
        back_populates="task",
        order_by="ToolCall.created_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    sources = relationship(
        "Source",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_agent_tasks_run_order", "run_id", "order_index"),
    )


class ToolCall(Base):
    """Represents a single tool invocation performed by the agent."""

    __tablename__ = "agent_tool_calls"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(
        Uuid,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        Uuid,
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name = Column(String(100), nullable=False, index=True)
    arguments = Column(Text, nullable=False)
    status = Column(
        Enum(
            ToolCallStatus,
            name="tool_call_status",
            create_constraint=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=ToolCallStatus.PENDING,
    )
    result_summary = Column(Text, nullable=True)
    result_data = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    run = relationship("AgentRun", back_populates="tool_calls")
    task = relationship("AgentTask", back_populates="tool_calls")
    sources = relationship(
        "Source",
        back_populates="tool_call",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_agent_tool_calls_task_created", "task_id", "created_at"),
        Index("ix_agent_tool_calls_run_created", "run_id", "created_at"),
    )


class Source(Base):
    """Represents a web source retrieved during research."""

    __tablename__ = "agent_sources"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(
        Uuid,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        Uuid,
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tool_call_id = Column(
        Uuid,
        ForeignKey("agent_tool_calls.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(500), nullable=False)
    url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=False, index=True)
    snippet = Column(Text, nullable=True)
    extracted_content = Column(Text, nullable=True)
    extraction_status = Column(
        Enum(
            ExtractionStatus,
            name="extraction_status",
            create_constraint=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=ExtractionStatus.SNIPPET_ONLY,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    run = relationship("AgentRun", back_populates="sources")
    task = relationship("AgentTask", back_populates="sources")
    tool_call = relationship("ToolCall", back_populates="sources")

    __table_args__ = (
        Index("ix_agent_sources_run_url", "run_id", "url"),
        Index("ix_agent_sources_run_created", "run_id", "created_at"),
    )
