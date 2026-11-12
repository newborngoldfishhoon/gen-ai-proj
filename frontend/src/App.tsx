import React, { useState, useEffect, useCallback } from 'react';
import type { RunListItem } from './types/agent';
import api from './services/api';
import GoalInput from './components/GoalInput';
import RunHistory from './components/RunHistory';
import RunDetail from './components/RunDetail';
import { Cpu, AlertTriangle, RefreshCw } from 'lucide-react';

type View = { type: 'dashboard' } | { type: 'detail'; runId: string };

export default function App() {
  const [view, setView] = useState<View>({ type: 'dashboard' });
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingRuns, setIsLoadingRuns] = useState(true);
  const [error, setError] = useState('');

  const fetchRuns = useCallback(async () => {
    try {
      const data = await api.listRuns(20, 0);
      setRuns(data.runs);
      setError('');
    } catch (err) {
      // Only show error if we have no runs cached
      if (runs.length === 0) {
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to connect to the backend'
        );
      }
    } finally {
      setIsLoadingRuns(false);
    }
  }, []);

  useEffect(() => {
    fetchRuns();

    // Poll for updates while on dashboard
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, [fetchRuns]);

  const handleSubmitGoal = async (goal: string) => {
    setIsSubmitting(true);
    setError('');

    try {
      const result = await api.createRun(goal);
      // Navigate to the run detail
      setView({ type: 'detail', runId: result.id });
      // Refresh runs list
      fetchRuns();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to start agent run'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSelectRun = (runId: string) => {
    setView({ type: 'detail', runId });
  };

  const handleBack = () => {
    setView({ type: 'dashboard' });
    fetchRuns();
  };

  return (
    <div className="min-h-screen bg-surface-950">
      {/* Background effect */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-brand-600/8 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-brand-500/5 rounded-full blur-3xl" />
      </div>

      <div className="relative max-w-4xl mx-auto px-4 py-8 md:py-12">
        {/* Header */}
        <header className="text-center mb-10 animate-fade-in">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-brand-600/15 rounded-xl border border-brand-500/20">
              <Cpu size={28} className="text-brand-400" />
            </div>
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight">
              <span className="text-surface-100">Agent</span>
              <span className="text-brand-400">Forge</span>
            </h1>
          </div>
          <p className="text-surface-400 text-sm md:text-base max-w-xl mx-auto leading-relaxed">
            Autonomous AI agent that plans, uses live research tools, extracts verified evidence,
            and delivers citation-backed reports.
          </p>
        </header>

        {/* Main Content */}
        {view.type === 'dashboard' ? (
          <div className="space-y-8">
            {/* Error banner */}
            {error && (
              <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-xl animate-slide-up">
                <AlertTriangle size={18} className="text-red-400 flex-shrink-0" />
                <p className="text-sm text-red-400 flex-1">{error}</p>
                <button
                  onClick={fetchRuns}
                  className="text-red-400 hover:text-red-300 transition-colors"
                  title="Retry"
                >
                  <RefreshCw size={14} />
                </button>
              </div>
            )}

            <GoalInput onSubmit={handleSubmitGoal} isLoading={isSubmitting} />

            <RunHistory
              runs={runs}
              onSelectRun={handleSelectRun}
              isLoading={isLoadingRuns}
            />
          </div>
        ) : (
          <RunDetail runId={view.runId} onBack={handleBack} />
        )}

        {/* Footer */}
        <footer className="mt-16 text-center text-xs text-surface-600">
          <p>AgentForge v0.2.0 — Phase 2: Tool Use & Web Research</p>
          <p className="mt-1">
            Autonomous tool use with live web search, webpage extraction, evidence tracking, and citation-backed reports.
          </p>
        </footer>
      </div>
    </div>
  );
}
