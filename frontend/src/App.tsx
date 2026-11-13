import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Session } from '@supabase/supabase-js';
import type { RunListItem } from './types/agent';
import api from './services/api';
import GoalInput from './components/GoalInput';
import LoginGate from './components/LoginGate';
import RunHistory from './components/RunHistory';
import RunDetail from './components/RunDetail';
import { clearGuestSession, GUEST_SESSION_KEY, startGuestSession, supabase } from './lib/supabase';
import { Cpu, AlertTriangle, LogOut, RefreshCw, UserRound } from 'lucide-react';

type View = { type: 'dashboard' } | { type: 'detail'; runId: string };

export default function App() {
  const [view, setView] = useState<View>({ type: 'dashboard' });
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingRuns, setIsLoadingRuns] = useState(true);
  const [error, setError] = useState('');
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [isGuest, setIsGuest] = useState(false);
  const hasLoadedRuns = useRef(false);
  const activeUserId = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    const applySession = (nextSession: Session | null) => {
      const nextUserId = nextSession?.user.id ?? null;
      if (activeUserId.current !== nextUserId) {
        activeUserId.current = nextUserId;
        hasLoadedRuns.current = false;
        setRuns([]);
        setIsLoadingRuns(Boolean(nextUserId));
        setView({ type: 'dashboard' });
      }
      setSession(nextSession);
      if (nextSession) {
        clearGuestSession();
        setIsGuest(false);
      } else {
        setIsGuest(Boolean(sessionStorage.getItem(GUEST_SESSION_KEY)));
      }
    };

    if (!supabase) {
      setIsGuest(Boolean(sessionStorage.getItem(GUEST_SESSION_KEY)));
      setAuthReady(true);
      return;
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!active) return;
      applySession(nextSession);
    });

    void supabase.auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      if (sessionError) setError(`Could not restore sign-in: ${sessionError.message}`);
      applySession(data.session);
      setAuthReady(true);
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  const fetchRuns = useCallback(async () => {
    if (!session) {
      setRuns([]);
      setIsLoadingRuns(false);
      return;
    }
    try {
      const data = await api.listRuns(20, 0);
      setRuns(data.runs);
      hasLoadedRuns.current = true;
      setError('');
    } catch (err) {
      if (!hasLoadedRuns.current) {
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to connect to the backend'
        );
      }
    } finally {
      setIsLoadingRuns(false);
    }
  }, [session]);

  useEffect(() => {
    if (!authReady) return;
    fetchRuns();
    if (!session) return;
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, [authReady, fetchRuns, session]);

  const handleGoogleSignIn = async () => {
    if (!supabase) {
      throw new Error('Google sign-in is not configured. Add the Supabase URL and publishable key.');
    }
    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    });
    if (signInError) throw signInError;
  };

  const handleGoogleSignInClick = async () => {
    try {
      await handleGoogleSignIn();
    } catch (signInError) {
      setError(signInError instanceof Error ? signInError.message : 'Google sign-in failed.');
    }
  };

  const handleContinueAsGuest = () => {
    startGuestSession();
    setIsGuest(true);
    setView({ type: 'dashboard' });
  };

  const handleSignOut = async () => {
    if (supabase) {
      const { error: signOutError } = await supabase.auth.signOut();
      if (signOutError) {
        setError(`Could not sign out: ${signOutError.message}`);
        return;
      }
    }
    setSession(null);
    setRuns([]);
    hasLoadedRuns.current = false;
    setIsLoadingRuns(false);
    setView({ type: 'dashboard' });
  };

  const handleLeaveGuest = () => {
    clearGuestSession();
    setIsGuest(false);
    setView({ type: 'dashboard' });
  };

  const handleSubmitGoal = async (goal: string) => {
    setIsSubmitting(true);
    setError('');

    try {
      const result = await api.createRun(goal);
      // Navigate to the run detail
      setView({ type: 'detail', runId: result.id });
      if (session) fetchRuns();
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

  const handleRetryRun = (runId: string) => {
    setView({ type: 'detail', runId });
    fetchRuns();
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
        {!authReady ? (
          <div className="glass-card mx-auto max-w-md p-8 text-center text-sm text-surface-400">
            Checking your sign-in…
          </div>
        ) : !session && !isGuest ? (
          <LoginGate
            googleConfigured={Boolean(supabase)}
            onGoogleSignIn={handleGoogleSignIn}
            onContinueAsGuest={handleContinueAsGuest}
          />
        ) : (
          <>
        <div className="mb-6 flex justify-end">
          {session ? (
            <button onClick={handleSignOut} className="btn-secondary text-xs">
              <LogOut size={14} />
              {session.user.email || 'Signed in'} · Sign out
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 text-xs text-surface-400">
                <UserRound size={14} /> Guest session
              </span>
              <button onClick={handleGoogleSignInClick} disabled={!supabase} className="btn-secondary text-xs">
                Sign in to save history
              </button>
              <button onClick={handleLeaveGuest} className="btn-secondary text-xs">
                Exit guest
              </button>
            </div>
          )}
        </div>
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
              isGuest={isGuest}
              onSignIn={handleGoogleSignInClick}
            />
          </div>
        ) : (
          <RunDetail
            runId={view.runId}
            onBack={handleBack}
            onRetry={handleRetryRun}
          />
        )}

        {/* Footer */}
        <footer className="mt-16 text-center text-xs text-surface-600">
          <p>AgentForge v0.2.0 — Phase 2: Tool Use & Web Research</p>
          <p className="mt-1">
            Autonomous tool use with live web search, webpage extraction, evidence tracking, and citation-backed reports.
          </p>
        </footer>
          </>
        )}
      </div>
    </div>
  );
}
