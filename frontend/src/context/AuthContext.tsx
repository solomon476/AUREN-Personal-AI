/**
 * Authentication Context and Session Management.
 * Manages Supabase Auth lifecycle, persistent session storage, and backend profile validation.
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import { fetchMyProfile, UserProfileResponse } from '../api/auth';
import { clearUserDataCache } from '../lib/queryClient';

interface AuthContextType {
  user: User | null;
  session: Session | null;
  profile: UserProfileResponse | null;
  isLoading: boolean;
  error: string | null;
  isConfigured: boolean;
  signIn: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  signUp: (email: string, password: string, fullName?: string) => Promise<{ success: boolean; error?: string }>;
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

  const isConfigured = supabase !== null;

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
      // Session exists locally in Supabase, but backend verification may fail if keys mismatch
      setProfile(null);
    }
  }, [session]);

  useEffect(() => {
    // Support local test or preview sessions stored in localStorage
    const testSessionRaw = window.localStorage.getItem('auren_test_session');
    if (testSessionRaw) {
      try {
        const parsed = JSON.parse(testSessionRaw);
        setUser(parsed.user ?? null);
        setSession(parsed.session ?? null);
        setProfile(parsed.profile ?? null);
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

    // 1. Initial session load
    supabase.auth.getSession().then(({ data: { session: initialSession }, error: sessionError }) => {
      if (sessionError) {
        setError(sessionError.message);
      }
      setSession(initialSession);
      setUser(initialSession?.user ?? null);
      setIsLoading(false);
    });

    // 2. Subscribe to auth state changes (login, logout, token refresh)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      setSession(newSession);
      setUser(newSession?.user ?? null);
      if (!newSession) {
        clearUserDataCache();
        setProfile(null);
      }
    });

    return () => {
      subscription.unsubscribe();
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

  const signIn = async (email: string, password: string) => {
    if (!supabase) {
      return { success: false, error: 'Supabase credentials are not configured in .env' };
    }
    setError(null);
    const { data, error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (signInError) {
      setError(signInError.message);
      return { success: false, error: signInError.message };
    }
    setSession(data.session);
    setUser(data.user);
    return { success: true };
  };

  const signUp = async (email: string, password: string, fullName?: string) => {
    if (!supabase) {
      return { success: false, error: 'Supabase credentials are not configured in .env' };
    }
    setError(null);
    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName || '',
        },
      },
    });
    if (signUpError) {
      setError(signUpError.message);
      return { success: false, error: signUpError.message };
    }
    setSession(data.session);
    setUser(data.user);
    return { success: true };
  };

  const signOut = async () => {
    if (supabase) {
      await supabase.auth.signOut();
    }
    clearUserDataCache();
    setSession(null);
    setUser(null);
    setProfile(null);
    setError(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        profile,
        isLoading,
        error,
        isConfigured,
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

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

