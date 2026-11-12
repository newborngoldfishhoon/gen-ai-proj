import React, { useState } from 'react';
import type { ToolCall } from '../types/agent';
import {
  Search,
  Calculator,
  FileText,
  Terminal,
  CheckCircle2,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Inbox,
  Clock,
} from 'lucide-react';

interface ToolTimelineProps {
  toolCalls: ToolCall[];
}

function getToolIcon(name: string) {
  switch (name) {
    case 'web_search':
      return <Search size={14} className="text-blue-400" />;
    case 'extract_webpage':
      return <FileText size={14} className="text-purple-400" />;
    case 'calculator':
      return <Calculator size={14} className="text-amber-400" />;
    default:
      return <Terminal size={14} className="text-brand-400" />;
  }
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '';
  if (!end) return 'Running...';
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function parseArguments(raw: string): string {
  try {
    const parsed = JSON.parse(raw);
    if (parsed.query) return `Query: "${parsed.query}"`;
    if (parsed.url) return `URL: ${parsed.url}`;
    if (parsed.expression) return `Expr: ${parsed.expression}`;
    return Object.entries(parsed)
      .map(([k, v]) => `${k}=${v}`)
      .join(', ');
  } catch {
    return raw;
  }
}

export default function ToolTimeline({ toolCalls }: ToolTimelineProps) {
  const [expandedCalls, setExpandedCalls] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpandedCalls((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (toolCalls.length === 0) {
    return (
      <div className="glass-card p-8 text-center animate-fade-in">
        <Inbox size={36} className="mx-auto text-surface-600 mb-3" />
        <h3 className="text-sm font-medium text-surface-300 mb-1">No Tool Calls Yet</h3>
        <p className="text-xs text-surface-500">
          When tasks invoke web search, webpage extraction, or the calculator, real-time activity will stream here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3 animate-fade-in">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-medium text-surface-400 uppercase tracking-wider">
          Tool Execution Timeline ({toolCalls.length})
        </h3>
        <span className="text-xs text-surface-500">Chronological backend tool dispatches</span>
      </div>

      <div className="relative pl-6 space-y-3 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-surface-700/50">
        {toolCalls.map((tc, idx) => {
          const isExpanded = expandedCalls.has(tc.id);
          const isRunning = tc.status === 'running' || tc.status === 'pending';
          const isCompleted = tc.status === 'completed';
          const isFailed = tc.status === 'failed';

          return (
            <div key={tc.id || idx} className="relative group">
              {/* Timeline marker node */}
              <div
                className={`absolute -left-6 top-3.5 w-5 h-5 rounded-full flex items-center justify-center border text-[10px] ${
                  isRunning
                    ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                    : isCompleted
                    ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400'
                    : 'bg-red-500/20 border-red-500/40 text-red-400'
                }`}
              >
                {isRunning ? (
                  <Loader2 size={10} className="animate-spin" />
                ) : isCompleted ? (
                  <CheckCircle2 size={10} />
                ) : (
                  <XCircle size={10} />
                )}
              </div>

              {/* Tool Card */}
              <div
                className={`rounded-xl border transition-all duration-200 overflow-hidden ${
                  isRunning
                    ? 'border-blue-500/30 bg-blue-500/5'
                    : isFailed
                    ? 'border-red-500/20 bg-red-500/5'
                    : 'border-surface-700/40 bg-surface-800/40 hover:border-surface-600/60'
                }`}
              >
                <button
                  onClick={() => toggleExpand(tc.id)}
                  className="w-full p-3.5 flex items-start justify-between gap-3 text-left hover:bg-surface-700/10 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="p-1 rounded-md bg-surface-700/50 flex-shrink-0">
                        {getToolIcon(tc.tool_name)}
                      </div>
                      <span className="text-xs font-bold text-surface-200 font-mono">
                        {tc.tool_name}
                      </span>
                      {tc.started_at && (
                        <span className="text-[11px] text-surface-500 flex items-center gap-1">
                          <Clock size={10} />
                          {formatDuration(tc.started_at, tc.completed_at)}
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-brand-300/90 font-mono truncate mb-1">
                      {parseArguments(tc.arguments)}
                    </p>

                    {tc.result_summary && (
                      <p className="text-xs text-surface-400 truncate">
                        {tc.result_summary}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0 pt-1">
                    <span
                      className={`text-[10px] font-medium px-2 py-0.5 rounded-full uppercase tracking-wider ${
                        isRunning
                          ? 'bg-blue-500/15 text-blue-400'
                          : isCompleted
                          ? 'bg-emerald-500/15 text-emerald-400'
                          : 'bg-red-500/15 text-red-400'
                      }`}
                    >
                      {tc.status}
                    </span>
                    {isExpanded ? (
                      <ChevronUp size={14} className="text-surface-500" />
                    ) : (
                      <ChevronDown size={14} className="text-surface-500" />
                    )}
                  </div>
                </button>

                {/* Expanded details */}
                {isExpanded && (
                  <div className="px-3.5 pb-3.5 pt-0 border-t border-surface-700/30 text-xs">
                    <div className="pt-2.5 space-y-2">
                      <div>
                        <span className="text-surface-500 uppercase tracking-wider text-[10px] block mb-1">
                          Full Arguments
                        </span>
                        <pre className="bg-surface-900/50 p-2 rounded border border-surface-700/30 text-surface-300 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap">
                          {tc.arguments}
                        </pre>
                      </div>

                      {tc.result_data && (
                        <div>
                          <span className="text-surface-500 uppercase tracking-wider text-[10px] block mb-1">
                            Result Data
                          </span>
                          <pre className="bg-surface-900/50 p-2.5 rounded border border-surface-700/30 text-surface-300 font-mono text-[11px] max-h-48 overflow-y-auto whitespace-pre-wrap">
                            {tc.result_data}
                          </pre>
                        </div>
                      )}

                      {tc.error_message && (
                        <div className="p-2.5 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                          <span className="font-semibold">Error: </span>
                          {tc.error_message}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
