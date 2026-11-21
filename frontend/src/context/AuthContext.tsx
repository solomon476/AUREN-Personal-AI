/**
 * Authentication Context and Session Management.
 * Manages Supabase Auth lifecycle, persistent session storage, and backend profile validation.
 * Elevated with structured email confirmation handling, duplicate user detection, and friendly error states.
 */

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase, isSupabaseConfigured } from '../lib/supabase';
import { fetchMyProfile, UserProfileResponse } from '../api/auth';
import { clearUserDataCache } from '../lib/queryClient';

export interface SignUpResult {
  success: boolean;
  error?: string;
  requiresEmailConfirmation?: boolean;
  userExists?: boolean;
}

export interface SignInResult {
  success: boolean;
  error?: string;
}

interface AuthContextType {
  user: User | null;
  session: Session | null;
  profile: UserProfileResponse | null;
  isLoading: boolean;
  error: string | null;
  isConfigured: boolean;
  signIn: (email: string, password: string) => Promise<SignInResult>;
  signUp: (email: string, password: string, fullName?: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<UserProfileResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const prevUserIdRef = useRef<string | null>(null);

  const refreshProfile = useCallback(async () => {
    if (!session) {
      setProfile(null);
      return;
    }
    try {
      const backendProfile = await fetchMyProfile();
      setProfile(backendProfile);
      setError(null);
    } catch (err) {
      console.warn('Backend profile verification warning:', err);
      // Session exists locally in Supabase, but backend verification may fail if keys mismatch or backend is offline
      setProfile(null);
    }
  }, [session]);

  useEffect(() => {
    let isMounted = true;

    // 1. Support local test or preview sessions stored in localStorage (for test/preview environments)
    const testSessionRaw = typeof window !== 'undefined' ? window.localStorage.getItem('auren_test_session') : null;
    if (testSessionRaw) {
      try {
        const parsed = JSON.parse(testSessionRaw);
        setUser(parsed.user ?? null);
        setSession(parsed.session ?? null);
        setProfile(parsed.profile ?? null);
        prevUserIdRef.current = parsed.user?.id ?? null;
        setIsLoading(false);
        return;
      } catch {
        // Invalid test session JSON, fallback to standard flow
      }
    }

    if (!supabase) {
      setIsLoading(false);
      return;
    }

    // 2. Initial session load from Supabase persistent storage
    supabase.auth
      .getSession()
      .then(({ data: { session: initialSession }, error: sessionError }) => {
        if (!isMounted) return;
        if (sessionError) {
          setError(sessionError.message);
        }
        setSession(initialSession);
        setUser(initialSession?.user ?? null);
        prevUserIdRef.current = initialSession?.user?.id ?? null;
        setIsLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to retrieve session');
        setIsLoading(false);
      });

    // 3. Subscribe to auth state changes (login, logout, token refresh)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, newSession) => {
      if (!isMounted) return;
      const prevUserId = prevUserIdRef.current;
      const nextUserId = newSession?.user?.id ?? null;
      prevUserIdRef.current = nextUserId;

      setSession(newSession);
      setUser(newSession?.user ?? null);
      setIsLoading(false);

      if (event === 'SIGNED_OUT' || !newSession) {
        clearUserDataCache();
        setProfile(null);
      } else if (prevUserId && nextUserId && prevUserId !== nextUserId) {
        clearUserDataCache();
        setProfile(null);
      } else if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
        setError(null);
      }
    });

    // 4. Capacitor native deep-link listener for mobile OAuth/Magic Link callbacks (auren://auth/callback)
    let capAppListener: any = null;
    try {
      import('@capacitor/app')
        .then(({ App }) => {
          if (!isMounted) return;
          capAppListener = App.addListener('appUrlOpen', async (data: { url: string }) => {
            if (data?.url && (data.url.includes('access_token') || data.url.includes('code='))) {
              try {
                const urlObj = new URL(data.url);
                const hashParams = new URLSearchParams(urlObj.hash.substring(1));
                const accessToken = hashParams.get('access_token');
                const refreshToken = hashParams.get('refresh_token');
                if (accessToken && refreshToken && supabase) {
                  await supabase.auth.setSession({
                    access_token: accessToken,
                    refresh_token: refreshToken,
                  });
                }
              } catch (urlErr) {
                console.warn('Failed parsing deep link auth url:', urlErr);
              }
            }
          });
        })
        .catch(() => {
          // Not running in Capacitor or plugin unavailable
        });
    } catch {
      // Non-blocking Capacitor check
    }

