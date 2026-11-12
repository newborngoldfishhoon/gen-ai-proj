import React from 'react';
import type { RunListItem } from '../types/agent';
import StatusBadge from './StatusBadge';
import { Clock, ChevronRight, Inbox } from 'lucide-react';

interface RunHistoryProps {
  runs: RunListItem[];
  onSelectRun: (runId: string) => void;
  isLoading: boolean;
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export default function RunHistory({
  runs,
  onSelectRun,
  isLoading,
}: RunHistoryProps) {
  if (isLoading) {
    return (
      <div className="glass-card p-6">
        <h3 className="text-sm font-medium text-surface-400 uppercase tracking-wider mb-4">
          Recent Runs
        </h3>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-surface-700/30 rounded-xl shimmer" />
          ))}
        </div>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="glass-card p-8 text-center">
        <Inbox size={40} className="mx-auto text-surface-600 mb-3" />
        <h3 className="text-sm font-medium text-surface-400 mb-1">
          No runs yet
        </h3>
        <p className="text-xs text-surface-500">
          Submit a goal above to start your first agent run.
        </p>
      </div>
    );
  }

  return (
    <div className="glass-card p-6">
      <h3 className="text-sm font-medium text-surface-400 uppercase tracking-wider mb-4">
        Recent Runs
      </h3>
      <div className="space-y-2">
        {runs.map((run) => (
          <button
            key={run.id}
            id={`run-${run.id}`}
            onClick={() => onSelectRun(run.id)}
            className="w-full text-left p-4 rounded-xl bg-surface-800/30 hover:bg-surface-700/40
                       border border-surface-700/30 hover:border-surface-600/50
                       transition-all duration-200 group"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-surface-200 font-medium truncate mb-1.5">
                  {run.goal}
                </p>
                <div className="flex items-center gap-3">
                  <StatusBadge status={run.status} size="sm" />
                  <span className="text-xs text-surface-500 flex items-center gap-1">
                    <Clock size={10} />
                    {formatRelativeTime(run.created_at)}
                  </span>
                  {run.task_count > 0 && (
                    <span className="text-xs text-surface-500">
                      {run.completed_task_count}/{run.task_count} tasks
                    </span>
                  )}
                  {run.tool_call_count !== undefined && run.tool_call_count > 0 && (
                    <span className="text-xs text-brand-400 font-mono">
                      {run.tool_call_count} tools
                    </span>
                  )}
                  {run.source_count !== undefined && run.source_count > 0 && (
                    <span className="text-xs text-emerald-400">
                      {run.source_count} sources
                    </span>
                  )}
                </div>
              </div>
              <ChevronRight
                size={16}
                className="text-surface-600 group-hover:text-surface-400 mt-0.5 transition-colors"
              />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
