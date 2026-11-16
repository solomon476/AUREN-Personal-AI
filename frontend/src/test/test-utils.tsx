/**
 * Testing utilities and custom render functions for React Testing Library.
 * Provides QueryClient, AuthContext, and Router wrappers for unit and integration testing.
 */

import React from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthContext } from '../context/AuthContext';
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router';
import { routeTree } from '../router';
import type { User, Session } from '@supabase/supabase-js';
import { UserProfileResponse } from '../api/auth';

export const defaultTestUser: User = {
  id: 'test-user-123',
  app_metadata: { provider: 'email' },
  user_metadata: { full_name: 'Solomon Tester' },
  aud: 'authenticated',
  created_at: new Date().toISOString(),
  email: 'test@auren.ai',
  role: 'authenticated',
};

export const defaultTestProfile: UserProfileResponse = {
  id: 'test-user-123',
  email: 'test@auren.ai',
  role: 'authenticated',
  full_name: 'Solomon Tester',
  avatar_url: null,
  app_metadata: {},
  user_metadata: {},
};

export interface MockAuthOptions {
  user?: User | null;
  session?: Session | null;
  profile?: UserProfileResponse | null;
  isLoading?: boolean;
}

export const MockAuthProvider: React.FC<{ children: React.ReactNode; auth?: MockAuthOptions }> = ({
  children,
  auth,
}) => {
  const user = auth?.user !== undefined ? auth.user : defaultTestUser;
  const session =
    auth?.session !== undefined
      ? auth.session
      : user
      ? ({ access_token: 'mock-jwt-token', user } as Session)
      : null;
  const profile =
    auth?.profile !== undefined
      ? auth.profile
      : user
      ? defaultTestProfile
      : null;

  const value = {
    user,
    session,
    profile,
    isLoading: auth?.isLoading ?? false,
    error: null,
    isConfigured: true,
    signIn: async () => ({ success: true }),
    signUp: async () => ({ success: true }),
    signOut: async () => {},
    refreshProfile: async () => {},
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
        gcTime: Infinity,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function createWrapper(queryClient?: QueryClient, auth?: MockAuthOptions) {
  const client = queryClient ?? createTestQueryClient();
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MockAuthProvider auth={auth}>{children}</MockAuthProvider>
      </QueryClientProvider>
    );
  };
}

export function renderWithProviders(
  ui: React.ReactElement,
  options?: Omit<RenderOptions, 'wrapper'> & {
    queryClient?: QueryClient;
    auth?: MockAuthOptions;
  }
) {
  const testClient = options?.queryClient ?? createTestQueryClient();
  const Wrapper = createWrapper(testClient, options?.auth);

  return {
    queryClient: testClient,
    ...render(ui, {
      wrapper: Wrapper,
      ...options,
    }),
  };
}

/**
 * Render a complete router test instance at a specific initial path with configurable auth.
 */
export async function renderRouter(
  initialPath: string = '/chat',
  authOptions?: MockAuthOptions
) {
  const queryClient = createTestQueryClient();
  const history = createMemoryHistory({ initialEntries: [initialPath] });
  const testRouter = createRouter({
    routeTree,
    history,
  });

  await testRouter.load();

  const renderResult = render(
    <QueryClientProvider client={queryClient}>
      <MockAuthProvider auth={authOptions}>
        <RouterProvider router={testRouter} />
      </MockAuthProvider>
    </QueryClientProvider>
  );

  return {
    ...renderResult,
    router: testRouter,
    queryClient,
    history,
  };
}
