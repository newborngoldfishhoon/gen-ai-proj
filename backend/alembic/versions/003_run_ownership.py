"""Associate saved runs with users and expire guest runs.

Revision ID: 003_run_ownership
Revises: 002_tool_use_sources
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_run_ownership"
down_revision: Union[str, None] = "002_tool_use_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("agent_runs", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.add_column("agent_runs", sa.Column("guest_session_hash", sa.String(length=64), nullable=True))
    op.add_column("agent_runs", sa.Column("guest_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agent_runs_owner_user_id", "agent_runs", ["owner_user_id"])
    op.create_index("ix_agent_runs_guest_session_hash", "agent_runs", ["guest_session_hash"])
    op.create_index("ix_agent_runs_guest_expires_at", "agent_runs", ["guest_expires_at"])

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE public.agent_runs ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY agent_runs_owner_access ON public.agent_runs "
            "FOR ALL TO authenticated "
            "USING (owner_user_id = (SELECT auth.uid())) "
            "WITH CHECK (owner_user_id = (SELECT auth.uid()))"
        )
        for table in ("agent_tasks", "agent_tool_calls", "agent_sources"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_owner_access ON public.{table} "
                "FOR ALL TO authenticated "
                "USING (EXISTS ("
                "SELECT 1 FROM public.agent_runs "
                f"WHERE public.agent_runs.id = public.{table}.run_id "
                "AND public.agent_runs.owner_user_id = (SELECT auth.uid())"
                ")) "
                "WITH CHECK (EXISTS ("
                "SELECT 1 FROM public.agent_runs "
                f"WHERE public.agent_runs.id = public.{table}.run_id "
                "AND public.agent_runs.owner_user_id = (SELECT auth.uid())"
                "))"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("agent_tasks", "agent_tool_calls", "agent_sources"):
            op.execute(f"DROP POLICY IF EXISTS {table}_owner_access ON public.{table}")
            op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS agent_runs_owner_access ON public.agent_runs")
        op.execute("ALTER TABLE public.agent_runs DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_agent_runs_guest_expires_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_guest_session_hash", table_name="agent_runs")
    op.drop_index("ix_agent_runs_owner_user_id", table_name="agent_runs")
    op.drop_column("agent_runs", "guest_expires_at")
    op.drop_column("agent_runs", "guest_session_hash")
    op.drop_column("agent_runs", "owner_user_id")
