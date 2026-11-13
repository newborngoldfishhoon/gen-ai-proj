import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          flowType: 'pkce',
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
        },
      })
    : null;

export const GUEST_SESSION_KEY = 'agentforge.guest-session';

export function startGuestSession(): void {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  const token = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  sessionStorage.setItem(GUEST_SESSION_KEY, token);
}

export function clearGuestSession(): void {
  sessionStorage.removeItem(GUEST_SESSION_KEY);
}

export async function getRequestAuthHeaders(): Promise<Record<string, string>> {
  if (supabase) {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      return { Authorization: `Bearer ${session.access_token}` };
    }
  }

  const guestSession = sessionStorage.getItem(GUEST_SESSION_KEY);
  return guestSession ? { 'X-Guest-Session': guestSession } : {};
}
