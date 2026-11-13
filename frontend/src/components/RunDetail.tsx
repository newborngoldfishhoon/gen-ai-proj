import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { AgentRun } from '../types/agent';
import api from '../services/api';
import StatusBadge from './StatusBadge';
import TaskCard from './TaskCard';
import ToolTimeline from './ToolTimeline';
import SourcePanel from './SourcePanel';
import ResourcePanel from './ResourcePanel';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { renderToStaticMarkup } from 'react-dom/server';
import { getCategory, type ResourceCategory } from './ResourcePanel';
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
  Compass,
} from 'lucide-react';

interface RunDetailProps {
  runId: string;
  onBack: () => void;
  onRetry: (runId: string) => void;
}

type TabType = 'tasks' | 'timeline' | 'sources' | 'resources' | 'report';
type ExportFormat = 'pdf' | 'markdown' | 'text' | 'html';

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character] || character);
}

function getResourceSummary(source: AgentRun['sources'][number]): string {
  const summary = source.snippet?.trim().replace(/\s+/g, ' ');
  if (!summary) return 'The search result did not provide a summary for this link.';
  return summary.length > 220 ? `${summary.slice(0, 217).trimEnd()}...` : summary;
}

function createReportHtml(title: string, report: string, resources: AgentRun['sources']): string {
  const reportBody = renderToStaticMarkup(
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {report}
    </ReactMarkdown>
  );
  const guideBody = renderToStaticMarkup(
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {createKickstartMarkdown(resources)}
    </ReactMarkdown>
  );
  const escapedTitle = escapeHtml(title);

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapedTitle}</title>
  <style>
    :root { color-scheme: light; font-family: Arial, sans-serif; color: #172033; background: #fff; }
    body { margin: 0; padding: 48px 24px; }
    main { max-width: 820px; margin: 0 auto; }
    section { width: 100%; }
    .kickstart { break-before: page; page-break-before: always; }
    h1 { font-size: 30px; line-height: 1.2; margin: 0 0 24px; letter-spacing: -.03em; }
    h2 { font-size: 20px; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }
    h3 { font-size: 16px; margin: 20px 0 8px; }
    p, li { font-size: 14px; line-height: 1.65; }
    ul, ol { padding-left: 22px; }
    a { color: #175cd3; overflow-wrap: anywhere; }
    table { width: 100%; table-layout: fixed; border-collapse: collapse; margin: 16px 0; font-size: 13px; }
    th, td { border: 1px solid #d0d5dd; padding: 8px 10px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
    th { background: #f2f4f7; }
    blockquote { margin: 16px 0; padding: 4px 14px; border-left: 3px solid #98a2b3; color: #475467; }
    code { font-family: Consolas, monospace; background: #f2f4f7; padding: 2px 4px; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; }
    @page { size: A4; margin: 18mm; }
    @media print { body { padding: 0; } a { color: #175cd3; text-decoration: none; } h2, h3 { break-after: avoid; } table, blockquote { break-inside: avoid; } }
  </style>
</head>
<body><main><section class="report-content">${reportBody}</section><section class="kickstart">${guideBody}</section></main></body>
</html>`;
}

function createKickstartMarkdown(resources: AgentRun['sources']): string {
  const validResources = resources.filter((source) => /^https?:\/\//i.test(source.url));
  const grouped = new Map<ResourceCategory, AgentRun['sources']>();
  for (const resource of validResources) {
    const category = getCategory(resource);
    grouped.set(category, [...(grouped.get(category) || []), resource]);
  }
  const sections = [...grouped.entries()].map(([category, items]) => [
    `## ${category}`,
    '',
    ...items.flatMap((source) => [
      `### [${source.title.replace(/[\\`*_{}[\]()#+.!|>~-]/g, '\\$&')}](${source.url})`,
      '',
      getResourceSummary(source),
      '',
    ]),
  ].join('\n'));
  const resourcesContent = sections.length ? sections.join('\n') : 'No resource links were found for this run.';
  return `# Kickstart Guide\n\nCurated tutorials, courses, opportunities, and useful links related to this research.\n\n${resourcesContent}`;
}

function createCombinedMarkdown(report: string, resources: AgentRun['sources']): string {
  return `${report}\n\n---\n\n${createKickstartMarkdown(resources)}`;
}

function encodeBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

async function createEmbeddedFontStyles(report: HTMLElement, guide: HTMLElement): Promise<string> {
  const fontLinks = Array.from(
    document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"][href]'),
  )
    .map((link) => link.href)
    .filter((href) => new URL(href).hostname === 'fonts.googleapis.com');
  const text = [...new Set(`${report.textContent || ''}${guide.textContent || ''}`)].join('');

  const fontStyles = await Promise.all(fontLinks.map(async (href) => {
    const url = new URL(href);
    url.searchParams.set('text', text);
    const cssResponse = await fetch(url);
    if (!cssResponse.ok) throw new Error('Could not load the report fonts for PDF export.');
    let css = await cssResponse.text();
    const fontUrls = [...new Set(
      Array.from(css.matchAll(/url\((https:\/\/fonts\.gstatic\.com\/[^)]+)\)/g), (match) => match[1]),
    )];
    for (const fontUrl of fontUrls) {
      const fontResponse = await fetch(fontUrl);
      if (!fontResponse.ok) throw new Error('Could not load the report fonts for PDF export.');
      const fontBytes = new Uint8Array(await fontResponse.arrayBuffer());
      const dataUrl = `data:font/woff2;base64,${encodeBase64(fontBytes)}`;
      css = css.split(fontUrl).join(dataUrl);
    }
    return css;
  }));
  return fontStyles.join('\n');
}

async function inlineReportImages(...elements: HTMLElement[]): Promise<void> {
  const images = elements.flatMap((element) =>
    Array.from(element.querySelectorAll<HTMLImageElement>('img[src]')),
  );
  await Promise.all(images.map(async (image) => {
    const source = image.currentSrc || image.src;
    if (source.startsWith('data:')) return;
    const response = await fetch(source);
    if (!response.ok) throw new Error('Could not load a report image for PDF export.');
    const imageBlob = await response.blob();
    if (!imageBlob.type.startsWith('image/')) {
      throw new Error('A report image has an unsupported format for PDF export.');
    }
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === 'string') resolve(reader.result);
        else reject(new Error('Could not embed a report image for PDF export.'));
      };
      reader.onerror = () => reject(new Error('Could not embed a report image for PDF export.'));
      reader.readAsDataURL(imageBlob);
    });
    image.src = dataUrl;
    image.removeAttribute('srcset');
    image.removeAttribute('sizes');
    image.loading = 'eager';
    await image.decode();
  }));
}

