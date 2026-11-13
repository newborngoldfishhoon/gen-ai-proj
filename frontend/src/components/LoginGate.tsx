import { useState } from 'react';
import { Chrome, Compass, LoaderCircle, LockKeyhole } from 'lucide-react';

interface LoginGateProps {
  googleConfigured: boolean;
  onGoogleSignIn: () => Promise<void>;
  onContinueAsGuest: () => void;
}

export default function LoginGate({
  googleConfigured,
  onGoogleSignIn,
  onContinueAsGuest,
}: LoginGateProps) {
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [error, setError] = useState('');

  const handleGoogleSignIn = async () => {
    setIsSigningIn(true);
    setError('');
    try {
      await onGoogleSignIn();
    } catch (signInError) {
      setError(signInError instanceof Error ? signInError.message : 'Google sign-in failed.');
      setIsSigningIn(false);
    }
  };

  return (
    <main className="glass-card mx-auto max-w-md p-8 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-brand-500/20 bg-brand-600/15">
        <LockKeyhole className="text-brand-400" size={24} />
      </div>
      <h2 className="mb-2 text-xl font-bold text-surface-100">Welcome to AgentForge</h2>
      <p className="mb-6 text-sm leading-relaxed text-surface-400">
        Sign in with Google to keep your research private and save your history to your account.
      </p>

      <div className="space-y-3">
        <button
          className="btn-primary w-full"
          disabled={!googleConfigured || isSigningIn}
          onClick={handleGoogleSignIn}
        >
          {isSigningIn ? <LoaderCircle size={17} className="animate-spin" /> : <Chrome size={17} />}
          Continue with Google
        </button>
        {!googleConfigured && (
          <p className="text-xs text-amber-300">
            Google sign-in needs Supabase settings in the deployment environment.
          </p>
        )}
        <button className="btn-secondary w-full" onClick={onContinueAsGuest}>
          <Compass size={17} />
          Continue as guest
        </button>
      </div>

      {error && <p role="alert" className="mt-4 text-sm text-red-400">{error}</p>}
      <p className="mt-5 text-xs text-surface-500">
        Guest runs are temporary and won’t appear in saved history.
      </p>
    </main>
  );
}
