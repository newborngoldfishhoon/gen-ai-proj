import React from 'react';
import type { Source } from '../types/agent';
import { ExternalLink, Globe, FileText, CheckCircle2, Clock, Inbox } from 'lucide-react';

interface SourcePanelProps {
  sources: Source[];
}

export default function SourcePanel({ sources }: SourcePanelProps) {
  if (sources.length === 0) {
    return (
      <div className="glass-card p-8 text-center animate-fade-in">
        <Inbox size={36} className="mx-auto text-surface-600 mb-3" />
        <h3 className="text-sm font-medium text-surface-300 mb-1">No Sources Yet</h3>
        <p className="text-xs text-surface-500">
          When the agent performs web searches or extracts webpages, retrieved sources will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3 animate-fade-in">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-medium text-surface-400 uppercase tracking-wider">
          Retrieved Sources ({sources.length})
        </h3>
        <span className="text-xs text-surface-500">
          Click any source to verify the original webpage
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {sources.map((src, index) => {
          const isExtracted = src.extraction_status === 'extracted';
          return (
            <div
              key={src.id || index}
              className="p-4 rounded-xl border border-surface-700/40 bg-surface-800/40 hover:border-surface-600/60 transition-all duration-200"
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="p-1.5 rounded-lg bg-surface-700/50 text-brand-400 flex-shrink-0">
                    <Globe size={14} />
                  </div>
                  <h4 className="text-sm font-semibold text-surface-100 truncate">
                    {src.title}
                  </h4>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <span
                    className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${
                      isExtracted
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                        : 'bg-blue-500/15 text-blue-400 border border-blue-500/20'
                    }`}
                  >
                    {isExtracted ? (
                      <>
                        <CheckCircle2 size={10} />
                        Page Extracted
                      </>
                    ) : (
                      <>
                        <FileText size={10} />
                        Search Snippet
                      </>
                    )}
                  </span>

                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1 text-surface-400 hover:text-brand-400 transition-colors"
                    title="Open original webpage in new tab"
                  >
                    <ExternalLink size={14} />
                  </a>
                </div>
              </div>

              {src.snippet && (
                <p className="text-xs text-surface-300 leading-relaxed line-clamp-3 mb-2 bg-surface-900/30 p-2.5 rounded-lg border border-surface-700/20">
                  {src.snippet}
                </p>
              )}

              <div className="flex items-center justify-between text-[11px] text-surface-500 pt-1">
                <span className="font-mono text-surface-400">{src.domain}</span>
                {src.created_at && (
                  <span className="flex items-center gap-1">
                    <Clock size={10} />
                    {new Date(src.created_at).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