async function createPdfExportHtml(): Promise<string> {
  await document.fonts.ready;
  const reportElement = document.querySelector<HTMLElement>('[data-pdf-export-report]');
  const guideElement = document.querySelector<HTMLElement>('[data-pdf-export-guide]');
  if (!reportElement || !guideElement) {
    throw new Error('Open the Final Report tab before exporting the PDF.');
  }

  const report = reportElement.cloneNode(true) as HTMLElement;
  report.querySelector('[data-pdf-export-toolbar]')?.remove();
  report.querySelector('[role="alert"]')?.remove();
  const guide = guideElement.cloneNode(true) as HTMLElement;
  await inlineReportImages(report, guide);
  const fontStyles = await createEmbeddedFontStyles(report, guide);

  const styles: string[] = [];
  for (const sheet of Array.from(document.styleSheets)) {
    const host = sheet.href ? new URL(sheet.href).hostname : '';
    if (host === 'fonts.googleapis.com') continue;
    try {
      styles.push(Array.from(sheet.cssRules, (rule) => rule.cssText).join('\n'));
    } catch {
      throw new Error('Could not prepare the report styles for PDF export.');
    }
  }

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    ${fontStyles}
    ${styles.join('\n')}
    @page { size: A4; margin: 14mm 14mm 18mm; }
    *, *::before, *::after {
      animation: none !important;
      transition: none !important;
      scroll-behavior: auto !important;
    }
    html, body { min-height: 0; margin: 0; background: #fff !important; }
    body { font-family: Inter, system-ui, sans-serif; color: #172033; }
    .pdf-document { width: 100%; max-width: 896px; margin: 0 auto; }
    .report-card { overflow: visible !important; }
    .report-paper, .resource-guide {
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }
    .resource-guide { break-before: page; page-break-before: always; }
    .markdown-content table {
      display: table !important;
      width: 100% !important;
      table-layout: fixed;
      overflow: visible !important;
      border-collapse: collapse;
    }
    .markdown-content th, .markdown-content td { overflow-wrap: anywhere; }
    .markdown-content thead { display: table-header-group; }
    .markdown-content tr, .resource-link-card, .resource-guide > header,
    .markdown-content blockquote, .markdown-content pre {
      break-inside: avoid-page;
      page-break-inside: avoid;
    }
    .report-paper h1, .report-paper h2, .report-paper h3 {
      break-after: avoid-page;
      page-break-after: avoid;
    }
    img, svg { max-width: 100%; }
    a { color: #175cd3; }
  </style>
</head>
<body class="pdf-export">
  <main class="pdf-document">${report.outerHTML}${guide.outerHTML}</main>
</body>
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
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [exportFormat, setExportFormat] = useState<ExportFormat>('pdf');
  const pollRef = useRef<number | null>(null);
  const exportResourceTask = run?.tasks.find((task) => task.title === 'Resource research');
  const exportResources = exportResourceTask
    ? run?.sources.filter((source) => source.task_id === exportResourceTask.id) || []
    : [];

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

  const handleDownloadReport = async () => {
    if (!run?.final_report) return;
    const safeGoal = run.goal.slice(0, 60).replace(/[<>:"/\\|?*\x00-\x1f]/g, '-').trim();
    const baseName = `agentforge-report-${safeGoal || run.id.slice(0, 8)}`;
    const combinedMarkdown = createCombinedMarkdown(run.final_report, exportResources);
    setExportError('');
    if (exportFormat === 'pdf') {
      if (isExportingPdf) return;
      setIsExportingPdf(true);
      try {
        const html = await createPdfExportHtml();
        const blob = await api.exportRunPdf(run.id, html);
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${baseName}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (err) {
        setExportError(err instanceof Error ? `PDF export failed: ${err.message}` : 'PDF export failed.');
      } finally {
        setIsExportingPdf(false);
      }
      return;
    }

    const html = createReportHtml(baseName, run.final_report, exportResources);
    const content = exportFormat === 'markdown'
      ? combinedMarkdown
      : exportFormat === 'text'
      ? combinedMarkdown
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
  const uniqueSources = [...new Map(sources.map((source) => [source.url, source])).values()];
  const resourceTask = exportResourceTask;
  const resourceSources = exportResources;
  const workflowPhase = finalPass?.status === 'in_progress'
    ? {
        title: 'Formatting report',
        description: 'Research is complete. Findings and citations are being formatted into the report.',
        icon: <Sparkles size={16} className="text-violet-300" />,
        tone: 'border-violet-400/20 bg-violet-500/5',
      }
    : finalPass?.status === 'completed' || run.status === 'completed'
    ? {
        title: 'Research complete',
        description: 'Your research answer and practical resource links are ready.',
        icon: <Check size={16} className="text-emerald-300" />,
        tone: 'border-emerald-400/20 bg-emerald-500/5',
      }
    : activeCount > 0
    ? {
        title: 'Researching',
        description: 'The answer research and resource search are running in parallel.',
        icon: <Layers3 size={16} className="text-blue-300" />,
        tone: 'border-blue-400/20 bg-blue-500/5',
      }
    : {
        title: 'Starting research',
        description: 'Preparing the answer and a separate search for tutorials, courses, and useful links.',
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
              {uniqueSources.length}
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
          Sources ({uniqueSources.length})
        </button>

        {resourceTask && (
          <button
            onClick={() => setActiveTab('resources')}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'resources'
                ? 'border-brand-500 text-brand-300'
                : 'border-transparent text-surface-400 hover:text-surface-200'
            }`}
          >
            <Compass size={16} />
            Kickstart ({resourceSources.length})
          </button>
        )}

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
        <SourcePanel sources={uniqueSources} />
      )}

      {activeTab === 'resources' && resourceTask && (
        <ResourcePanel sources={resourceSources} taskStatus={resourceTask.status} />
      )}

      {activeTab === 'report' && run.final_report && (
        <div className="report-card overflow-hidden animate-fade-in" data-pdf-export-report>
          <div className="p-4 bg-surface-800/80 border-b border-surface-700/40 flex items-center justify-between gap-3" data-pdf-export-toolbar>
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
                <option value="pdf">PDF document</option>
                <option value="markdown">Markdown</option>
                <option value="text">Plain text</option>
                <option value="html">HTML</option>
              </select>
              <button
                onClick={handleDownloadReport}
                className="btn-primary text-xs py-1.5 px-3"
                title={exportFormat === 'pdf' ? 'Download the complete report as a PDF' : `Download ${exportFormat} report`}
                disabled={exportFormat === 'pdf' && isExportingPdf}
              >
                {isExportingPdf ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />}
                {isExportingPdf ? 'Preparing PDF…' : exportFormat === 'pdf' ? 'Export PDF' : `Export ${exportFormat.toUpperCase()}`}
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
      {activeTab === 'report' && run.final_report && resourceTask && (
        <ResourcePanel
          sources={resourceSources}
          taskStatus={resourceTask.status}
          printable
          exportTarget
        />
      )}
    </div>
  );
}