    return () => {
      isMounted = false;
      subscription.unsubscribe();
      if (capAppListener && typeof capAppListener.remove === 'function') {
        capAppListener.remove();
      }
    };
  }, []);

  // Update backend profile when session changes
  useEffect(() => {
    if (session) {
      refreshProfile();
    } else {
      setProfile(null);
    }
  }, [session, refreshProfile]);

  const signIn = async (email: string, password: string): Promise<SignInResult> => {
    if (!supabase) {
      return { success: false, error: 'Supabase authentication is not configured in .env' };
    }
    setError(null);
    const cleanEmail = email.trim();

    const { data, error: signInError } = await supabase.auth.signInWithPassword({
      email: cleanEmail,
      password,
    });

    if (signInError) {
      let friendlyError = signInError.message;
      const lower = signInError.message.toLowerCase();

      if (lower.includes('invalid login credentials') || lower.includes('invalid credentials')) {
        friendlyError = 'Invalid email or password. Please check your credentials and try again.';
      } else if (lower.includes('email not confirmed')) {
        friendlyError = 'Email address not yet confirmed. Please verify your email using the link sent to your inbox.';
      }

      setError(friendlyError);
      return { success: false, error: friendlyError };
    }

    setSession(data.session);
    setUser(data.user);
    prevUserIdRef.current = data.user?.id ?? null;
    return { success: true };
  };

  const signUp = async (
    email: string,
    password: string,
    fullName?: string
  ): Promise<SignUpResult> => {
    if (!supabase) {
      return { success: false, error: 'Supabase authentication is not configured in .env' };
    }
    setError(null);
    const cleanEmail = email.trim();
    const cleanFullName = (fullName || '').trim();
    const redirectUrl = typeof window !== 'undefined' ? `${window.location.origin}/` : undefined;

    const { data, error: signUpError } = await supabase.auth.signUp({
      email: cleanEmail,
      password,
      options: {
        data: {
          full_name: cleanFullName,
        },
        emailRedirectTo: redirectUrl,
      },
    });

    if (signUpError) {
      let friendlyError = signUpError.message;
      let userExists = false;
      const lower = signUpError.message.toLowerCase();

      if (lower.includes('already registered') || lower.includes('user already exists')) {
        friendlyError = 'An account with this email already exists. Please sign in instead.';
        userExists = true;
      } else if (
        signUpError.message.includes('over_email_send_rate_limit') ||
        lower.includes('rate limit')
      ) {
        friendlyError =
          'Email delivery rate limit reached. Supabase limits verification emails per hour. Please wait a few minutes before trying again.';
      }

      setError(friendlyError);
      return { success: false, error: friendlyError, userExists };
    }

    // Check duplicate user detection with email confirmation enabled (identities array empty)
    if (data.user && data.user.identities && data.user.identities.length === 0) {
      const duplicateMsg = 'An account with this email already exists. Please sign in instead.';
      setError(duplicateMsg);
      return {
        success: false,
        userExists: true,
        error: duplicateMsg,
      };
    }

    // Check if email confirmation is required (user created, but session is null pending verification)
    if (!data.session && data.user) {
      setSession(null);
      setUser(null);
      return { success: true, requiresEmailConfirmation: true };
    }

    // Immediate session (email confirmation disabled or auto-confirmed)
    setSession(data.session);
    setUser(data.user);
    prevUserIdRef.current = data.user?.id ?? null;
    return { success: true, requiresEmailConfirmation: false };
  };

  const signOut = async () => {
    if (supabase) {
      try {
        await supabase.auth.signOut();
      } catch (err) {
        console.warn('Supabase signOut warning:', err);
      }
    }
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('auren_test_session');
    }
    clearUserDataCache();
    setSession(null);
    setUser(null);
    setProfile(null);
    setError(null);
    prevUserIdRef.current = null;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        profile,
        isLoading,
        error,
        isConfigured: isSupabaseConfigured,
        signIn,
        signUp,
        signOut,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

const defaultGuestAuth: AuthContextType = {
  user: null,
  session: null,
  profile: null,
  isLoading: false,
  error: null,
  isConfigured: false,
  signIn: async () => ({ success: false, error: 'Auth not initialized' }),
  signUp: async () => ({ success: false, error: 'Auth not initialized' }),
  signOut: async () => {},
  refreshProfile: async () => {},
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  return context || defaultGuestAuth;
}
