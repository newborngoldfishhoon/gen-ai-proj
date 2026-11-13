import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { AgentRun } from '../types/agent';
import api from '../services/api';
import StatusBadge from './StatusBadge';
import TaskCard from './TaskCard';
import ToolTimeline from './ToolTimeline';
import SourcePanel from './SourcePanel';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  ArrowLeft,
  FileText,
  Target,
  AlertTriangle,
  Clock,
  Wrench,
  Globe,
  ListTodo,
  Copy,
  Check,
  Download,
  Layers3,
  Sparkles,
  RefreshCw,
} from 'lucide-react';

interface RunDetailProps {
  runId: string;
  onBack: () => void;
  onRetry: (runId: string) => void;
}

type TabType = 'tasks' | 'timeline' | 'sources' | 'report';
type ExportFormat = 'markdown' | 'text' | 'html' | 'pdf';

function createReportHtml(title: string, report: string): string {
  const body = renderToStaticMarkup(
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
  );
  const escapedTitle = title.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character] || character);

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapedTitle}</title>
  <style>
    :root { color-scheme: light; font-family: Inter, Arial, sans-serif; color: #172033; background: #fff; }
    body { margin: 0; padding: 48px 24px; }
    main { max-width: 820px; margin: 0 auto; }
    h1 { font-size: 30px; line-height: 1.2; margin: 0 0 24px; letter-spacing: -.03em; }
    h2 { font-size: 20px; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }
    h3 { font-size: 16px; margin: 20px 0 8px; }
    p, li { font-size: 14px; line-height: 1.65; }
    ul, ol { padding-left: 22px; }
    a { color: #175cd3; overflow-wrap: anywhere; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }
    th, td { border: 1px solid #d0d5dd; padding: 8px 10px; text-align: left; vertical-align: top; }
    th { background: #f2f4f7; }
    blockquote { margin: 16px 0; padding: 4px 14px; border-left: 3px solid #98a2b3; color: #475467; }
    code { font-family: Consolas, monospace; background: #f2f4f7; padding: 2px 4px; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; }
    @page { size: A4; margin: 18mm; }
    @media print { body { padding: 0; } a { color: #175cd3; text-decoration: none; } h2, h3 { break-after: avoid; } table, blockquote { break-inside: avoid; } }
  </style>
</head>
<body><main>${body}</main></body>
</html>`;
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleString();
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return 'In progress...';
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remainSecs = secs % 60;
  return `${mins}m ${remainSecs}s`;
}

export default function RunDetail({ runId, onBack, onRetry }: RunDetailProps) {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [error, setError] = useState<string>('');
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState<TabType>('tasks');
  const [copied, setCopied] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState('');
  const [exportError, setExportError] = useState('');
  const [exportFormat, setExportFormat] = useState<ExportFormat>('markdown');
  const pollRef = useRef<number | null>(null);

  const fetchRun = useCallback(async () => {
    try {
      const data = await api.getRun(runId);
      setRun(data);
      setError('');

      // Auto-switch to report tab on first completion
      if (data.status === 'completed' && data.final_report && activeTab === 'tasks') {
        // Keep current tab, but notify user
      }

      // Stop polling when terminal
      if (data.status === 'completed' || data.status === 'failed') {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run');
    }
  }, [runId, activeTab]);

  useEffect(() => {
    fetchRun();

    // Poll every 2 seconds while active
    pollRef.current = window.setInterval(fetchRun, 2000);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [fetchRun]);

  const toggleTask = (taskId: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  const handleCopyReport = async () => {
    if (!run?.final_report) return;
    try {
      await navigator.clipboard.writeText(run.final_report);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy report:', err);
    }
  };

  const handleDownloadReport = () => {
    if (!run?.final_report) return;
    const safeGoal = run.goal.slice(0, 60).replace(/[<>:"/\\|?*\x00-\x1f]/g, '-').trim();
    const baseName = `agentforge-report-${safeGoal || run.id.slice(0, 8)}`;
    if (exportFormat === 'pdf') {
      setExportError('');
      const printWindow = window.open('', '_blank');
      if (!printWindow) {
        setExportError('Allow pop-ups to print or save the report as a PDF.');
        return;
      }
      printWindow.document.open();
      printWindow.document.write(createReportHtml(baseName, run.final_report));
      printWindow.document.close();
      window.setTimeout(() => {
        printWindow.focus();
        printWindow.print();
      }, 250);
      return;
    }

    const html = createReportHtml(baseName, run.final_report);
    const content = exportFormat === 'markdown'
      ? run.final_report
      : exportFormat === 'text'
      ? run.final_report
          .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
          .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1 ($2)')
          .replace(/^#{1,6}\s+/gm, '')
          .replace(/[*_`~]/g, '')
      : html;
    const mimeType = exportFormat === 'html'
      ? 'text/html;charset=utf-8'
      : exportFormat === 'text'
      ? 'text/plain;charset=utf-8'
      : 'text/markdown;charset=utf-8';
    const extension = exportFormat === 'html' ? 'html' : exportFormat === 'text' ? 'txt' : 'md';
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${baseName}.${extension}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handleRetry = async () => {
    if (!run || retrying) return;
    setRetrying(true);
    setRetryError('');
    try {
      const retriedRun = await api.retryRun(run.id);
      onRetry(retriedRun.id);
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : 'Failed to retry this run');
      setRetrying(false);
    }
  };

  if (error && !run) {
    return (
      <div className="glass-card p-8 text-center animate-fade-in">
        <AlertTriangle size={40} className="mx-auto text-red-400 mb-3" />
        <p className="text-red-400 mb-4">{error}</p>
        <button onClick={onBack} className="btn-secondary">
          <ArrowLeft size={16} />
          Back to Dashboard
        </button>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="glass-card p-8 animate-fade-in">
        <div className="space-y-4">
          <div className="h-8 bg-surface-700/30 rounded-lg shimmer w-3/4" />
          <div className="h-4 bg-surface-700/30 rounded shimmer w-1/2" />
          <div className="space-y-3 mt-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-surface-700/30 rounded-xl shimmer" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const completedCount = run.tasks.filter((t) => t.status === 'completed').length;
  const activeCount = run.tasks.filter((t) => t.status === 'in_progress').length;
  const finalPass = run.tasks.find((task) => task.title === 'Final Report');
  const parallelTasks = run.tasks.filter(
    (task) => task.title !== 'Final Report'
  );
  const totalTasks = run.tasks.length;
  const progressPercent = totalTasks > 0 ? (completedCount / totalTasks) * 100 : 0;
  const toolCalls = run.tool_calls || [];
  const sources = run.sources || [];
  const workflowPhase = finalPass?.status === 'in_progress'
    ? {
        title: 'Formatting report',
        description: 'Research is complete. Findings and citations are being formatted into the report.',
        icon: <Sparkles size={16} className="text-violet-300" />,
        tone: 'border-violet-400/20 bg-violet-500/5',
      }
    : finalPass?.status === 'completed' || run.status === 'completed'
    ? {
        title: 'Fast research complete',
        description: 'The research answer and source list are ready.',
        icon: <Check size={16} className="text-emerald-300" />,
        tone: 'border-emerald-400/20 bg-emerald-500/5',
      }
    : activeCount > 0
    ? {
        title: 'Researching',
        description: 'One focused research task is running with a single search to return results faster.',
        icon: <Layers3 size={16} className="text-blue-300" />,
        tone: 'border-blue-400/20 bg-blue-500/5',
      }
    : {
        title: 'Starting fast research',
        description: 'Preparing one focused research task; the answer and source list are formatted without extra synthesis.',
        icon: <Layers3 size={16} className="text-brand-300" />,
        tone: 'border-brand-400/20 bg-brand-500/5',
      };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Run Summary Card */}
      <div className="glass-card p-6">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-surface-400 hover:text-surface-200 transition-colors mb-4"
        >
          <ArrowLeft size={14} />
          Back to Dashboard
        </button>

        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <Target size={18} className="text-brand-400 flex-shrink-0" />
              <h1 className="text-xl font-bold text-surface-100 truncate">
                {run.goal}
              </h1>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-xs text-surface-500">
              <span className="flex items-center gap-1">
                <Clock size={12} />
                Started {formatDateTime(run.created_at)}
              </span>
              {run.completed_at && (
                <span>
                  Duration: {formatDuration(run.created_at, run.completed_at)}
                </span>
              )}
            </div>
          </div>
          <StatusBadge status={run.status} />
        </div>

        {/* Metric Badges */}
        <div className="grid grid-cols-3 gap-3 mt-5 pt-4 border-t border-surface-700/30 text-center">
          <div className="p-2.5 rounded-xl bg-surface-900/40 border border-surface-700/20">
            <span className="text-[11px] text-surface-400 block uppercase tracking-wider mb-0.5">
              Tasks
            </span>
            <span className="text-lg font-bold text-surface-100">
              {completedCount} / {totalTasks}
            </span>
          </div>

          <div className="p-2.5 rounded-xl bg-surface-900/40 border border-surface-700/20">
            <span className="text-[11px] text-surface-400 block uppercase tracking-wider mb-0.5">
              Tool Calls
            </span>
            <span className="text-lg font-bold text-brand-300">
              {toolCalls.length}
            </span>
          </div>

          <div className="p-2.5 rounded-xl bg-surface-900/40 border border-surface-700/20">
            <span className="text-[11px] text-surface-400 block uppercase tracking-wider mb-0.5">
              Sources Verified
            </span>
            <span className="text-lg font-bold text-emerald-400">
              {sources.length}
            </span>
          </div>
        </div>

        {/* Progress bar */}
        {totalTasks > 0 && (
          <div className="mt-4">
            <div className="h-1.5 bg-surface-700/50 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  run.status === 'failed'
                    ? 'bg-red-500'
                    : run.status === 'completed'
                    ? 'bg-emerald-500'
                    : 'bg-brand-500'
                }`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        )}

        {/* Error message */}
        {(run.error_message || run.status === 'failed') && (
          <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
              {run.error_message && (
                <p className="text-sm text-red-400">{run.error_message}</p>
              )}
            </div>
            {run.status === 'failed' && (
              <button
                onClick={handleRetry}
                disabled={retrying}
                className="btn-secondary mt-3 text-xs py-1.5 px-3 disabled:opacity-50"
              >
                <RefreshCw size={13} className={retrying ? 'animate-spin' : ''} />
                {retrying ? 'Starting retry…' : 'Retry this run'}
              </button>
            )}
            {retryError && (
              <p role="alert" className="mt-2 text-xs text-red-300">{retryError}</p>
            )}
          </div>
        )}
        {retryError && !run.error_message && (
          <p role="alert" className="mt-2 text-xs text-red-300">{retryError}</p>
        )}
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-1 border-b border-surface-700/50 px-1 overflow-x-auto">
        <button
          onClick={() => setActiveTab('tasks')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
            activeTab === 'tasks'
              ? 'border-brand-500 text-brand-300'
              : 'border-transparent text-surface-400 hover:text-surface-200'
          }`}
        >
          <ListTodo size={16} />
          Tasks ({totalTasks})
        </button>

        <button
          onClick={() => setActiveTab('timeline')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
            activeTab === 'timeline'
              ? 'border-brand-500 text-brand-300'
              : 'border-transparent text-surface-400 hover:text-surface-200'
          }`}
        >
          <Wrench size={16} />
          Tool Activity ({toolCalls.length})
        </button>

        <button
          onClick={() => setActiveTab('sources')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
            activeTab === 'sources'
              ? 'border-brand-500 text-brand-300'
              : 'border-transparent text-surface-400 hover:text-surface-200'
          }`}
        >
          <Globe size={16} />
          Sources ({sources.length})
        </button>

        {run.final_report && (
          <button
            onClick={() => setActiveTab('report')}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'report'
                ? 'border-brand-500 text-brand-300'
                : 'border-transparent text-surface-400 hover:text-surface-200'
            }`}
          >
            <FileText size={16} />
            Final Report
          </button>
        )}
      </div>

      {/* Tab Panels */}
      {activeTab === 'tasks' && (
        <div className="space-y-2 animate-fade-in">
          {run.status === 'running' && (
            <div className={`flex items-start gap-3 p-4 mb-4 rounded-xl border ${workflowPhase.tone}`}>
              <div className="mt-0.5">{workflowPhase.icon}</div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-surface-100">{workflowPhase.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-surface-400">
                  {workflowPhase.description}
                </p>
              </div>
              {activeCount > 1 && (
                <span className="ml-auto flex-shrink-0 rounded-full bg-blue-400/10 px-2.5 py-1 text-[11px] font-medium text-blue-200">
                  {activeCount} simultaneous
                </span>
              )}
            </div>
          )}

          {parallelTasks.length > 0 && (
            <div className="flex items-center gap-2 px-1 pt-1 pb-2 text-xs font-semibold uppercase tracking-wider text-surface-400">
              <Layers3 size={13} className="text-blue-300" />
              Research
              <span className="text-surface-600">({parallelTasks.length})</span>
            </div>
          )}
          {parallelTasks
            .slice()
            .sort((a, b) => a.order_index - b.order_index)
            .map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                index={task.order_index}
                isExpanded={expandedTasks.has(task.id)}
                onToggle={() => toggleTask(task.id)}
              />
            ))}

          {finalPass && (
            <>
              <div className="flex items-center gap-2 px-1 pt-4 pb-2 text-xs font-semibold uppercase tracking-wider text-surface-400">
                <Sparkles size={13} className="text-violet-300" />
                Final Report
              </div>
              <TaskCard
                key={finalPass.id}
                task={finalPass}
                index={finalPass.order_index}
                isExpanded={expandedTasks.has(finalPass.id)}
                onToggle={() => toggleTask(finalPass.id)}
              />
            </>
          )}
        </div>
      )}

      {activeTab === 'timeline' && (
        <ToolTimeline toolCalls={toolCalls} />
      )}

      {activeTab === 'sources' && (
        <SourcePanel sources={sources} />
      )}

      {activeTab === 'report' && run.final_report && (
        <div className="report-card overflow-hidden animate-fade-in">
          <div className="p-4 bg-surface-800/80 border-b border-surface-700/40 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <FileText size={18} className="text-brand-400" />
              <h3 className="text-base font-semibold text-surface-100">
                Synthesized Research Report
              </h3>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleCopyReport}
                className="btn-secondary text-xs py-1.5 px-3"
                title="Copy report markdown to clipboard"
              >
                {copied ? (
                  <>
                    <Check size={14} className="text-emerald-400" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy size={14} />
                    Copy Markdown
                  </>
                )}
              </button>

              <label className="sr-only" htmlFor="report-export-format">Report export format</label>
              <select
                id="report-export-format"
                value={exportFormat}
                onChange={(event) => setExportFormat(event.target.value as ExportFormat)}
                className="rounded-lg border border-surface-600/50 bg-surface-700/50 px-2.5 py-1.5 text-xs text-surface-200 focus:outline-none focus:ring-2 focus:ring-brand-500/40"
              >
                <option value="markdown">Markdown</option>
                <option value="text">Plain text</option>
                <option value="html">HTML</option>
                <option value="pdf">PDF / Print</option>
              </select>
              <button
                onClick={handleDownloadReport}
                className="btn-secondary text-xs py-1.5 px-3"
                title={exportFormat === 'pdf' ? 'Print or save the report as a PDF' : `Download ${exportFormat} report`}
              >
                <Download size={14} />
                {exportFormat === 'pdf' ? 'Print / PDF' : 'Export'}
              </button>
            </div>
          </div>

          {exportError && (
            <p role="alert" className="px-4 pt-3 text-sm text-red-600">{exportError}</p>
          )}
          <div className="report-paper p-6 md:p-10 markdown-content text-sm leading-relaxed">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ node, ...props }) => (
                  <a
                    {...props}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-700 hover:text-blue-900 underline font-medium"
                  />
                ),
              }}
            >
              {run.final_report}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}
