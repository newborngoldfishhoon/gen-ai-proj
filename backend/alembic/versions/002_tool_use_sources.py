"""Add agent_tool_calls and agent_sources tables for Phase 2

Revision ID: 002_tool_use_sources
Revises: 001_initial
Create Date: 2025-01-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "002_tool_use_sources"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Create tool_call_status enum on Postgres
    if is_postgres:
        tool_call_status = postgresql.ENUM(
            "pending", "running", "completed", "failed",
            name="tool_call_status",
            create_type=False,
        )
        tool_call_status.create(bind, checkfirst=True)

        extraction_status = postgresql.ENUM(
            "snippet_only", "extracted", "failed",
            name="extraction_status",
            create_type=False,
        )
        extraction_status.create(bind, checkfirst=True)
    else:
        tool_call_status = sa.String(50)
        extraction_status = sa.String(50)

    # Create agent_tool_calls table
    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("arguments", sa.Text(), nullable=False),
        sa.Column("status", tool_call_status, nullable=False, server_default="pending"),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("result_data", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_tool_calls_task_created", "agent_tool_calls", ["task_id", "created_at"])
    op.create_index("ix_agent_tool_calls_run_created", "agent_tool_calls", ["run_id", "created_at"])
    op.create_index("ix_agent_tool_calls_tool_name", "agent_tool_calls", ["tool_name"])

    # Create agent_sources table
    op.create_table(
        "agent_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tool_call_id", sa.Uuid(), sa.ForeignKey("agent_tool_calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("extracted_content", sa.Text(), nullable=True),
        sa.Column("extraction_status", extraction_status, nullable=False, server_default="snippet_only"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_sources_run_url", "agent_sources", ["run_id", "url"])
    op.create_index("ix_agent_sources_run_created", "agent_sources", ["run_id", "created_at"])
    op.create_index("ix_agent_sources_domain", "agent_sources", ["domain"])


def downgrade() -> None:
    op.drop_table("agent_sources")
    op.drop_table("agent_tool_calls")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS extraction_status")
        op.execute("DROP TYPE IF EXISTS tool_call_status")
