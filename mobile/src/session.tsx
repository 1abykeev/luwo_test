import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api, isSessionExpired } from '@/api/client';
import type { Profile } from '@/api/types';
import { clearSession, loadSession, saveSession } from '@/storage';

export type SessionState =
  | { status: 'loading' }
  | { status: 'signedOut' }
  | { status: 'signedIn'; token: string; profile: Profile; email: string | null };

interface SessionContextValue {
  state: SessionState;
  signIn: (email: string, password: string) => Promise<void>; // throws ApiError on failure
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: 'loading' });

  // On start: reopen the saved session, and ask the server who we are (the account may have been removed).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const saved = await loadSession();
      if (!saved) return cancelled ? undefined : setState({ status: 'signedOut' });
      try {
        const profile = await api.me(saved.token);
        if (!cancelled) setState({ status: 'signedIn', token: saved.token, profile, email: saved.email ?? null });
      } catch (error) {
        if (cancelled) return;
        if (isSessionExpired(error)) {
          await clearSession();
          setState({ status: 'signedOut' });
        } else {
          // the server is unreachable: keep the saved session, the chat will show the connection problem
          setState({ status: 'signedIn', token: saved.token, profile: saved.profile, email: saved.email ?? null });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const address = email.trim().toLowerCase();
    const response = await api.login(address, password);
    await saveSession({ token: response.access_token, profile: response.user, email: address });
    setState({ status: 'signedIn', token: response.access_token, profile: response.user, email: address });
  }, []);

  const signOut = useCallback(async () => {
    await clearSession();
    setState({ status: 'signedOut' });
  }, []);

  const value = useMemo(() => ({ state, signIn, signOut }), [state, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used inside <SessionProvider>');
  return value;
}
