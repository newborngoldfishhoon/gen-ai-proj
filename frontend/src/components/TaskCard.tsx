import React from 'react';
import type { AgentTask } from '../types/agent';
import StatusBadge from './StatusBadge';
import { ChevronDown, ChevronUp, Search, Calculator, FileText, Terminal, Wrench } from 'lucide-react';

interface TaskCardProps {
  task: AgentTask;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}

function getToolMiniIcon(name: string) {
  switch (name) {
    case 'web_search':
      return <Search size={10} className="text-blue-400" />;
    case 'extract_webpage':
      return <FileText size={10} className="text-purple-400" />;
    case 'calculator':
      return <Calculator size={10} className="text-amber-400" />;
    default:
      return <Terminal size={10} className="text-brand-400" />;
  }
}

export default function TaskCard({
  task,
  index,
  isExpanded,
  onToggle,
}: TaskCardProps) {
  const isActive = task.status === 'in_progress';
  const isCompleted = task.status === 'completed';
  const isFailed = task.status === 'failed';
  const toolCalls = task.tool_calls || [];

  return (
    <div
      id={`task-${task.id}`}
      className={`rounded-xl border transition-all duration-300 overflow-hidden ${
        isActive
          ? 'border-blue-500/30 bg-blue-500/5 shadow-md shadow-blue-500/5'
          : isFailed
          ? 'border-red-500/20 bg-red-500/5'
          : isCompleted
          ? 'border-emerald-500/10 bg-surface-800/30'
          : 'border-surface-700/30 bg-surface-800/20'
      }`}
    >
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-surface-700/10 transition-colors"
      >
        {/* Step number */}
        <div
          className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${
            isActive
              ? 'bg-blue-500/20 text-blue-400'
              : isCompleted
              ? 'bg-emerald-500/15 text-emerald-400'
              : isFailed
              ? 'bg-red-500/15 text-red-400'
              : 'bg-surface-700/50 text-surface-400'
          }`}
        >
          {index + 1}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <h4
              className={`text-sm font-semibold truncate ${
                isActive ? 'text-surface-100' : 'text-surface-200'
              }`}
            >
              {task.title}
            </h4>
          </div>
          <p className="text-xs text-surface-400 truncate mb-1">
            {task.description}
          </p>

          {/* Inline tool badges if any were executed in this task */}
          {toolCalls.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              {toolCalls.map((tc, i) => (
                <span
                  key={tc.id || i}
                  className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-700/40 text-surface-300 border border-surface-600/30"
                  title={tc.result_summary || tc.tool_name}
                >
                  {getToolMiniIcon(tc.tool_name)}
                  {tc.tool_name}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <StatusBadge status={task.status} size="sm" />
          {(task.result || task.error_message || toolCalls.length > 0) && (
            isExpanded ? (
              <ChevronUp size={14} className="text-surface-500" />
            ) : (
              <ChevronDown size={14} className="text-surface-500" />
            )
          )}
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4 pt-0 border-t border-surface-700/30 mt-0">
          <div className="pt-3 space-y-3">
            {/* Tool activity for this task */}
            {toolCalls.length > 0 && (
              <div className="p-2.5 rounded-lg bg-surface-900/40 border border-surface-700/30">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-surface-300 mb-2">
                  <Wrench size={12} className="text-brand-400" />
                  Tool Activity in this Task ({toolCalls.length})
                </div>
                <div className="space-y-1.5">
                  {toolCalls.map((tc, idx) => (
                    <div
                      key={tc.id || idx}
                      className="text-xs text-surface-400 flex items-start gap-2 bg-surface-800/40 p-2 rounded"
                    >
                      <div className="pt-0.5">{getToolMiniIcon(tc.tool_name)}</div>
                      <div className="flex-1 min-w-0">
                        <span className="font-mono text-brand-300 font-medium">
                          {tc.tool_name}
                        </span>
                        {tc.result_summary && (
                          <span className="text-surface-300 ml-1.5 block sm:inline">
                            — {tc.result_summary}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Task text result */}
            {task.result && (
              <div>
                <div className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-1.5">
                  {isFailed ? 'Task Error' : 'Task Findings'}
                </div>
                <div className={`text-sm leading-relaxed whitespace-pre-wrap p-4 rounded-lg max-h-[400px] overflow-y-auto border ${
                  isFailed
                    ? 'text-amber-300 bg-amber-500/10 border-amber-500/20'
                    : 'text-surface-300 bg-surface-800/50 border-surface-700/20'
                }`}>
                  {task.result}
                </div>
              </div>
            )}

            {task.error_message && (
              <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 p-3 rounded-lg">
                <span className="font-semibold uppercase tracking-wider">Technical detail: </span>
                {task.error_message.replace(/Client error '[^']*' for url '[^']*'/g, 'AI provider API error')}
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  );
}
